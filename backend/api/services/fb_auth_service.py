"""
Service utilities for Facebook app authentication management.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from facebook_business.adobjects.systemuser import SystemUser
from facebook_business.adobjects.user import User
from facebook_business.api import FacebookAdsApi
from facebook_business.exceptions import FacebookRequestError
from fastapi.concurrency import run_in_threadpool

from api.models.fb_auth import FbAdAccountModel, FbAppAuthSyncResult
from utils.account_id import normalize_account_id
from utils.db import ADAccountDocument, FbAppAuthDocument, FbAppTokenInfoDocument
from utils.schemas.ad_account import FbAppSeedInfo, FbAppTokenInfo


class FacebookAuthError(Exception):
    """Domain specific error while handling Facebook authentication."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass
class _TokenSyncPayload:
    token_info: dict[str, Any]
    accounts: list[dict[str, str]]
    user_name: str | None


def _filter_token_info_fields(raw_info: dict[str, Any]) -> dict[str, Any]:
    """
    Filter token info payload to match the FbAppTokenInfo schema.
    """

    allowed_fields = set(FbAppTokenInfo.model_fields.keys())
    return {field: value for field, value in raw_info.items() if field in allowed_fields}


def _ts_to_datetime(ts: int | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _last4(token: str | None) -> str | None:
    if not token:
        return None
    return token[-4:]


def _as_utc(dt: datetime | None) -> datetime | None:
    if not dt:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=timezone.utc)


def _fetch_user_name(
    api: FacebookAdsApi, token_type: str | None, user_id: str | None
) -> str | None:
    if not user_id:
        return None
    try:
        if token_type == "USER":
            profile = User("me", api=api).api_get(fields=["name"])
        elif token_type == "SYSTEM_USER":
            profile = SystemUser(user_id, api=api).api_get(fields=["name"])
        else:
            return None
        return profile.get("name")
    except FacebookRequestError:
        return None


def _fetch_token_info_and_accounts(seed_info: FbAppSeedInfo) -> _TokenSyncPayload:
    try:
        api = FacebookAdsApi.init(
            app_id=seed_info.app_id,
            app_secret=seed_info.app_secret,
            access_token=seed_info.access_token,
        )
        params = {
            "input_token": seed_info.access_token,
            "access_token": f"{seed_info.app_id}|{seed_info.app_secret}",
        }
        response = api.call("GET", ("debug_token",), params=params)
        payload = response.json() or {}
        token_info = payload.get("data")
        if not token_info:
            raise FacebookAuthError(
                "Facebook debug_token response missing data section",
                code="DEBUG_TOKEN_EMPTY",
            )
    except (
        FacebookRequestError
    ) as exc:  # pragma: no cover - exercised via tests with mocking
        raise FacebookAuthError(
            "Facebook API rejected the provided credentials",
            code=str(exc.api_error_code()) if exc.api_error_code() else None,
            details={
                "message": exc.api_error_message(),
                "type": exc.api_error_type(),
            },
        ) from exc
    print
    token_type: str | None = token_info.get("type")
    user_id = token_info.get("user_id")
    if not user_id:
        print(
            "[WARNING] Failed to retrieve user ID from Facebook token",
            token_info,
        )
        raise FacebookAuthError(
            "debug_token response does not contain user_id",
            code="DEBUG_TOKEN_NO_USER",
        )

    if str(token_info.get("app_id")) != seed_info.app_id:
        raise FacebookAuthError(
            "debug_token app_id does not match provided app_id",
            code="DEBUG_TOKEN_APP_ID_MISMATCH",
        )

    accounts_cursor: Iterable[dict[str, Any]] = []
    if token_type == "USER":
        accounts_cursor = User("me", api=api).get_ad_accounts(fields=["id", "name"])
    elif token_type == "SYSTEM_USER":
        accounts_cursor = SystemUser(user_id, api=api).get_assigned_ad_accounts(
            fields=["id", "name"]
        )

    accounts: list[dict[str, str]] = []
    for account in accounts_cursor:
        account_id = account.get("id")
        if not account_id:
            continue
        accounts.append(
            {
                "id": normalize_account_id(str(account_id)),
                "name": account.get("name") or str(account_id),
            }
        )

    user_name = _fetch_user_name(api, token_type, user_id)

    return _TokenSyncPayload(
        token_info=token_info, accounts=accounts, user_name=user_name
    )


def _should_extend_token_expiry(
    expires_at: int | None,
    *,
    threshold: timedelta = timedelta(days=30),
    reference: datetime | None = None,
) -> bool:
    """
    Determine whether the token expiry should be extended (<= threshold remaining).
    """

    if not expires_at:
        return False

    reference_ts = reference or datetime.now(tz=timezone.utc)
    expires_at_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
    return expires_at_dt - reference_ts <= threshold


