"""
Error handling decorators for API services

Provides decorators to standardize error handling across service methods,
particularly for Facebook API errors.
"""

from functools import wraps
from typing import Any, Callable, TypeVar
from facebook_business.exceptions import FacebookRequestError

T = TypeVar('T')


def handle_facebook_api_errors(operation_name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to handle Facebook API errors consistently.

    This decorator wraps async service methods and provides standardized error handling
    for Facebook API errors. It catches FacebookRequestError and other exceptions,
    then re-raises them as ValueError with a formatted message.

    Args:
        operation_name: Human-readable name for the operation (e.g., "get ad status", "start ad")

    Returns:
        Decorator function that wraps the service method

    Example:
        ```python
        @handle_facebook_api_errors("get ad status")
        async def get_ad_status(ad_account_id: str, ad_id: str) -> dict[str, Any]:
            # Method implementation
            pass
        ```

    Error Handling:
        - FacebookRequestError: Extracts API error message and re-raises as ValueError
        - Other exceptions: Re-raises as ValueError with operation context
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return await func(*args, **kwargs)
            except FacebookRequestError as e:
                error_message = e.api_error_message() if hasattr(e, 'api_error_message') else str(e)
                raise ValueError(f"Facebook API error: {error_message}") from e
            except Exception as e:
                raise ValueError(f"Failed to {operation_name}: {str(e)}") from e

        return wrapper

    return decorator


def handle_api_errors(operation_name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to handle general API errors.

    Similar to handle_facebook_api_errors but without Facebook-specific error handling.
    Useful for non-Facebook API operations that still need standardized error handling.

    Args:
        operation_name: Human-readable name for the operation

    Returns:
        Decorator function that wraps the service method

    Example:
        ```python
        @handle_api_errors("query insights")
        async def query_insights(params: dict) -> dict[str, Any]:
            # Method implementation
            pass
        ```
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                raise ValueError(f"Failed to {operation_name}: {str(e)}") from e

        return wrapper

    return decorator
