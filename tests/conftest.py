"""Test configuration and fixtures."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_db_path():
    """Create a temporary database path for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


@pytest.fixture
def sample_rss_content():
    """Sample arXiv RSS content for testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:dc="http://purl.org/dc/elements/1.1/"
         xmlns:arxiv="http://arxiv.org/schemas/atom">
  <channel>
    <title>cs.AI updates on arXiv.org</title>
    <link>https://arxiv.org/</link>
  </channel>
  <item>
    <title>Test Paper Title</title>
    <link>https://arxiv.org/abs/2512.14709</link>
    <description>
      arXiv:2512.14709v1 Announce Type: new
      Abstract: This is a test abstract for the paper.
    </description>
    <dc:creator>John Doe, Jane Smith</dc:creator>
    <category>cs.AI</category>
    <guid isPermaLink="false">oai:arXiv.org:2512.14709v1</guid>
    <pubDate>Thu, 19 Dec 2024 00:00:00 GMT</pubDate>
  </item>
</rdf:RDF>"""


@pytest.fixture
def sample_paper_dict():
    """Sample paper data for testing."""
    return {
        "guid": "oai:arXiv.org:2512.14709v1",
        "arxiv_id": "2512.14709",
        "title": "Test Paper Title",
        "abstract": "This is a test abstract for the paper.",
        "authors": ["John Doe", "Jane Smith"],
        "categories": ["cs.AI"],
        "announce_type": "new",
        "abs_url": "https://arxiv.org/abs/2512.14709",
        "source_id": "arxiv.cs.AI",
    }
