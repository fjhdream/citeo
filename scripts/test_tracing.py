"""Test script to verify OpenAI Agents SDK tracing configuration.

This script runs a simple agent call and checks if tracing is working.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agents import Runner

from citeo.ai.agents import summarizer_agent
from citeo.config.settings import settings


async def test_tracing():
    """Test tracing configuration and run a simple agent call."""

    print("=" * 60)
    print("OpenAI Agents SDK Tracing Test")
    print("=" * 60)

    # Check tracing status
    print("\n📊 Tracing Configuration:")
    print(f"  - OPENAI_TRACING_ENABLED: {settings.openai_tracing_enabled}")
    print(f"  - OPENAI_TRACING_API_KEY: {'Set' if settings.openai_tracing_api_key else 'Not set'}")
    print(f"  - OPENAI_BASE_URL: {settings.openai_base_url or 'Default (api.openai.com)'}")

    # Determine expected behavior based on configuration
    tracing_should_be_disabled = not settings.openai_tracing_enabled or (
        settings.openai_base_url and not settings.openai_tracing_api_key
    )

    if tracing_should_be_disabled:
        print("\n⚠️  Tracing is DISABLED")
        if not settings.openai_tracing_enabled:
            print("   Reason: OPENAI_TRACING_ENABLED=false in config")
        elif settings.openai_base_url and not settings.openai_tracing_api_key:
            print("   Reason: Using custom base URL without separate tracing key")
    else:
        print("\n✅ Tracing is ENABLED")
        if settings.openai_tracing_api_key:
            print("   Using separate API key for tracing")
        else:
            print("   Using main API key for tracing")

    # Run a test agent call
    print("\n🧪 Running test agent call...")

    test_input = """
    Title: Attention Is All You Need

    Abstract: The dominant sequence transduction models are based on complex recurrent
    or convolutional neural networks. We propose a new simple network architecture,
    the Transformer, based solely on attention mechanisms.
    """

    try:
        result = await Runner.run(summarizer_agent, test_input)

        print("\n✅ Agent call successful!")
        print("\nResult:")
        print(f"  Title (ZH): {result.final_output.title_zh}")
        print(f"  Relevance: {result.final_output.relevance_score}")

        # Check for tracing info in result
        if hasattr(result, "trace_id") and result.trace_id:
            print(f"\n🔍 Trace ID found: {result.trace_id}")
            print(f"   View trace at: https://platform.openai.com/traces/{result.trace_id}")
        elif hasattr(result, "trace_url") and result.trace_url:
            print(f"\n🔍 Trace URL: {result.trace_url}")
        else:
            print("\n📝 No trace info in result (tracing may be disabled or not available)")
            print(
                f"   Result attributes: {[attr for attr in dir(result) if not attr.startswith('_')]}"
            )

    except Exception as e:
        print(f"\n❌ Agent call failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)

    return True


if __name__ == "__main__":
    asyncio.run(test_tracing())
