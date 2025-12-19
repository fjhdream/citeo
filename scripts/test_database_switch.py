"""Test script to verify database factory and configuration switching.

Tests SQLite and D1 storage creation with various configurations.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pydantic import SecretStr

from citeo.config.settings import Settings
from citeo.storage import D1PaperStorage, SQLitePaperStorage, create_storage


def test_sqlite_storage():
    """Test SQLite storage creation."""
    print("=" * 60)
    print("Test 1: SQLite Storage")
    print("=" * 60)

    settings = Settings(
        db_type="sqlite",
        db_path=Path("data/test.db"),
        openai_api_key=SecretStr("test-key"),
    )

    try:
        storage = create_storage(settings)
        assert isinstance(storage, SQLitePaperStorage), f"Expected SQLitePaperStorage, got {type(storage)}"
        print("✅ SQLite storage created successfully")
        print(f"   Type: {type(storage).__name__}")
        return True
    except Exception as e:
        print(f"❌ SQLite storage creation failed: {e}")
        return False


def test_d1_storage_valid():
    """Test D1 storage creation with valid config."""
    print("\n" + "=" * 60)
    print("Test 2: D1 Storage (Valid Config)")
    print("=" * 60)

    settings = Settings(
        db_type="d1",
        d1_account_id="test-account-id",
        d1_database_id="test-database-id",
        d1_api_token=SecretStr("test-api-token"),
        openai_api_key=SecretStr("test-key"),
    )

    try:
        storage = create_storage(settings)
        assert isinstance(storage, D1PaperStorage), f"Expected D1PaperStorage, got {type(storage)}"
        print("✅ D1 storage created successfully")
        print(f"   Type: {type(storage).__name__}")
        return True
    except Exception as e:
        print(f"❌ D1 storage creation failed: {e}")
        return False


def test_d1_storage_missing_account_id():
    """Test D1 storage creation with missing account ID."""
    print("\n" + "=" * 60)
    print("Test 3: D1 Storage (Missing Account ID)")
    print("=" * 60)

    settings = Settings(
        db_type="d1",
        d1_database_id="test-database-id",
        d1_api_token=SecretStr("test-api-token"),
        openai_api_key=SecretStr("test-key"),
    )

    try:
        storage = create_storage(settings)
        print(f"❌ Should have raised ValueError, but got: {type(storage).__name__}")
        return False
    except ValueError as e:
        print(f"✅ Correctly raised ValueError: {e}")
        return True
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_d1_storage_missing_database_id():
    """Test D1 storage creation with missing database ID."""
    print("\n" + "=" * 60)
    print("Test 4: D1 Storage (Missing Database ID)")
    print("=" * 60)

    settings = Settings(
        db_type="d1",
        d1_account_id="test-account-id",
        d1_api_token=SecretStr("test-api-token"),
        openai_api_key=SecretStr("test-key"),
    )

    try:
        storage = create_storage(settings)
        print(f"❌ Should have raised ValueError, but got: {type(storage).__name__}")
        return False
    except ValueError as e:
        print(f"✅ Correctly raised ValueError: {e}")
        return True
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_d1_storage_missing_api_token():
    """Test D1 storage creation with missing API token."""
    print("\n" + "=" * 60)
    print("Test 5: D1 Storage (Missing API Token)")
    print("=" * 60)

    settings = Settings(
        db_type="d1",
        d1_account_id="test-account-id",
        d1_database_id="test-database-id",
        openai_api_key=SecretStr("test-key"),
    )

    try:
        storage = create_storage(settings)
        print(f"❌ Should have raised ValueError, but got: {type(storage).__name__}")
        return False
    except ValueError as e:
        print(f"✅ Correctly raised ValueError: {e}")
        return True
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_unsupported_db_type():
    """Test creation with unsupported database type."""
    print("\n" + "=" * 60)
    print("Test 6: Unsupported Database Type")
    print("=" * 60)

    settings = Settings(
        db_type="postgresql",
        openai_api_key=SecretStr("test-key"),
    )

    try:
        storage = create_storage(settings)
        print(f"❌ Should have raised ValueError, but got: {type(storage).__name__}")
        return False
    except ValueError as e:
        print(f"✅ Correctly raised ValueError: {e}")
        return True
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "🧪 Database Factory Test Suite" + "\n")

    results = []
    results.append(("SQLite Storage", test_sqlite_storage()))
    results.append(("D1 Storage (Valid)", test_d1_storage_valid()))
    results.append(("D1 Missing Account ID", test_d1_storage_missing_account_id()))
    results.append(("D1 Missing Database ID", test_d1_storage_missing_database_id()))
    results.append(("D1 Missing API Token", test_d1_storage_missing_api_token()))
    results.append(("Unsupported DB Type", test_unsupported_db_type()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
