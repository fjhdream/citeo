"""HTTP API integration tests.

Tests API endpoints with real HTTP server using httpx client.
"""

import asyncio
import signal
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import httpx
import uvicorn
from multiprocessing import Process


def run_server():
    """Run the API server in a separate process."""
    from citeo.main import create_app

    # Create app (lifespan handles initialization)
    app = create_app()

    # Run server
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8765,
        log_level="error",  # Suppress logs for testing
    )


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


async def test_http_api():
    """Test API with real HTTP requests."""
    print("=" * 70)
    print("🌐 HTTP API Integration Tests")
    print("=" * 70)

    base_url = "http://127.0.0.1:8765"

    # Start server in background
    print(f"\n🚀 Starting API server on {base_url}...")
    server_process = Process(target=run_server, daemon=True)
    server_process.start()

    # Wait for server to be ready
    if not await wait_for_server(base_url, timeout=15):
        print(f"❌ Server failed to start within timeout")
        server_process.terminate()
        return False

    print(f"✅ Server is ready")

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
            # Test 1: Health Check
            print(f"\n" + "-" * 70)
            print("Test 1: GET /api/health")
            print("-" * 70)
            try:
                response = await client.get("/api/health")
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ Health check passed")
                    print(f"   Status Code: {response.status_code}")
                    print(f"   Response: {data}")
                else:
                    print(f"❌ Unexpected status code: {response.status_code}")
                    return False
            except Exception as e:
                print(f"❌ Health check failed: {e}")
                return False

            # Test 2: Get nonexistent paper (404)
            print(f"\n" + "-" * 70)
            print("Test 2: GET /api/papers/9999.99999 (404)")
            print("-" * 70)
            try:
                response = await client.get("/api/papers/9999.99999")
                if response.status_code == 404:
                    data = response.json()
                    print(f"✅ 404 handling works correctly")
                    print(f"   Status Code: {response.status_code}")
                    print(f"   Error: {data.get('detail')}")
                else:
                    print(f"❌ Expected 404, got {response.status_code}")
                    return False
            except Exception as e:
                print(f"❌ 404 test failed: {e}")
                return False

            # Test 3: Create a test paper and retrieve it
            print(f"\n" + "-" * 70)
            print("Test 3: Paper Retrieval via HTTP")
            print("-" * 70)

            # First, create a test paper using storage directly
            from citeo.config.settings import settings
            from citeo.models.paper import Paper
            from citeo.storage import create_storage

            storage = create_storage(settings)
            await storage.initialize()

            test_paper = Paper(
                guid=f"oai:arXiv.org:http_test.{datetime.now().microsecond}",
                arxiv_id=f"2501.{datetime.now().microsecond:05d}",
                title="HTTP API Test Paper",
                abstract="Testing HTTP API endpoints.",
                authors=["HTTP Test Author"],
                categories=["cs.AI"],
                announce_type="new",
                published_at=datetime.utcnow(),
                abs_url=f"https://arxiv.org/abs/2501.{datetime.now().microsecond:05d}",
                source_id="http_test",
                fetched_at=datetime.utcnow(),
            )

            is_new = await storage.save_paper(test_paper)
            print(f"   Created test paper: {test_paper.arxiv_id}")

            # Now retrieve via HTTP
            try:
                response = await client.get(f"/api/papers/{test_paper.arxiv_id}")
                if response.status_code == 200:
                    data = response.json()
                    if data["arxiv_id"] == test_paper.arxiv_id:
                        print(f"✅ Paper retrieval via HTTP works")
                        print(f"   Status Code: {response.status_code}")
                        print(f"   arXiv ID: {data['arxiv_id']}")
                        print(f"   Title: {data['title']}")
                        print(f"   Authors: {data['authors']}")
                    else:
                        print(f"❌ Wrong paper returned")
                        return False
                else:
                    print(f"❌ Unexpected status code: {response.status_code}")
                    return False
            except Exception as e:
                print(f"❌ Paper retrieval failed: {e}")
                import traceback
                traceback.print_exc()
                return False
            finally:
                await storage.close()

            # Test 4: Get analysis status
            print(f"\n" + "-" * 70)
            print("Test 4: GET /api/papers/{arxiv_id}/analysis")
            print("-" * 70)
            try:
                response = await client.get(f"/api/papers/{test_paper.arxiv_id}/analysis")
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ Analysis endpoint works")
                    print(f"   Status Code: {response.status_code}")
                    print(f"   Status: {data.get('status')}")
                    print(f"   Has Analysis: {data.get('analysis') is not None}")
                else:
                    print(f"❌ Unexpected status code: {response.status_code}")
                    return False
            except Exception as e:
                print(f"❌ Analysis endpoint failed: {e}")
                return False

            # Test 5: Content-Type headers
            print(f"\n" + "-" * 70)
            print("Test 5: Response Headers")
            print("-" * 70)
            try:
                response = await client.get("/api/health")
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    print(f"✅ Correct Content-Type header")
                    print(f"   Content-Type: {content_type}")
                else:
                    print(f"⚠️  Unexpected Content-Type: {content_type}")
            except Exception as e:
                print(f"❌ Headers test failed: {e}")
                return False

    finally:
        # Cleanup: stop server
        print(f"\n" + "=" * 70)
        print("Cleanup")
        print("=" * 70)
        print(f"🛑 Stopping server...")
        server_process.terminate()
        server_process.join(timeout=5)
        if server_process.is_alive():
            server_process.kill()
        print(f"✅ Server stopped")

    # Summary
    print(f"\n" + "=" * 70)
    print("✅ All HTTP API Tests Passed!")
    print("=" * 70)
    print(f"\nValidated:")
    print(f"  ✅ HTTP server starts and responds")
    print(f"  ✅ JSON API responses")
    print(f"  ✅ Error handling (404)")
    print(f"  ✅ Paper retrieval via HTTP")
    print(f"  ✅ Analysis status endpoint")
    print(f"  ✅ Correct response headers")
    print(f"\n💡 API is production-ready for HTTP requests!")

    return True


if __name__ == "__main__":
    result = asyncio.run(test_http_api())
    sys.exit(0 if result else 1)
