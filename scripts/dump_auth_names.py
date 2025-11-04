import asyncio

from utils.db import init_db, close_db, FbAppAuthDocument


async def main():
    await init_db()
    docs = await FbAppAuthDocument.find_all().to_list()
    for doc in docs:
        print(doc.app_id, doc.user_id, doc.user_name)
    await close_db()


if __name__ == '__main__':
    asyncio.run(main())

