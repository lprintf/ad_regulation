"""
Predictions endpoints.
Provides API for evaluating ad performance using trained ML models.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from api.dependencies.auth import get_current_user
from api.models.insights import (
    PredictionRecord,
    PredictionRequest,
    PredictionResponse,
)
from api.models.responses import SuccessResponse
from api.services.prediction_service import PredictionService

router = APIRouter(prefix="/predictions", tags=["Predictions"])


@router.post("/evaluate", response_model=SuccessResponse[PredictionResponse])
async def evaluate_ads(
    request: PredictionRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> SuccessResponse[PredictionResponse]:
    """
    Evaluate ad performance for today using the trained ML model.

    This endpoint fetches recent data, builds features, and predicts the probability
    that each ad should be stopped based on ROAS performance.

    Args:
        request: Prediction request with optional ad_account_ids and lookback_days
        user_id: Current user ID from X-User-Id header

    Returns:
        SuccessResponse containing predictions with stop probabilities and features

    Example:
        Request:
        ```json
        {
            "ad_account_ids": ["act_123456789", "act_987654321"],
            "lookback_days": 10
        }
        ```

        Response:
        ```json
        {
            "success": true,
            "data": {
                "predictions": [
                    {
                        "ad_account_name": "My Account",
                        "ad_id": "123456789",
                        "date": "2025-10-27",
                        "pred_proba": 0.75,
                        "features": {
                            "spend_lag1": 100.5,
                            "roas_lag1": 0.45,
                            ...
                        }
                    }
                ],
                "total_records": 10,
                "date_range": {"since": "2025-10-17", "until": "2025-10-27"},
                "evaluation_date": "2025-10-27"
            }
        }
        ```
    """
    try:
        result = await PredictionService.predict_today(
            ad_account_ids=request.ad_account_ids,
            lookback_days=request.lookback_days,
            model_path=request.model_path,
        )

        prediction_data = PredictionResponse(
            predictions=[
                PredictionRecord(
                    ad_account_name=pred["ad_account_name"],
                    ad_id=pred["ad_id"],
                    date=pred["date"],
                    pred_proba=pred["pred_proba"],
                    features=pred["features"],
                )
                for pred in result["predictions"]
            ],
            total_records=result["total_records"],
            date_range=result["date_range"],
            evaluation_date=result["evaluation_date"],
        )

        return SuccessResponse(
            data=prediction_data,
            message=f"Successfully evaluated {result['total_records']} ads",
        )

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to evaluate ads: {str(e)}",
        )


@router.get("/evaluate/{ad_account_id}", response_model=SuccessResponse[PredictionResponse])
async def evaluate_account_ads(
    ad_account_id: Annotated[
        str,
        Path(
            description="Ad account ID (with or without act_ prefix)",
            examples=["act_123456789"],
        ),
    ],
    lookback_days: Annotated[
        int,
        Query(
            description="Number of days to look back for feature calculation",
            ge=7,
            le=30,
        ),
    ] = 10,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[PredictionResponse]:
    """
    Evaluate ad performance for a specific ad account.

    This is a convenience endpoint for evaluating a single account without
    needing to provide a request body.

    Args:
        ad_account_id: Ad account ID to evaluate
        lookback_days: Number of days to look back (default: 10)
        user_id: Current user ID from X-User-Id header

    Returns:
        SuccessResponse containing predictions for the specified account

    Example:
        ```
        GET /predictions/evaluate/act_123456789?lookback_days=10
        ```

        Response:
        ```json
        {
            "success": true,
            "data": {
                "predictions": [...],
                "total_records": 5,
                "date_range": {"since": "2025-10-17", "until": "2025-10-27"},
                "evaluation_date": "2025-10-27"
            }
        }
        ```
    """
    try:
        result = await PredictionService.predict_for_account(
            ad_account_id=ad_account_id,
            lookback_days=lookback_days,
        )

        prediction_data = PredictionResponse(
            predictions=[
                PredictionRecord(
                    ad_account_name=pred["ad_account_name"],
                    ad_id=pred["ad_id"],
                    date=pred["date"],
                    pred_proba=pred["pred_proba"],
                    features=pred["features"],
                )
                for pred in result["predictions"]
            ],
            total_records=result["total_records"],
            date_range=result["date_range"],
            evaluation_date=result["evaluation_date"],
        )

        return SuccessResponse(
            data=prediction_data,
            message=f"Successfully evaluated {result['total_records']} ads for account {ad_account_id}",
        )

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to evaluate ads: {str(e)}",
        )
