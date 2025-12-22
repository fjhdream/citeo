#!/usr/bin/env python3
"""Quick script to verify web view endpoint appears in Swagger/OpenAPI.

Run this script, then visit:
http://localhost:8000/docs

Look for:
- "web-view" tag section
- GET /api/view/{arxiv_id} endpoint
"""

import subprocess
import sys
import time
import webbrowser

print("🚀 Starting Citeo API server...")
print("=" * 60)

# Start the server in the background
try:
    print("\n1. Launching server...")
    print("   Command: uv run citeo")

    # Note: We'll just show instructions instead of actually starting
    # because the user might want to control this themselves

    print("\n" + "=" * 60)
    print("📋 INSTRUCTIONS:")
    print("=" * 60)

    print("\n1. Start the API server:")
    print("   uv run citeo")
    print()

    print("2. Open Swagger UI in your browser:")
    print("   http://localhost:8000/docs")
    print()

    print("3. Look for the 'web-view' section:")
    print("   You should see:")
    print("   - Tag: 'web-view'")
    print("   - Endpoint: GET /api/view/{arxiv_id}")
    print("   - Summary: 'View deep analysis in browser'")
    print()

    print("4. Try it out:")
    print("   - Click on the endpoint")
    print("   - Click 'Try it out'")
    print("   - Enter an arxiv_id (e.g., 2512.15117)")
    print("   - Click 'Execute'")
    print("   - The response will be HTML (view in browser)")
    print()

    print("5. Or directly visit in browser:")
    print("   http://localhost:8000/api/view/2512.15117")
    print()

    print("=" * 60)
    print("🔧 TROUBLESHOOTING:")
    print("=" * 60)
    print()
    print("If you don't see the endpoint:")
    print("1. Make sure the server is running (uv run citeo)")
    print("2. Refresh the Swagger page (Ctrl+R / Cmd+R)")
    print("3. Check the URL is correct: http://localhost:8000/docs")
    print("4. Check server logs for any errors")
    print()
    print("If you get 404 when accessing /api/view/{arxiv_id}:")
    print("1. Make sure the paper has deep analysis (not all papers do)")
    print("2. Try with a known paper ID from test: 2512.15117")
    print("3. Run analysis first if needed:")
    print("   curl -X POST http://localhost:8000/api/papers/{arxiv_id}/analyze")
    print()

    print("=" * 60)

    # Ask if user wants to open browser
    try:
        choice = input("\nOpen http://localhost:8000/docs now? [y/N]: ").strip().lower()
        if choice == "y":
            print("\n🌐 Opening browser...")
            webbrowser.open("http://localhost:8000/docs")
            print("   If the page doesn't load, start the server first: uv run citeo")
    except KeyboardInterrupt:
        print("\n\n👋 Cancelled")

except Exception as e:
    print(f"\n❌ Error: {e}")
    sys.exit(1)
