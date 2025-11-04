"""
Utility script to backfill Facebook auth user names.

Usage:
    python scripts/update_fb_auth_user_names.py
"""

import asyncio

from facebook_business.api import FacebookAdsApi
from facebook_business.exceptions import FacebookRequestError

from utils.db import FbAppAuthDocument, init_db, close_db
from api.services.fb_auth_service import _fetch_user_name


async def update_user_names(verbose: bool = True) -> None:
    await init_db()
    updated = 0
    total = 0

    auth_docs = await FbAppAuthDocument.find_all().to_list()
    total = len(auth_docs)

    for auth in auth_docs:
        label = f"{auth.app_id}:{auth.user_id}"
        if verbose:
            print(f"[{label}] Fetching user name...", end=" ")

        try:
            api = FacebookAdsApi.init(
                app_id=auth.app_id,
                app_secret=auth.app_secret,
                access_token=auth.access_token,
            )
            user_name = _fetch_user_name(api, auth.type, auth.user_id)
        except FacebookRequestError as exc:  # pragma: no cover - network path
            if verbose:
                print(f"failed: {exc.api_error_message()} (code={exc.api_error_code()})")
            continue

        if user_name:
            if user_name != auth.user_name:
                auth.user_name = user_name
                await auth.save()
                updated += 1
                if verbose:
                    print(f"updated to '{user_name}'")
            else:
                if verbose:
                    print(f"unchanged '{user_name}'")
        else:
            if verbose:
                print("no name returned; token may lack required permissions or is invalid.")

    await close_db()
    print(f"Processed {total} records. Updated {updated} user names.")


if __name__ == "__main__":
    asyncio.run(update_user_names())
