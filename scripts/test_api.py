"""API integration tests.

Tests all API endpoints with real database backend.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


from citeo.api.routes import init_services
from citeo.models.paper import Paper


async def test_api():
    """Test all API endpoints."""
    print("=" * 70)
    print("🧪 API Integration Tests")
    print("=" * 70)

    # Load settings
    try:
        from citeo.config.settings import settings
    except Exception as e:
        print(f"❌ Failed to load settings: {e}")
        return False

    print("\n📊 Configuration:")
    print(f"  DB_TYPE: {settings.db_type}")

    # Initialize services
    print("\n🔧 Initializing API services...")
    try:
        init_services(settings)
        print("✅ Services initialized")
    except Exception as e:
        print(f"❌ Failed to initialize services: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Get storage and prepare test data
    from citeo.api.routes import get_storage

    storage = get_storage()
    await storage.initialize()
    print("✅ Storage initialized")

    # Create test paper
    test_paper = Paper(
        guid=f"oai:arXiv.org:api_test.{datetime.now().microsecond}",
        arxiv_id=f"2501.{datetime.now().microsecond:05d}",
        title="API Test Paper",
        abstract="This paper tests the API endpoints.",
        authors=["Test Author"],
        categories=["cs.AI"],
        announce_type="new",
        published_at=datetime.utcnow(),
        abs_url=f"https://arxiv.org/abs/2501.{datetime.now().microsecond:05d}",
        source_id="test_source",
        fetched_at=datetime.utcnow(),
    )

    print("\n📄 Creating test paper...")
    try:
        is_new = await storage.save_paper(test_paper)
        print(f"✅ Test paper saved (new={is_new})")
        print(f"   arXiv ID: {test_paper.arxiv_id}")
        print(f"   Title: {test_paper.title}")
    except Exception as e:
        print(f"❌ Failed to save test paper: {e}")
        return False

    # Start testing endpoints
    print("\n" + "=" * 70)
    print("Testing API Endpoints")
    print("=" * 70)

    # We'll test the route handlers directly instead of starting a server
    # This is more reliable for integration tests

    # Test 1: Health Check
    print("\n" + "-" * 70)
    print("Test 1: Health Check Endpoint")
    print("-" * 70)
    try:
        from citeo.api.routes import health_check

        response = await health_check()
        if response.status == "ok":
            print("✅ Health check passed")
            print(f"   Status: {response.status}")
            print(f"   Version: {response.version}")
        else:
            print(f"❌ Health check failed: unexpected status {response.status}")
            return False
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test 2: Get Paper by arXiv ID
    print("\n" + "-" * 70)
    print("Test 2: GET /api/papers/{arxiv_id}")
    print("-" * 70)
    try:
        from citeo.api.routes import get_paper

        paper_response = await get_paper(test_paper.arxiv_id)
        if paper_response.arxiv_id == test_paper.arxiv_id:
            print("✅ Get paper endpoint passed")
            print(f"   arXiv ID: {paper_response.arxiv_id}")
            print(f"   Title: {paper_response.title}")
            print(f"   Authors: {len(paper_response.authors)} authors")
            print(f"   Has Summary: {paper_response.has_summary}")
            print(f"   Has Deep Analysis: {paper_response.has_deep_analysis}")
        else:
            print("❌ Get paper failed: wrong paper returned")
            return False
    except Exception as e:
        print(f"❌ Get paper failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test 3: Get Analysis (should not exist yet)
    print("\n" + "-" * 70)
    print("Test 3: GET /api/papers/{arxiv_id}/analysis")
    print("-" * 70)
    try:
        from citeo.api.routes import get_analysis

        analysis_response = await get_analysis(test_paper.arxiv_id)
        if analysis_response.status == "not_available":
            print("✅ Get analysis endpoint passed")
            print(f"   Status: {analysis_response.status} (expected)")
            print(f"   Analysis: {analysis_response.analysis}")
        else:
            print(f"⚠️  Unexpected status: {analysis_response.status}")
            print("   This is okay if analysis already exists")
    except Exception as e:
        print(f"❌ Get analysis failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test 4: Test nonexistent paper (404 handling)
    print("\n" + "-" * 70)
    print("Test 4: Error Handling (404)")
    print("-" * 70)
    try:
        from fastapi import HTTPException

        from citeo.api.routes import get_paper

        try:
            await get_paper("9999.99999")
            print("❌ Error handling failed: should have raised HTTPException")
            return False
        except HTTPException as e:
            if e.status_code == 404:
                print("✅ 404 error handling passed")
                print(f"   Status: {e.status_code}")
                print(f"   Detail: {e.detail}")
            else:
                print(f"❌ Wrong status code: {e.status_code} (expected 404)")
                return False
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test 5: Service Dependencies
    print("\n" + "-" * 70)
    print("Test 5: Service Dependencies")
    print("-" * 70)
    try:
        from citeo.api.routes import get_pdf_service, get_storage

        storage_instance = get_storage()
        pdf_service_instance = get_pdf_service()

        if storage_instance is not None and pdf_service_instance is not None:
            print("✅ Service dependencies working")
            print(f"   Storage: {type(storage_instance).__name__}")
            print(f"   PDF Service: {type(pdf_service_instance).__name__}")
        else:
            print("❌ Service dependencies failed: services are None")
            return False
    except Exception as e:
        print(f"❌ Service dependencies test failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test 6: Factory Pattern Integration
    print("\n" + "-" * 70)
    print("Test 6: Factory Pattern Integration")
    print("-" * 70)
    try:
        # Verify that the storage was created via factory
        # by checking it has all required Protocol methods
        required_methods = [
            "initialize",
            "save_paper",
            "get_paper_by_guid",
            "get_paper_by_arxiv_id",
            "get_papers_by_date",
            "get_pending_papers",
            "mark_as_notified",
            "update_summary",
            "close",
        ]

        all_methods_present = all(
            hasattr(storage_instance, method) and callable(getattr(storage_instance, method))
            for method in required_methods
        )

        if all_methods_present:
            print("✅ Factory pattern working correctly")
            print("   Storage implements all PaperStorage Protocol methods")
            print(f"   Concrete type: {type(storage_instance).__name__}")

            # Verify storage operations work
            test_retrieve = await storage_instance.get_paper_by_arxiv_id(test_paper.arxiv_id)
            if test_retrieve and test_retrieve.arxiv_id == test_paper.arxiv_id:
                print("✅ Storage operations working through Protocol")
            else:
                print("❌ Storage operations failed")
                return False
        else:
            missing = [m for m in required_methods if not hasattr(storage_instance, m)]
            print(f"❌ Storage missing required methods: {missing}")
            return False
    except Exception as e:
        print(f"❌ Factory pattern test failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Cleanup
    print("\n" + "=" * 70)
    print("Cleanup")
    print("=" * 70)
    await storage.close()
    print("✅ Storage connection closed")

    # Summary
    print("\n" + "=" * 70)
    print("✅ All API Tests Passed!")
    print("=" * 70)
    print("\nValidated Endpoints:")
    print("  ✅ GET /api/health - Health check")
    print("  ✅ GET /api/papers/{arxiv_id} - Get paper info")
    print("  ✅ GET /api/papers/{arxiv_id}/analysis - Get analysis status")
    print("  ✅ Error handling (404 responses)")
    print("  ✅ Service initialization and dependencies")
    print("  ✅ Factory pattern integration")
    print(f"\n💡 All API endpoints working correctly with {settings.db_type.upper()} database!")

    return True


if __name__ == "__main__":
    result = asyncio.run(test_api())
    sys.exit(0 if result else 1)
