"""
Unified Facebook Ad Account ID utilities.

Facebook ad account IDs can appear in two formats:
- With prefix: "act_123456789"
- Without prefix: "123456789"

This module provides utilities to normalize and convert between formats.
"""


def normalize_account_id(account_id: str | None) -> str:
    """
    Normalize ad account ID to include act_ prefix (Facebook SDK format).

    Args:
        account_id: Raw account ID (with or without act_ prefix)

    Returns:
        Normalized account ID with act_ prefix

    Raises:
        ValueError: If account_id is None or empty

    Examples:
        >>> normalize_account_id("123456")
        "act_123456"
        >>> normalize_account_id("act_123456")
        "act_123456"
    """
    if not account_id:
        raise ValueError("account_id cannot be None or empty")

    stripped = account_id.strip()
    if not stripped:
        raise ValueError("account_id cannot be blank")

    # Already has prefix
    if stripped.startswith("act_"):
        return stripped

    # Remove any stray "act_" at the start and re-add it properly
    # This handles cases like "act_act_123" -> "act_123"
    cleaned = stripped.lstrip("act_")
    return f"act_{cleaned}"


def remove_account_id_prefix(account_id: str | None) -> str:
    """
    Remove act_ prefix from account ID (database storage format).

    Args:
        account_id: Account ID (with or without act_ prefix)

    Returns:
        Account ID without act_ prefix

    Raises:
        ValueError: If account_id is None or empty

    Examples:
        >>> remove_account_id_prefix("act_123456")
        "123456"
        >>> remove_account_id_prefix("123456")
        "123456"
    """
    if not account_id:
        raise ValueError("account_id cannot be None or empty")

    stripped = account_id.strip()
    if not stripped:
        raise ValueError("account_id cannot be blank")

    if stripped.startswith("act_"):
        return stripped[4:]  # Remove "act_" (4 characters)

    return stripped


def has_account_id_prefix(account_id: str | None) -> bool:
    """
    Check if account ID has act_ prefix.

    Args:
        account_id: Account ID to check

    Returns:
        True if account ID starts with act_, False otherwise

    Examples:
        >>> has_account_id_prefix("act_123456")
        True
        >>> has_account_id_prefix("123456")
        False
    """
    if not account_id:
        return False

    return account_id.strip().startswith("act_")
