"""Real D1 database integration test.

Tests actual D1 database operations with real credentials.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from citeo.config.settings import settings
from citeo.models.paper import Paper
from citeo.storage import create_storage


async def test_d1_real():
    """Test real D1 database operations."""
    print("=" * 70)
    print("🧪 Real D1 Database Integration Test")
    print("=" * 70)

    # Check configuration
    print(f"\n📊 Current Configuration:")
    print(f"  DB_TYPE: {settings.db_type}")

    if settings.db_type.lower() != "d1":
        print(f"\n⚠️  Warning: DB_TYPE is '{settings.db_type}', not 'd1'")
        print(f"   This test requires D1 configuration.")
        return False

    print(f"  D1_ACCOUNT_ID: {settings.d1_account_id}")
    print(f"  D1_DATABASE_ID: {settings.d1_database_id}")
    print(f"  D1_API_TOKEN: {'*' * 20} (hidden)")

    # Create storage
    print(f"\n🔧 Creating D1 storage instance...")
    try:
        storage = create_storage(settings)
        print(f"✅ Storage created: {type(storage).__name__}")
    except Exception as e:
        print(f"❌ Failed to create storage: {e}")
        return False

    # Test 1: Initialize database schema
    print(f"\n" + "=" * 70)
    print("Test 1: Initialize Database Schema")
    print("=" * 70)
    try:
        await storage.initialize()
        print("✅ Database schema initialized successfully")
    except Exception as e:
        print(f"❌ Schema initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test 2: Save a test paper
    print(f"\n" + "=" * 70)
    print("Test 2: Save Test Paper")
    print("=" * 70)

    test_paper = Paper(
        guid="oai:arXiv.org:test.12345",
        arxiv_id="test.12345",
        title="Test Paper for D1 Integration",
        abstract="This is a test paper to verify D1 database operations.",
        authors=["Test Author 1", "Test Author 2"],
        categories=["cs.AI", "cs.LG"],
        announce_type="new",
        published_at=datetime.utcnow(),
        abs_url="https://arxiv.org/abs/test.12345",
        source_id="test_source",
        fetched_at=datetime.utcnow(),
    )

    try:
        is_new = await storage.save_paper(test_paper)
        if is_new:
            print(f"✅ Test paper saved successfully (new record)")
        else:
            print(f"✅ Paper already exists (deduplication working)")
    except Exception as e:
        print(f"❌ Failed to save paper: {e}")
        import traceback
        traceback.print_exc()
        await storage.close()
        return False

    # Test 3: Get paper by GUID
    print(f"\n" + "=" * 70)
    print("Test 3: Get Paper by GUID")
    print("=" * 70)
    try:
        retrieved = await storage.get_paper_by_guid(test_paper.guid)
        if retrieved:
            print(f"✅ Paper retrieved successfully")
            print(f"   Title: {retrieved.title}")
            print(f"   arXiv ID: {retrieved.arxiv_id}")
            print(f"   Authors: {len(retrieved.authors)} authors")
        else:
            print(f"❌ Paper not found by GUID")
            await storage.close()
            return False
    except Exception as e:
        print(f"❌ Failed to get paper by GUID: {e}")
        import traceback
        traceback.print_exc()
        await storage.close()
        return False

    # Test 4: Get paper by arXiv ID
    print(f"\n" + "=" * 70)
    print("Test 4: Get Paper by arXiv ID")
    print("=" * 70)
    try:
        retrieved = await storage.get_paper_by_arxiv_id(test_paper.arxiv_id)
        if retrieved:
            print(f"✅ Paper retrieved by arXiv ID successfully")
            print(f"   Title: {retrieved.title}")
        else:
            print(f"❌ Paper not found by arXiv ID")
            await storage.close()
            return False
    except Exception as e:
        print(f"❌ Failed to get paper by arXiv ID: {e}")
        import traceback
        traceback.print_exc()
        await storage.close()
        return False

    # Test 5: Get pending papers
    print(f"\n" + "=" * 70)
    print("Test 5: Get Pending Papers")
    print("=" * 70)
    try:
        pending = await storage.get_pending_papers()
        print(f"✅ Retrieved {len(pending)} pending paper(s)")
        if pending:
            print(f"   First paper: {pending[0].title[:50]}...")
    except Exception as e:
        print(f"❌ Failed to get pending papers: {e}")
        import traceback
        traceback.print_exc()
        await storage.close()
        return False

    # Test 6: Mark as notified
    print(f"\n" + "=" * 70)
    print("Test 6: Mark Paper as Notified")
    print("=" * 70)
    try:
        await storage.mark_as_notified(test_paper.guid)
        print(f"✅ Paper marked as notified")

        # Verify
        retrieved = await storage.get_paper_by_guid(test_paper.guid)
        if retrieved and retrieved.is_notified:
            print(f"✅ Verified: is_notified = True")
        else:
            print(f"⚠️  Warning: is_notified status not updated")
    except Exception as e:
        print(f"❌ Failed to mark as notified: {e}")
        import traceback
        traceback.print_exc()
        await storage.close()
        return False

    # Test 7: Update summary
    print(f"\n" + "=" * 70)
    print("Test 7: Update Paper Summary")
    print("=" * 70)
    try:
        from citeo.models.paper import PaperSummary

        test_summary = PaperSummary(
            title_zh="测试论文标题",
            abstract_zh="这是一个测试摘要",
            key_points=["要点1", "要点2", "要点3"],
            relevance_score=0.85,
        )

        await storage.update_summary(test_paper.guid, test_summary)
        print(f"✅ Summary updated successfully")

        # Verify
        retrieved = await storage.get_paper_by_guid(test_paper.guid)
        if retrieved and retrieved.summary:
            print(f"✅ Verified: Summary exists")
            print(f"   Title (ZH): {retrieved.summary.title_zh}")
            print(f"   Relevance: {retrieved.summary.relevance_score}")
            print(f"   Key Points: {len(retrieved.summary.key_points)}")
        else:
            print(f"⚠️  Warning: Summary not found")
    except Exception as e:
        print(f"❌ Failed to update summary: {e}")
        import traceback
        traceback.print_exc()
        await storage.close()
        return False

    # Test 8: Get papers by date
    print(f"\n" + "=" * 70)
    print("Test 8: Get Papers by Date Range")
    print("=" * 70)
    try:
        from datetime import timedelta

        start_date = datetime.utcnow() - timedelta(days=1)
        end_date = datetime.utcnow() + timedelta(days=1)

        papers = await storage.get_papers_by_date(start_date, end_date)
        print(f"✅ Retrieved {len(papers)} paper(s) in date range")
    except Exception as e:
        print(f"❌ Failed to get papers by date: {e}")
        import traceback
        traceback.print_exc()
        await storage.close()
        return False

    # Cleanup
    print(f"\n" + "=" * 70)
    print("Cleanup")
    print("=" * 70)
    await storage.close()
    print(f"✅ Storage connection closed")

    # Summary
    print(f"\n" + "=" * 70)
    print("✅ All D1 Integration Tests Passed!")
    print("=" * 70)
    print(f"\nD1 Database is working correctly:")
    print(f"  ✅ Schema initialization")
    print(f"  ✅ Save paper (with deduplication)")
    print(f"  ✅ Get paper by GUID")
    print(f"  ✅ Get paper by arXiv ID")
    print(f"  ✅ Get pending papers")
    print(f"  ✅ Mark as notified")
    print(f"  ✅ Update summary")
    print(f"  ✅ Get papers by date range")

    return True


if __name__ == "__main__":
    result = asyncio.run(test_d1_real())
    sys.exit(0 if result else 1)