def _exchange_access_token(
    app_id: str,
    app_secret: str,
    current_token: str,
    *,
    extend_expiry: bool,
) -> dict[str, Any]:
    """
    Exchange a Facebook access token for a new long-lived token via the SDK.
    """

    try:
        api = FacebookAdsApi.init(
            app_id=app_id,
            app_secret=app_secret,
            access_token=current_token,
        )
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": current_token,
        }
        if extend_expiry:
            params["set_token_expires_in_60_days"] = "true"

        response = api.call("GET", ("oauth", "access_token"), params=params)
        exchange_payload = response.json() or {}
    except FacebookRequestError as exc:  # pragma: no cover - network error via SDK
        raise FacebookAuthError(
            "Facebook token exchange failed",
            code=str(exc.api_error_code()) if exc.api_error_code() else None,
            details={
                "message": exc.api_error_message(),
                "type": exc.api_error_type(),
            },
        ) from exc

    if "access_token" not in exchange_payload:
        raise FacebookAuthError(
            "Facebook token exchange response missing access_token",
            code="TOKEN_EXCHANGE_EMPTY",
            details={"response": exchange_payload},
        )

    return exchange_payload


async def sync_fb_app_credentials(
    seed_info: FbAppSeedInfo,
    *,
    triggered_by: str | None = None,
) -> FbAppAuthSyncResult:
    """
    Validate credentials via Facebook API, persist token + auth state, and refresh ad accounts.
    """

    payload = await run_in_threadpool(_fetch_token_info_and_accounts, seed_info)
    token_info = payload.token_info
    filtered_token_info = _filter_token_info_fields(token_info)

    # Persist raw token info
    token_doc = await FbAppTokenInfoDocument.find_one(
        {"app_id": token_info["app_id"], "user_id": token_info["user_id"]}
    )

    now = datetime.utcnow()
    if token_doc:
        for field, value in filtered_token_info.items():
            setattr(token_doc, field, value)
        token_doc.fetched_at = now
        await token_doc.save()
    else:
        token_doc = FbAppTokenInfoDocument(**filtered_token_info, fetched_at=now)
        await token_doc.insert()

    # Persist auth credentials (app secret & token)
    auth_doc = await FbAppAuthDocument.find_one(
        {"app_id": seed_info.app_id, "user_id": token_info["user_id"]}
    )

    if auth_doc:
        auth_doc.app_secret = seed_info.app_secret
        auth_doc.access_token = seed_info.access_token
        auth_doc.type = token_info.get("type")
        auth_doc.last_synced_at = now
        auth_doc.last_synced_by = triggered_by
        auth_doc.user_name = payload.user_name
        await auth_doc.save()
    else:
        auth_doc = FbAppAuthDocument(
            app_id=seed_info.app_id,
            app_secret=seed_info.app_secret,
            access_token=seed_info.access_token,
            user_id=token_info["user_id"],
            type=token_info.get("type"),
            last_synced_at=now,
            last_synced_by=triggered_by,
            user_name=payload.user_name,
        )
        await auth_doc.insert()

    # Sync ad accounts discovered for token
    account_documents: list[ADAccountDocument] = []
    for raw_account in payload.accounts:
        existing_account = await ADAccountDocument.find_one(
            ADAccountDocument.id == raw_account["id"], fetch_links=False
        )
        if existing_account:
            existing_account.name = raw_account["name"]
            existing_account.fb_app_auth = auth_doc
            await existing_account.save()
            account_documents.append(existing_account)
        else:
            new_doc = ADAccountDocument(
                id=raw_account["id"],
                name=raw_account["name"],
                fb_app_auth=auth_doc,
            )
            await new_doc.insert()
            account_documents.append(new_doc)

    return FbAppAuthSyncResult(
        app_id=auth_doc.app_id,
        user_id=auth_doc.user_id,
        type=auth_doc.type,
        application=token_info.get("application"),
        is_valid=token_info.get("is_valid"),
        expires_at=_ts_to_datetime(token_info.get("expires_at")),
        data_access_expires_at=_ts_to_datetime(
            token_info.get("data_access_expires_at")
        ),
        scopes=token_info.get("scopes") or [],
        granular_scopes=token_info.get("granular_scopes") or [],
        accounts=[
            FbAdAccountModel(id=acc.id, name=acc.name) for acc in account_documents
        ],
        last_synced_at=_as_utc(auth_doc.last_synced_at),
        last_synced_by=auth_doc.last_synced_by,
        access_token_last4=_last4(auth_doc.access_token),
        user_name=auth_doc.user_name,
    )


