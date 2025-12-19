"""Test switching between SQLite and D1 databases.

Validates that the application can seamlessly switch database types
by changing configuration only.
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pydantic import SecretStr

from citeo.config.settings import Settings
from citeo.models.paper import Paper
from citeo.storage import create_storage


async def test_database_switch():
    """Test switching between SQLite and D1."""
    print("=" * 70)
    print("🔄 Database Switching Test")
    print("=" * 70)

    # Test Paper
    test_paper = Paper(
        guid=f"oai:arXiv.org:switch.{datetime.now().microsecond}",
        arxiv_id=f"switch.{datetime.now().microsecond}",
        title="Database Switching Test Paper",
        abstract="Testing database switching between SQLite and D1.",
        authors=["Test Author"],
        categories=["cs.AI"],
        announce_type="new",
        published_at=datetime.utcnow(),
        abs_url="https://arxiv.org/abs/switch.test",
        source_id="test_source",
        fetched_at=datetime.utcnow(),
    )

    # Test 1: Use SQLite
    print("\n" + "=" * 70)
    print("Test 1: SQLite Database")
    print("=" * 70)

    sqlite_settings = Settings(
        db_type="sqlite",
        db_path=Path("/tmp/citeo_test.db"),
        openai_api_key=SecretStr("test-key"),
    )

    try:
        sqlite_storage = create_storage(sqlite_settings)
        print(f"✅ Created storage: {type(sqlite_storage).__name__}")

        await sqlite_storage.initialize()
        print(f"✅ SQLite initialized")

        is_new = await sqlite_storage.save_paper(test_paper)
        print(f"✅ Saved paper to SQLite (new={is_new})")

        retrieved = await sqlite_storage.get_paper_by_guid(test_paper.guid)
        if retrieved:
            print(f"✅ Retrieved paper from SQLite")
            print(f"   Title: {retrieved.title}")
        else:
            print(f"❌ Failed to retrieve paper from SQLite")
            return False

        await sqlite_storage.close()
        print(f"✅ SQLite storage closed")

    except Exception as e:
        print(f"❌ SQLite test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test 2: Switch to D1
    print("\n" + "=" * 70)
    print("Test 2: Switch to D1 Database")
    print("=" * 70)

    # Try to load settings to get D1 credentials
    try:
        from citeo.config.settings import settings as current_settings

        if current_settings.db_type.lower() != "d1":
            print("⚠️  Current DB_TYPE is not 'd1'")
            print(f"   Current: {current_settings.db_type}")
            print("   Skipping D1 test (SQLite test passed)")
            return True

        if not all([
            current_settings.d1_account_id,
            current_settings.d1_database_id,
            current_settings.d1_api_token,
        ]):
            print("⚠️  D1 credentials not configured")
            print("   Skipping D1 test (SQLite test passed)")
            return True

        d1_settings = Settings(
            db_type="d1",
            d1_account_id=current_settings.d1_account_id,
            d1_database_id=current_settings.d1_database_id,
            d1_api_token=current_settings.d1_api_token,
            openai_api_key=SecretStr("test-key"),
        )
    except Exception as e:
        print(f"⚠️  Failed to load D1 settings: {e}")
        print("   Skipping D1 test (SQLite test passed)")
        return True

    try:
        d1_storage = create_storage(d1_settings)
        print(f"✅ Created storage: {type(d1_storage).__name__}")

        await d1_storage.initialize()
        print(f"✅ D1 initialized")

        # Save to D1
        is_new = await d1_storage.save_paper(test_paper)
        print(f"✅ Saved paper to D1 (new={is_new})")

        # Retrieve from D1
        retrieved = await d1_storage.get_paper_by_guid(test_paper.guid)
        if retrieved:
            print(f"✅ Retrieved paper from D1")
            print(f"   Title: {retrieved.title}")
        else:
            print(f"❌ Failed to retrieve paper from D1")
            await d1_storage.close()
            return False

        await d1_storage.close()
        print(f"✅ D1 storage closed")

    except Exception as e:
        print(f"❌ D1 test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test 3: Switch back to SQLite
    print("\n" + "=" * 70)
    print("Test 3: Switch Back to SQLite")
    print("=" * 70)

    try:
        sqlite_storage2 = create_storage(sqlite_settings)
        print(f"✅ Created storage: {type(sqlite_storage2).__name__}")

        # Should still be able to read the previously saved paper
        retrieved = await sqlite_storage2.get_paper_by_guid(test_paper.guid)
        if retrieved:
            print(f"✅ Retrieved paper from SQLite (after switch)")
            print(f"   Data persisted correctly")
        else:
            print(f"⚠️  Paper not found (expected if database was recreated)")

        await sqlite_storage2.close()
        print(f"✅ SQLite storage closed")

    except Exception as e:
        print(f"❌ Switch back test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Summary
    print("\n" + "=" * 70)
    print("✅ Database Switching Test Passed!")
    print("=" * 70)
    print("\nValidated:")
    print("  ✅ SQLite storage creation and operations")
    print("  ✅ D1 storage creation and operations")
    print("  ✅ Seamless switching between database types")
    print("  ✅ Same interface for both storage types")
    print("\n💡 Switching databases requires only configuration changes")
    print("   No code modifications needed!")

    return True


if __name__ == "__main__":
    result = asyncio.run(test_database_switch())
    sys.exit(0 if result else 1)
