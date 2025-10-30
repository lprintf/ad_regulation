"""
List ad accounts in database
"""
import asyncio
from utils.db import init_db, close_db, ADAccountDocument


async def list_ad_accounts():
    """List all ad accounts in database"""
    await init_db()
    print("✓ Database initialized\n")

    try:
        accounts = await ADAccountDocument.find_all().to_list()

        if not accounts:
            print("❌ No ad accounts found in database")
            print("\nPlease ensure ad account credentials are properly configured in MongoDB.")
            print("Check ADAccountDocument and FbAppAuthDocument collections.")
        else:
            print(f"Found {len(accounts)} ad account(s):\n")
            for acc in accounts:
                print(f"  ID: {acc.id}")
                print(f"  Name: {acc.name}")
                print(f"  Has Auth: {acc.fb_app_auth is not None}")
                print("-" * 60)

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        await close_db()
        print("\n✓ Database connection closed")


if __name__ == "__main__":
    asyncio.run(list_ad_accounts())
