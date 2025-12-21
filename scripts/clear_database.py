"""Clear all data from the database.

WARNING: This will delete ALL papers from the database!
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from citeo.config.settings import settings
from citeo.storage import create_storage


async def clear_database():
    """Clear all papers from the database."""
    print("=" * 70)
    print("⚠️  DATABASE CLEANUP")
    print("=" * 70)
    print(f"\nDatabase Type: {settings.db_type}")

    if settings.db_type == "sqlite":
        print(f"Database Path: {settings.db_path}")
    elif settings.db_type == "d1":
        print(f"D1 Account ID: {settings.d1_account_id}")
        print(f"D1 Database ID: {settings.d1_database_id}")

    print("\n⚠️  WARNING: This will delete ALL papers from the database!")
    response = input("\nAre you sure you want to continue? (yes/no): ")

    if response.lower() != "yes":
        print("\n❌ Operation cancelled.")
        return False

    print("\n🗑️  Clearing database...")

    storage = create_storage(settings)
    await storage.initialize()

    # Execute DELETE statement
    if settings.db_type == "sqlite":
        import aiosqlite

        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute("DELETE FROM papers")
            await db.commit()
            cursor = await db.execute("SELECT COUNT(*) FROM papers")
            count = (await cursor.fetchone())[0]
            print(f"✅ Database cleared. Remaining papers: {count}")
    elif settings.db_type == "d1":
        from citeo.storage.d1 import D1PaperStorage

        if isinstance(storage, D1PaperStorage):
            result = await storage._execute("DELETE FROM papers")
            print("✅ Database cleared")

            # Verify
            count_result = await storage._execute("SELECT COUNT(*) as count FROM papers")
            count = count_result.get("results", [{}])[0].get("count", 0)
            print(f"   Remaining papers: {count}")

    await storage.close()

    print("\n" + "=" * 70)
    print("✅ Database cleanup completed!")
    print("=" * 70)

    return True


if __name__ == "__main__":
    result = asyncio.run(clear_database())
    sys.exit(0 if result else 1)
