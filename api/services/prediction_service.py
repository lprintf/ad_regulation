"""
Service layer for prediction operations.
Encapsulates business logic for evaluating ads using trained ML models.
"""

import os
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from baseline.data_build import build_features, clean_data
from baseline.get_data import get_insight, insight_to_df
from baseline.train_tools import load_model
from utils.db import ADAccountDocument


class PredictionService:
    """Service for ad performance prediction using ML models."""

    # Model cache
    _model_cache: HistGradientBoostingClassifier | None = None
    _model_path: str = "models/model.feather"

    @classmethod
    def _get_model(cls) -> HistGradientBoostingClassifier:
        """
        Load and cache the trained model.

        Returns:
            Trained HistGradientBoostingClassifier model

        Raises:
            FileNotFoundError: If model file doesn't exist
        """
        if cls._model_cache is None:
            if not os.path.exists(cls._model_path):
                raise FileNotFoundError(
                    f"Model file not found: {cls._model_path}. "
                    "Please train a model first using baseline/train_tools.py"
                )
            cls._model_cache = load_model(cls._model_path)
        return cls._model_cache

    @staticmethod
    async def predict_today(
        ad_account_ids: list[str] | None = None,
        lookback_days: int = 10,
        model_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Predict ad performance for today using the trained model.

        Args:
            ad_account_ids: List of ad account IDs to evaluate. If None, evaluate all accounts.
            lookback_days: Number of days to look back for feature calculation (default: 10)
            model_path: Optional custom model path

        Returns:
            Dictionary containing predictions with ad_id, date, pred_proba, and features

        Raises:
            FileNotFoundError: If model file doesn't exist
            ValueError: If no valid data found
        """
        # Override model path if provided
        if model_path:
            PredictionService._model_path = model_path
            PredictionService._model_cache = None

        # Load model
        model = PredictionService._get_model()

        # Calculate date range
        yesterday = datetime.now() - timedelta(days=1)
        until = yesterday.strftime("%Y-%m-%d")
        since = (yesterday - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        # Get ad accounts
        if ad_account_ids is None:
            ad_accounts = await ADAccountDocument.find(fetch_links=True).to_list()
            ad_account_ids = [acc.id for acc in ad_accounts]
            ad_account_name_dict = {acc.id: acc.name for acc in ad_accounts}
        else:
            # Fetch specific accounts
            ad_accounts = await ADAccountDocument.find(
                {"_id": {"$in": ad_account_ids}}, fetch_links=True
            ).to_list()
            ad_account_name_dict = {acc.id: acc.name for acc in ad_accounts}

        # Process each ad account
        all_predictions = []

        for ad_account_id in ad_account_ids:
            try:
                # Fetch insights data
                insight = await get_insight(ad_account_id, since=since, until=until)
                df = insight_to_df(insight)

                if df.empty:
                    continue

                # Clean data
                df_clean = clean_data(df)

                # Build features (use iloc_index=-1 to get only the latest day)
                features = build_features(df_clean, iloc_index=-1)

                if features.empty:
                    continue

                # Prepare features for prediction (drop ad_id and date)
                feature_cols = [col for col in features.columns if col not in ["ad_id", "date"]]
                X = features[feature_cols].fillna(0)

                # Predict
                pred_proba = model.predict_proba(X)[:, 1]

                # Add predictions to features
                features["pred_proba"] = pred_proba
                features["ad_account_name"] = ad_account_name_dict.get(
                    ad_account_id, ad_account_id
                )

                # Reorder columns: ad_account_name, ad_id, date, pred_proba, then features
                cols = ["ad_account_name", "ad_id", "date", "pred_proba"] + [
                    col
                    for col in features.columns
                    if col not in ["ad_account_name", "ad_id", "date", "pred_proba"]
                ]
                features = features.reindex(columns=cols)

                all_predictions.append(features)

            except Exception as e:
                print(f"Error processing account {ad_account_id}: {e}")
                continue

        if not all_predictions:
            raise ValueError("No valid predictions could be generated. Check if ads have sufficient data.")

        # Combine all predictions
        all_predictions_df = pd.concat(all_predictions, axis=0, ignore_index=True)

        # Convert to list of dictionaries
        predictions_list = PredictionService._df_to_predictions_list(all_predictions_df)

        return {
            "predictions": predictions_list,
            "total_records": len(predictions_list),
            "date_range": {"since": since, "until": until},
            "evaluation_date": yesterday.strftime("%Y-%m-%d"),
        }

    @staticmethod
    async def predict_for_account(
        ad_account_id: str,
        lookback_days: int = 10,
        model_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Predict ad performance for a specific ad account.

        Args:
            ad_account_id: Ad account ID to evaluate
            lookback_days: Number of days to look back for feature calculation
            model_path: Optional custom model path

        Returns:
            Dictionary containing predictions for the specified account
        """
        result = await PredictionService.predict_today(
            ad_account_ids=[ad_account_id],
            lookback_days=lookback_days,
            model_path=model_path,
        )
        return result

    @staticmethod
    def _df_to_predictions_list(df: pd.DataFrame) -> list[dict[str, Any]]:
        """
        Convert predictions DataFrame to list of dictionaries.

        Args:
            df: DataFrame with predictions and features

        Returns:
            List of prediction dictionaries
        """
        predictions_list = []

        for _, row in df.iterrows():
            # Extract main fields
            prediction_record = {
                "ad_account_name": str(row["ad_account_name"]),
                "ad_id": str(row["ad_id"]),
                "date": str(row["date"]),
                "pred_proba": float(row["pred_proba"]),
                "features": {},
            }

            # Add all features (excluding main fields)
            excluded_fields = {"ad_account_name", "ad_id", "date", "pred_proba"}
            for col in df.columns:
                if col not in excluded_fields:
                    value = row[col]
                    # Convert to appropriate type
                    if pd.isna(value):
                        prediction_record["features"][col] = None
                    elif isinstance(value, (int, np.integer)):
                        prediction_record["features"][col] = int(value)
                    elif isinstance(value, (float, np.floating)):
                        prediction_record["features"][col] = float(value)
                    else:
                        prediction_record["features"][col] = str(value)

            predictions_list.append(prediction_record)

        return predictions_list