async def refresh_fb_app_token(
    app_id: str,
    user_id: str,
    *,
    triggered_by: str | None = None,
) -> FbAppAuthSyncResult:
    """
    Refresh a stored Facebook app token and optionally extend its expiry when nearing expiration.
    """

    auth_doc = await FbAppAuthDocument.find_one(
        {"app_id": app_id, "user_id": user_id}
    )
    if not auth_doc:
        raise FacebookAuthError(
            "Facebook app credentials not found for refresh request",
            code="TOKEN_NOT_FOUND",
            details={"app_id": app_id, "user_id": user_id},
        )

    if not auth_doc.access_token:
        raise FacebookAuthError(
            "Stored Facebook app credentials miss access_token",
            code="TOKEN_MISSING",
            details={"app_id": app_id, "user_id": user_id},
        )

    token_doc = await FbAppTokenInfoDocument.find_one(
        {"app_id": app_id, "user_id": user_id}
    )
    expires_at = token_doc.expires_at if token_doc else None
    extend_expiry = _should_extend_token_expiry(
        expires_at,
        reference=datetime.now(tz=timezone.utc),
    )

    # Log refresh attempt details
    import logging
    logger = logging.getLogger(__name__)
    if expires_at:
        old_expires_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
        logger.info(
            f"Token refresh: app_id={app_id}, user_id={user_id}, "
            f"old_expires_at={old_expires_dt}, extend_expiry={extend_expiry}"
        )

    exchange_payload = await run_in_threadpool(
        _exchange_access_token,
        auth_doc.app_id,
        auth_doc.app_secret,
        auth_doc.access_token,
        extend_expiry=extend_expiry,
    )

    refreshed_token = exchange_payload["access_token"]

    # Log exchange response
    logger.info(f"Token exchange response: {exchange_payload}")
    logger.info(
        f"Token changed: {auth_doc.access_token[-4:] if auth_doc.access_token else 'N/A'} -> {refreshed_token[-4:]}"
    )

    # Persist the refreshed token and re-sync related metadata.
    seed_info = FbAppSeedInfo(
        app_id=auth_doc.app_id,
        app_secret=auth_doc.app_secret,
        access_token=refreshed_token,
    )

    result = await sync_fb_app_credentials(seed_info, triggered_by=triggered_by)

    # Log new expiry after sync
    if result.expires_at:
        logger.info(
            f"Token refresh completed: new_expires_at={result.expires_at}, "
            f"token_changed={auth_doc.access_token[-4:] if auth_doc.access_token else 'N/A'} != {refreshed_token[-4:]}"
        )

    return result


async def resync_fb_app_accounts(
    app_id: str,
    user_id: str,
    *,
    triggered_by: str | None = None,
) -> FbAppAuthSyncResult:
    """
    Re-sync Facebook token metadata and ad accounts using the stored credentials.
    """

    auth_doc = await FbAppAuthDocument.find_one(
        {"app_id": app_id, "user_id": user_id}
    )
    if not auth_doc:
        raise FacebookAuthError(
            "Facebook app credentials not found for re-sync request",
            code="TOKEN_NOT_FOUND",
            details={"app_id": app_id, "user_id": user_id},
        )

    if not auth_doc.access_token:
        raise FacebookAuthError(
            "Stored Facebook app credentials miss access_token",
            code="TOKEN_MISSING",
            details={"app_id": app_id, "user_id": user_id},
        )

    seed_info = FbAppSeedInfo(
        app_id=auth_doc.app_id,
        app_secret=auth_doc.app_secret,
        access_token=auth_doc.access_token,
    )

    return await sync_fb_app_credentials(seed_info, triggered_by=triggered_by)


async def list_fb_app_credentials() -> list[FbAppAuthSyncResult]:
    """
    Collect stored Facebook auth records and join with cached token info + accounts.
    """

    auth_documents = await FbAppAuthDocument.find_all().to_list()
    token_documents = await FbAppTokenInfoDocument.find_all().to_list()
    token_index = {
        (token.app_id, token.user_id): token
        for token in token_documents
        if token.user_id
    }

    account_documents = await ADAccountDocument.find(fetch_links=True).to_list()
    account_index: dict[tuple[str, str], list[ADAccountDocument]] = {}
    for account in account_documents:
        fb_auth = account.fb_app_auth
        if not fb_auth:
            continue
        key = (fb_auth.app_id, fb_auth.user_id)
        account_index.setdefault(key, []).append(account)

    results: list[FbAppAuthSyncResult] = []
    for auth_doc in auth_documents:
        token_doc = token_index.get((auth_doc.app_id, auth_doc.user_id))
        token_payload = token_doc.model_dump() if token_doc else {}

        results.append(
            FbAppAuthSyncResult(
                app_id=auth_doc.app_id,
                user_id=auth_doc.user_id,
                type=auth_doc.type,
                application=token_payload.get("application"),
                is_valid=token_payload.get("is_valid"),
                expires_at=_ts_to_datetime(token_payload.get("expires_at")),
                data_access_expires_at=_ts_to_datetime(
                    token_payload.get("data_access_expires_at")
                ),
                scopes=token_payload.get("scopes") or [],
                granular_scopes=token_payload.get("granular_scopes") or [],
                accounts=[
                    FbAdAccountModel(id=account.id, name=account.name)
                    for account in account_index.get(
                        (auth_doc.app_id, auth_doc.user_id), []
                    )
                ],
                last_synced_at=_as_utc(auth_doc.last_synced_at)
                or datetime.now(tz=timezone.utc),
                last_synced_by=auth_doc.last_synced_by,
                access_token_last4=_last4(auth_doc.access_token),
                user_name=auth_doc.user_name,
            )
        )

    return results
