"""
Check if specific ad account exists in database
"""
import asyncio
from utils.db import init_db, close_db, ADAccountDocument


async def check_account():
    """Check if ad account exists"""
    await init_db()
    print("✓ Database initialized\n")

    # The account ID from the notebook
    account_id = "act_1279567647104057"

    try:
        account = await ADAccountDocument.find_one(
            ADAccountDocument.id == account_id, fetch_links=True
        )

        if account:
            print(f"✓ Found account:")
            print(f"  ID: {account.id}")
            print(f"  Name: {account.name}")
            print(f"  Has Auth: {account.fb_app_auth is not None}")
            if account.fb_app_auth:
                print(f"  App ID: {account.fb_app_auth.app_id}")
                print(f"  User ID: {account.fb_app_auth.user_id}")
        else:
            print(f"❌ Account {account_id} NOT found in database")
            print("\nTrying without act_ prefix...")
            account_id_no_prefix = account_id.replace("act_", "")
            account = await ADAccountDocument.find_one(
                ADAccountDocument.id == account_id_no_prefix, fetch_links=True
            )
            if account:
                print(f"✓ Found account with ID: {account.id}")
            else:
                print(f"❌ Account {account_id_no_prefix} also not found")

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        await close_db()
        print("\n✓ Database connection closed")


if __name__ == "__main__":
    asyncio.run(check_account())
