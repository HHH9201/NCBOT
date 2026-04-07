
import asyncio
import os
from common.db_permissions import db_permission_manager

async def test_search():
    print("Initializing DB...")
    await db_permission_manager.initialize()
    print("Searching for '只狼'...")
    results = await db_permission_manager.search_game_resources("只狼")
    print(f"Found {len(results)} results:")
    for res in results:
        print(f"- {res.get('zh_name')} ({res.get('en_name')})")
        print(f"  Baidu: {res.get('baidu_url')}")
        print(f"  Quark: {res.get('quark_url')}")

if __name__ == "__main__":
    asyncio.run(test_search())
