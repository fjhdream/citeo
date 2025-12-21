"""Quick test for the new /api/papers/by-date endpoint."""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multiprocessing import Process

import httpx
import uvicorn


def run_server():
    """Run the API server in a separate process."""
    from citeo.main import create_app

    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=8766, log_level="error")


async def wait_for_server(base_url: str, timeout: int = 10):
    """Wait for server to be ready."""
    start = asyncio.get_event_loop().time()
    async with httpx.AsyncClient() as client:
        while True:
            try:
                response = await client.get(f"{base_url}/api/health", timeout=1.0)
                if response.status_code == 200:
                    return True
            except (httpx.ConnectError, httpx.ReadTimeout):
                pass

            if asyncio.get_event_loop().time() - start > timeout:
                return False

            await asyncio.sleep(0.1)


async def test_by_date_endpoint():
    """Test the new /api/papers/by-date endpoint."""
    print("=" * 70)
    print("🧪 Testing /api/papers/by-date endpoint")
    print("=" * 70)

    base_url = "http://127.0.0.1:8766"

    # Start server
    print(f"\n🚀 Starting API server on {base_url}...")
    server_process = Process(target=run_server, daemon=True)
    server_process.start()

    if not await wait_for_server(base_url, timeout=15):
        print("❌ Server failed to start")
        server_process.terminate()
        return False

    print("✅ Server is ready")

    try:
        # First, create some test papers
        from citeo.config.settings import settings
        from citeo.models.paper import Paper
        from citeo.storage import create_storage

        storage = create_storage(settings)
        await storage.initialize()

        # Create papers with different dates
        today = datetime.utcnow()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)

        test_papers = [
            Paper(
                guid="test:today_1",
                arxiv_id="2512.00001",
                title="Today's Paper 1",
                abstract="Test paper for today",
                authors=["Test Author"],
                categories=["cs.AI"],
                announce_type="new",
                published_at=today,
                abs_url="https://arxiv.org/abs/2512.00001",
                source_id="test",
                fetched_at=today,
            ),
            Paper(
                guid="test:today_2",
                arxiv_id="2512.00002",
                title="Today's Paper 2",
                abstract="Another test paper for today",
                authors=["Test Author"],
                categories=["cs.LG"],
                announce_type="new",
                published_at=today,
                abs_url="https://arxiv.org/abs/2512.00002",
                source_id="test",
                fetched_at=today,
            ),
            Paper(
                guid="test:yesterday",
                arxiv_id="2512.00003",
                title="Yesterday's Paper",
                abstract="Test paper for yesterday",
                authors=["Test Author"],
                categories=["cs.AI"],
                announce_type="new",
                published_at=yesterday,
                abs_url="https://arxiv.org/abs/2512.00003",
                source_id="test",
                fetched_at=yesterday,
            ),
        ]

        for paper in test_papers:
            await storage.save_paper(paper)

        print(f"✅ Created {len(test_papers)} test papers")

        await storage.close()

        async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
            # Test 1: Get today's papers (default)
            print("\n" + "-" * 70)
            print("Test 1: GET /api/papers/by-date (default - today)")
            print("-" * 70)
            try:
                response = await client.get("/api/papers/by-date")
                if response.status_code == 200:
                    data = response.json()
                    print("✅ Default query works")
                    print(f"   Status Code: {response.status_code}")
                    print(f"   Total: {data['total']}")
                    print(f"   Count: {data['count']}")
                    print(f"   Limit: {data['limit']}")
                    print(f"   Papers returned: {len(data['papers'])}")
                    if data["papers"]:
                        print(f"   First paper: {data['papers'][0]['title']}")
                else:
                    print(f"❌ Unexpected status: {response.status_code}")
                    print(f"   Response: {response.text}")
                    return False
            except Exception as e:
                print(f"❌ Test failed: {e}")
                import traceback

                traceback.print_exc()
                return False

            # Test 2: Query with specific date
            print("\n" + "-" * 70)
            print("Test 2: GET /api/papers/by-date?date=YYYY-MM-DD")
            print("-" * 70)
            try:
                date_str = today.strftime("%Y-%m-%d")
                response = await client.get(f"/api/papers/by-date?date={date_str}")
                if response.status_code == 200:
                    data = response.json()
                    print("✅ Date query works")
                    print(f"   Query Date: {date_str}")
                    print(f"   Total: {data['total']}")
                    print(f"   Count: {data['count']}")
                    print(f"   Query Date (response): {data['query_date']}")
                else:
                    print(f"❌ Unexpected status: {response.status_code}")
                    return False
            except Exception as e:
                print(f"❌ Test failed: {e}")
                return False

            # Test 3: Query with date range
            print("\n" + "-" * 70)
            print("Test 3: GET /api/papers/by-date?start_date=...&end_date=...")
            print("-" * 70)
            try:
                start_str = yesterday.strftime("%Y-%m-%d")
                end_str = tomorrow.strftime("%Y-%m-%d")
                response = await client.get(
                    f"/api/papers/by-date?start_date={start_str}&end_date={end_str}"
                )
                if response.status_code == 200:
                    data = response.json()
                    print("✅ Range query works")
                    print(f"   Range: {start_str} to {end_str}")
                    print(f"   Total: {data['total']}")
                    print(f"   Count: {data['count']}")
                    print(f"   Query Range: {data['query_range']}")
                else:
                    print(f"❌ Unexpected status: {response.status_code}")
                    return False
            except Exception as e:
                print(f"❌ Test failed: {e}")
                return False

            # Test 4: Pagination
            print("\n" + "-" * 70)
            print("Test 4: GET /api/papers/by-date?limit=1&offset=0")
            print("-" * 70)
            try:
                response = await client.get("/api/papers/by-date?limit=1&offset=0")
                if response.status_code == 200:
                    data = response.json()
                    print("✅ Pagination works")
                    print(f"   Limit: {data['limit']}")
                    print(f"   Offset: {data['offset']}")
                    print(f"   Papers returned: {len(data['papers'])}")
                    if len(data["papers"]) <= 1:
                        print("   ✅ Limit respected")
                    else:
                        print("   ❌ Limit not respected")
                        return False
                else:
                    print(f"❌ Unexpected status: {response.status_code}")
                    return False
            except Exception as e:
                print(f"❌ Test failed: {e}")
                return False

            # Test 5: Invalid date format
            print("\n" + "-" * 70)
            print("Test 5: GET /api/papers/by-date?date=invalid (400)")
            print("-" * 70)
            try:
                response = await client.get("/api/papers/by-date?date=invalid")
                if response.status_code == 400:
                    data = response.json()
                    print("✅ Error handling works")
                    print(f"   Status Code: {response.status_code}")
                    print(f"   Error: {data.get('detail')}")
                else:
                    print(f"❌ Expected 400, got {response.status_code}")
                    return False
            except Exception as e:
                print(f"❌ Test failed: {e}")
                return False

            # Test 6: Conflicting parameters
            print("\n" + "-" * 70)
            print("Test 6: GET /api/papers/by-date?date=X&start_date=Y (400)")
            print("-" * 70)
            try:
                response = await client.get(
                    "/api/papers/by-date?date=2025-01-01&start_date=2025-01-02"
                )
                if response.status_code == 400:
                    data = response.json()
                    print("✅ Parameter validation works")
                    print(f"   Status Code: {response.status_code}")
                    print(f"   Error: {data.get('detail')}")
                else:
                    print(f"❌ Expected 400, got {response.status_code}")
                    return False
            except Exception as e:
                print(f"❌ Test failed: {e}")
                return False

    finally:
        # Cleanup
        print("\n" + "=" * 70)
        print("Cleanup")
        print("=" * 70)
        print("🛑 Stopping server...")
        server_process.terminate()
        server_process.join(timeout=5)
        if server_process.is_alive():
            server_process.kill()
        print("✅ Server stopped")

    # Summary
    print("\n" + "=" * 70)
    print("✅ All Tests Passed!")
    print("=" * 70)
    print("\nValidated:")
    print("  ✅ Default query (today's papers)")
    print("  ✅ Single date query")
    print("  ✅ Date range query")
    print("  ✅ Pagination (limit/offset)")
    print("  ✅ Invalid date error handling")
    print("  ✅ Conflicting parameters error handling")
    print("\n💡 /api/papers/by-date endpoint is working correctly!")

    return True


if __name__ == "__main__":
    result = asyncio.run(test_by_date_endpoint())
    sys.exit(0 if result else 1)
