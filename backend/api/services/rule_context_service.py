"""
Utility service to build execution context with real advertising data.
Fetches insights metrics from MongoDB+Redis hybrid cache for fast, realtime execution.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from facebook_business.adobjects.ad import Ad

from utils.db import RuleBindingDocument, AdEntityNamesDocument

logger = logging.getLogger(__name__)


class RuleContextService:
    """Builds contextual data for rule execution."""

    LAST_N_DAYS = 14  # Default fallback

    @staticmethod
    async def build_context(
        binding: RuleBindingDocument | None,
        params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if binding is None:
            return {}

        if binding.entity_type == "ad":
            return await RuleContextService._build_ad_context(binding, params)

        return {
            "rule_name": binding.rule_name,
            "entity_id": binding.entity_id,
            "entity_type": binding.entity_type,
            "metadata": binding.metadata,
            "notes": ["No specialised context builder for this entity type."],
        }

    @staticmethod
    async def _build_ad_context(
        binding: RuleBindingDocument,
        params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Build context for ad entity using MongoDB+Redis hybrid insights.
        Fast and realtime - combines historical (MongoDB) + recent (Redis) data.
        """
        from api.services.insights_service import InsightsService

        ad_account_id = binding.metadata.get("ad_account_id")
        if not ad_account_id:
            raise ValueError(
                "Rule binding metadata must include 'ad_account_id' for ad entities"
            )

        ad_id = binding.entity_id
        fetch_errors: list[str] = []

        # Use lookback_days from params if provided, otherwise use default
        lookback_days = RuleContextService.LAST_N_DAYS
        if params and "lookback_days" in params:
            lookback_days = int(params["lookback_days"])

        # Support evaluation_date for historical simulation
        reference_date = datetime.utcnow()
        if params and params.get("evaluation_date"):
            try:
                from datetime import datetime as dt
                evaluation_date_str = params["evaluation_date"]
                reference_date = dt.strptime(evaluation_date_str, "%Y-%m-%d")
                logger.info(
                    "Using evaluation_date=%s for historical simulation",
                    evaluation_date_str
                )
            except Exception as exc:
                logger.warning(
                    "Invalid evaluation_date format '%s', using current date: %s",
                    params.get("evaluation_date"),
                    exc
                )

        # Query ad entity metadata from MongoDB
        ad_entity = await AdEntityNamesDocument.find_one(
            AdEntityNamesDocument.account_id == ad_account_id,
            AdEntityNamesDocument.entity_type == "ad",
            AdEntityNamesDocument.entity_id == ad_id
        )

        ad_details: dict[str, Any] = {
            "ad_id": ad_id,
            "name": ad_entity.entity_name if ad_entity else None,
            "account_id": ad_account_id,
            "configured_status": ad_entity.configured_status if ad_entity else None,
            "effective_status": ad_entity.effective_status if ad_entity else None,
        }

        # Query insights from MongoDB+Redis hybrid (last N days from reference_date)
        since = reference_date - timedelta(days=lookback_days)
        until = reference_date

        since_str = since.strftime("%Y-%m-%d")
        until_str = until.strftime("%Y-%m-%d")

        try:
            insights_data = await InsightsService.query_insights_mongo_redis(
                ad_account_id=ad_account_id,
                since=since_str,
                until=until_str,
                level="ad",
                time_increment=1,
                object_level="ad",
                object_ids=[ad_id],
                mask_ad_ids=False,
            )

            # Extract insights records
            insights_records = insights_data.get("insights", [])

            if not insights_records:
                logger.warning(
                    "No insights data found for ad_id=%s in last %d days",
                    ad_id,
                    lookback_days
                )
                fetch_errors.append(
                    f"No insights data found for ad {ad_id}"
                )

        except Exception as exc:
            logger.error(
                "Failed to fetch insights for ad %s: %s", ad_id, exc, exc_info=True
            )
            fetch_errors.append(f"Failed to fetch insights: {exc}")
            insights_records = []

        # Transform to daily samples format
        insights_rows: list[dict[str, Any]] = []
        for record in insights_records:
            metrics = record.get("metrics", {})
            insights_rows.append({
                "spend": float(metrics.get("spend") or 0),
                "clicks": int(metrics.get("clicks") or 0),
                "impressions": int(metrics.get("impressions") or 0),
                "reach": int(metrics.get("reach") or 0),
                "inline_link_clicks": int(metrics.get("inline_link_clicks") or 0),
                "outbound_clicks": int(metrics.get("outbound_clicks") or 0),
                "landing_page_view": int(metrics.get("landing_page_view") or 0),
                "onsite_web_add_to_cart": int(metrics.get("onsite_web_add_to_cart") or 0),
                "onsite_web_checkout": int(metrics.get("onsite_web_checkout") or 0),
                "onsite_web_purchase": int(metrics.get("onsite_web_purchase") or 0),
                "onsite_web_add_to_cart_value": float(metrics.get("onsite_web_add_to_cart_value") or 0),
                "onsite_web_checkout_value": float(metrics.get("onsite_web_checkout_value") or 0),
                "onsite_web_purchase_value": float(metrics.get("onsite_web_purchase_value") or 0),
                "date_start": record.get("date"),
                "date_stop": record.get("date"),
            })

        # Aggregate metrics
        total_spend = sum(row["spend"] for row in insights_rows)
        total_clicks = sum(row["clicks"] for row in insights_rows)
        total_impressions = sum(row["impressions"] for row in insights_rows)

        ctr = (total_clicks / total_impressions * 100) if total_impressions else 0.0
        cpc = (total_spend / total_clicks) if total_clicks else None

        # ML Prediction (enabled by default for ML-related rules)
        # Check if explicitly disabled, otherwise enable by default
        enable_ml = True
        if params and "enable_ml_prediction" in params:
            enable_ml = params["enable_ml_prediction"]

        ml_prediction: dict[str, Any] | None = None
        if enable_ml:
            try:
                ml_prediction = await RuleContextService._compute_ml_prediction(
                    ad_account_id=ad_account_id,
                    ad_id=ad_id,
                    insights_rows=insights_rows,
                    reference_date=until_str,
                    lookback_days=lookback_days,
                )
                logger.info(
                    "ML prediction computed for ad %s: available=%s, stop_proba=%.2f%%",
                    ad_id,
                    ml_prediction.get("available", False),
                    ml_prediction.get("stop_probability", 0) * 100,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to compute ML prediction for ad %s: %s",
                    ad_id, exc, exc_info=True
                )
                ml_prediction = {
                    "error": str(exc),
                    "available": False,
                }

        # Try to get targeting info from metadata or Facebook API (lightweight call)
        targeting_countries: list[str] = []
        try:
            from utils.fb_api_flyweight_factory import get_api
            api = await get_api(ad_account_id)
            ad = Ad(ad_id, api=api)

            def _fetch_targeting() -> list[str]:
                ad_data = ad.api_get(fields=[Ad.Field.targeting])
                targeting = ad_data.get(Ad.Field.targeting) or {}
                countries = (
                    targeting.get("geo_locations", {}).get("countries")
                    if isinstance(targeting, dict)
                    else None
                )
                return list(countries or [])

            targeting_countries = await asyncio.to_thread(_fetch_targeting)
        except Exception as exc:
            logger.warning(
                "Failed to fetch targeting for ad %s: %s", ad_id, exc
            )
            # Don't add to fetch_errors since this is optional

        return {
            "rule_name": binding.rule_name,
            "entity_type": binding.entity_type,
            "entity_id": binding.entity_id,
            "metadata": binding.metadata,
            "ad": ad_details,
            "targeting": {
                "countries": targeting_countries,
            },
            "performance": {
                "spend": total_spend,
                "clicks": total_clicks,
                "impressions": total_impressions,
                "ctr": ctr,
                "ctr_unit": "percent",
                "cpc": cpc,
                "currency": "USD",
                "window": {
                    "since": insights_rows[0]["date_start"] if insights_rows else None,
                    "until": insights_rows[-1]["date_stop"] if insights_rows else None,
                    "days": lookback_days,
                },
                "daily_samples": insights_rows,
            },
            "ml_prediction": ml_prediction,  # ML prediction data (if enabled)
            "fetch_errors": fetch_errors,
        }

    @staticmethod
    async def _compute_ml_prediction(
        ad_account_id: str,
        ad_id: str,
        insights_rows: list[dict[str, Any]],
        reference_date: str,
        lookback_days: int,
    ) -> dict[str, Any]:
        """
        Compute ML prediction for the given ad using historical insights data.

        Returns:
            Dictionary with prediction probability and feature importance.
        """
        import pandas as pd
        import numpy as np
        from baseline.data_build import build_features, clean_data
        from baseline.train_tools import load_model
        import os

        # Check if model exists
        model_path = "models/model.feather"
        if not os.path.exists(model_path):
            return {
                "available": False,
                "error": f"Model file not found: {model_path}",
                "message": "Train a model first using baseline/train_tools.py",
            }

        # Convert insights_rows to DataFrame format expected by baseline
        df_data = []
        for row in insights_rows:
            df_data.append({
                "ad_id": ad_id,
                "date": row["date_start"],
                "spend": float(row.get("spend", 0)),
                "impressions": int(row.get("impressions", 0)),
                "reach": int(row.get("reach", 0)),
                "clicks": int(row.get("clicks", 0)),
                "inline_link_clicks": int(row.get("inline_link_clicks", 0)),
                "outbound_clicks": int(row.get("outbound_clicks", 0)),
                "landing_page_view": int(row.get("landing_page_view", 0)),
                "onsite_web_add_to_cart": int(row.get("onsite_web_add_to_cart", 0)),
                "onsite_web_checkout": int(row.get("onsite_web_checkout", 0)),
                "onsite_web_purchase": int(row.get("onsite_web_purchase", 0)),
                "onsite_web_add_to_cart_value": float(row.get("onsite_web_add_to_cart_value", 0)),
                "onsite_web_checkout_value": float(row.get("onsite_web_checkout_value", 0)),
                "onsite_web_purchase_value": float(row.get("onsite_web_purchase_value", 0)),
            })

        if not df_data:
            return {
                "available": False,
                "error": "No data available for prediction",
            }

        df = pd.DataFrame(df_data)

        # Clean data
        try:
            df_clean = clean_data(df)
            if df_clean.empty:
                return {
                    "available": False,
                    "error": "No valid data after cleaning (insufficient spend or samples)",
                }
        except Exception as exc:
            return {
                "available": False,
                "error": f"Data cleaning failed: {exc}",
            }

        # Build features (use iloc_index=-1 to get only the latest observation)
        try:
            features = build_features(df_clean, iloc_index=-1)
            if features.empty:
                return {
                    "available": False,
                    "error": "Failed to build features (insufficient historical data)",
                }
        except Exception as exc:
            return {
                "available": False,
                "error": f"Feature building failed: {exc}",
            }

        # Load model and predict
        try:
            model_package = load_model(model_path)

            # Handle both old format (model object) and new format (dict with feature_names)
            if isinstance(model_package, dict) and "model" in model_package:
                model = model_package["model"]
                saved_feature_names = model_package.get("feature_names", [])
                logger.info(
                    "Loaded model in NEW format with %d saved feature names",
                    len(saved_feature_names)
                )
            else:
                # Old format: just the model object
                model = model_package
                saved_feature_names = []
                logger.warning("Loaded model in OLD format without feature names")

            # Prepare features (drop ad_id and date)
            feature_cols = [col for col in features.columns if col not in ["ad_id", "date"]]
            logger.info(
                "Features built: %d columns (excluding ad_id, date)",
                len(feature_cols)
            )

            # If model was saved with feature names, reorder to match
            if saved_feature_names:
                # Check for missing features
                available_features = set(features.columns)
                missing_features = [f for f in saved_feature_names if f not in available_features]
                extra_features = [f for f in feature_cols if f not in saved_feature_names]

                if missing_features:
                    logger.error(
                        "Missing %d features required by model: %s",
                        len(missing_features),
                        missing_features[:5]  # Show first 5
                    )
                    return {
                        "available": False,
                        "error": f"Missing {len(missing_features)} features: {missing_features[:5]}",
                    }

                if extra_features:
                    logger.warning(
                        "Found %d extra features not in model: %s",
                        len(extra_features),
                        extra_features[:5]
                    )

                # Use saved feature order
                X = features[saved_feature_names].fillna(0)
                logger.info(
                    "Reordered features to match model (%d features)",
                    len(saved_feature_names)
                )
            else:
                # Old behavior: use features as-is (may cause issues)
                X = features[feature_cols].fillna(0)
                logger.warning(
                    "Model does not have saved feature names, using current feature order. "
                    "This may cause prediction errors. Retrain the model to fix this."
                )

            # Get prediction probability
            pred_proba = model.predict_proba(X)[0, 1]  # Probability of class 1 (stop)

            # Get feature importances if available
            feature_importance = {}
            if hasattr(model, 'feature_importances_'):
                importances = model.feature_importances_
                # Get top 10 most important features
                top_indices = np.argsort(importances)[::-1][:10]
                used_features = saved_feature_names if saved_feature_names else feature_cols
                for idx in top_indices:
                    if idx < len(used_features):
                        feature_importance[used_features[idx]] = float(importances[idx])

            return {
                "available": True,
                "stop_probability": float(pred_proba),
                "evaluation_date": reference_date,
                "lookback_days": lookback_days,
                "features_used": len(saved_feature_names) if saved_feature_names else len(feature_cols),
                "feature_importance": feature_importance,
                "model_path": model_path,
            }

        except Exception as exc:
            logger.error(
                "ML prediction failed for ad %s: %s",
                ad_id, exc, exc_info=True
            )
            return {
                "available": False,
                "error": f"Prediction failed: {exc}",
            }

