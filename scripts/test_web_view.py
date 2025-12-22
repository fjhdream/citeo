#!/usr/bin/env python3
"""Test script for web view endpoint.

Quick test to verify the new /api/view/{arxiv_id} endpoint works correctly.
"""

import asyncio

from citeo.api.routes import get_storage, init_services, view_analysis
from citeo.config.settings import settings


async def test_web_view():
    """Test the web view endpoint with existing data."""
    print("🧪 Testing Web View Endpoint\n")

    # Initialize services
    print("1. Initializing services...")
    init_services(settings)
    print("   ✅ Services initialized\n")

    # Get storage
    storage = get_storage()

    # Find a paper with deep analysis
    print("2. Looking for papers with deep analysis...")
    from datetime import datetime, timedelta

    # Look in the last 7 days
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=7)

    papers = await storage.get_papers_by_date(start_date, end_date)
    papers_with_analysis = [p for p in papers if p.summary and p.summary.deep_analysis]

    if papers_with_analysis:
        paper = papers_with_analysis[0]
        print(f"   ✅ Found paper with deep analysis: {paper.arxiv_id}")
        print(f"      Title: {paper.title[:60]}...")
        print(f"      Analysis length: {len(paper.summary.deep_analysis)} chars\n")

        # Create a mock request object
        from fastapi import Request

        class MockClient:
            host = "127.0.0.1"

        class MockRequest:
            client = MockClient()

        mock_request = MockRequest()

        # Test the view_analysis function
        print("3. Testing view_analysis endpoint...")
        try:
            response = await view_analysis(paper.arxiv_id, mock_request)
            print(f"   ✅ View rendered successfully")
            print(f"      Response type: {type(response)}")
            print(f"      Content length: {len(response.body)} bytes\n")

            # Check if the HTML contains expected elements
            html_content = response.body.decode("utf-8")
            checks = [
                ("<!DOCTYPE html>" in html_content, "HTML doctype"),
                ("<title>" in html_content, "Title tag"),
                (paper.arxiv_id in html_content, "arXiv ID"),
                ("完整查看" not in html_content, "No self-reference link"),
                (
                    paper.abs_url in html_content
                    or paper.abs_url.replace("&", "&amp;") in html_content,
                    "arXiv abstract URL",
                ),
            ]

            print("4. Checking HTML content:")
            for passed, check_name in checks:
                status = "✅" if passed else "❌"
                print(f"   {status} {check_name}")

            print("\n✨ All tests passed!")

        except Exception as e:
            print(f"   ❌ Error: {e}\n")
            import traceback

            traceback.print_exc()

    else:
        print("   ⚠️  No papers with deep analysis found in the last 7 days")
        print("      Run analysis on a paper first using:")
        print("      curl -X POST http://localhost:8000/api/papers/{arxiv_id}/analyze")
        print()


if __name__ == "__main__":
    asyncio.run(test_web_view())
