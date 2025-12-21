"""arXiv RSS feed parser implementation."""

import re
from datetime import datetime

import feedparser

from citeo.exceptions import ParseError
from citeo.models.paper import Paper


class ArxivParser:
    """Parser for arXiv RSS feeds.

    Handles the specific structure of arXiv RSS items including
    extraction of arXiv ID, abstract, and metadata.
    """

    def parse(self, raw_content: str, source_id: str) -> list[Paper]:
        """Parse arXiv RSS content into Paper objects.

        Args:
            raw_content: Raw XML string from arXiv RSS.
            source_id: Source identifier for metadata.

        Returns:
            List of parsed Paper objects.

        Raises:
            ParseError: When parsing fails.
        """
        try:
            feed = feedparser.parse(raw_content)

            if feed.bozo and not feed.entries:
                # feedparser sets bozo=1 for any parse issues
                raise ParseError(source_id, f"Feed parse error: {feed.bozo_exception}")

            papers: list[Paper] = []
            for entry in feed.entries:
                paper = self._parse_entry(entry, source_id)
                if paper:
                    papers.append(paper)

            return papers

        except ParseError:
            raise
        except Exception as e:
            raise ParseError(source_id, f"Unexpected parse error: {e}") from e

    def _parse_entry(self, entry: feedparser.FeedParserDict, source_id: str) -> Paper | None:
        """Parse a single feed entry into a Paper object.

        Args:
            entry: feedparser entry dict.
            source_id: Source identifier.

        Returns:
            Paper object or None if entry is invalid.
        """
        # Extract GUID
        guid = entry.get("id", entry.get("guid", ""))
        if not guid:
            return None

        # Extract arXiv ID from GUID (e.g., oai:arXiv.org:2512.14709v1 -> 2512.14709)
        arxiv_id = self._extract_arxiv_id(guid)
        if not arxiv_id:
            return None

        # Extract title (remove newlines and extra spaces)
        title = self._clean_text(entry.get("title", ""))
        if not title:
            return None

        # Extract abstract from description
        description = entry.get("description", entry.get("summary", ""))
        abstract = self._extract_abstract(description)

        # Extract authors
        authors = self._extract_authors(entry)

        # Extract categories
        categories = self._extract_categories(entry)

        # Extract announce type
        announce_type = self._extract_announce_type(entry, description)

        # Extract publication date
        published_at = self._parse_date(entry)

        # Build abstract URL
        abs_url = entry.get("link", f"https://arxiv.org/abs/{arxiv_id}")

        return Paper(
            guid=guid,
            arxiv_id=arxiv_id,
            title=title,
            abstract=abstract,
            authors=authors,
            categories=categories,
            announce_type=announce_type,
            published_at=published_at,
            abs_url=abs_url,
            source_id=source_id,
        )

    def _extract_arxiv_id(self, guid: str) -> str | None:
        """Extract arXiv ID from GUID.

        Example: oai:arXiv.org:2512.14709v1 -> 2512.14709
        """
        # Pattern matches arXiv IDs like 2512.14709 or 2512.14709v1
        match = re.search(r"(\d{4}\.\d{4,5})", guid)
        if match:
            return match.group(1)

        # Try older format like arXiv:cs/0001001
        match = re.search(r"([a-z-]+/\d+)", guid)
        if match:
            return match.group(1)

        return None

    def _extract_abstract(self, description: str) -> str:
        """Extract abstract from description field.

        The description typically contains metadata followed by the abstract.
        """
        if not description:
            return ""

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", description)

        # The abstract usually comes after "Abstract:" or after metadata lines
        # arXiv format: "arXiv:ID ... Abstract: ..."
        abstract_match = re.search(r"Abstract:\s*(.+)", text, re.DOTALL | re.IGNORECASE)
        if abstract_match:
            return self._clean_text(abstract_match.group(1))

        # If no "Abstract:" marker, try to find the main text
        # Skip lines that look like metadata (short lines with colons)
        lines = text.strip().split("\n")
        abstract_lines = []
        in_abstract = False

        for line in lines:
            line = line.strip()
            # Skip empty lines and metadata-like lines at the start
            if not line:
                if in_abstract:
                    abstract_lines.append("")
                continue

            # Detect metadata lines (usually short with specific patterns)
            if not in_abstract and (
                ":" in line[:30]
                and len(line) < 100
                and any(
                    kw in line.lower() for kw in ["arxiv:", "comments:", "subjects:", "report-no:"]
                )
            ):
                continue

            in_abstract = True
            abstract_lines.append(line)

        return self._clean_text(" ".join(abstract_lines))

    def _extract_authors(self, entry: feedparser.FeedParserDict) -> list[str]:
        """Extract author names from entry."""
        authors = []

        # Try dc:creator first (Dublin Core)
        if "author" in entry:
            author = entry["author"]
            if isinstance(author, str):
                # Parse comma or "and" separated names
                authors = self._parse_author_string(author)
            elif isinstance(author, dict) and "name" in author:
                authors = [author["name"]]

        # Try authors list
        if not authors and "authors" in entry:
            for author in entry["authors"]:
                if isinstance(author, dict) and "name" in author:
                    authors.append(author["name"])
                elif isinstance(author, str):
                    authors.append(author)

        return authors

    def _parse_author_string(self, author_str: str) -> list[str]:
        """Parse author string into list of names."""
        # Remove HTML tags
        author_str = re.sub(r"<[^>]+>", "", author_str)

        # Split by comma or " and "
        parts = re.split(r",\s*|\s+and\s+", author_str)
        return [name.strip() for name in parts if name.strip()]

    def _extract_categories(self, entry: feedparser.FeedParserDict) -> list[str]:
        """Extract categories/tags from entry."""
        categories = []

        # Try tags
        if "tags" in entry:
            for tag in entry["tags"]:
                if isinstance(tag, dict) and "term" in tag:
                    categories.append(tag["term"])
                elif isinstance(tag, str):
                    categories.append(tag)

        # Try category field
        if not categories and "category" in entry:
            cat = entry["category"]
            if isinstance(cat, str):
                categories = [cat]
            elif isinstance(cat, list):
                categories = cat

        return categories

    def _extract_announce_type(self, entry: feedparser.FeedParserDict, description: str) -> str:
        """Extract announcement type (new, cross, replace)."""
        # Check arxiv:announce_type if available
        if hasattr(entry, "arxiv_announce_type"):
            return entry.arxiv_announce_type

        # Try to infer from description
        desc_lower = description.lower()
        if "cross-list" in desc_lower or "cross list" in desc_lower:
            return "cross"
        if "replacement" in desc_lower or "replaced" in desc_lower:
            return "replace"

        return "new"

    def _parse_date(self, entry: feedparser.FeedParserDict) -> datetime:
        """Parse publication date from entry."""
        # Try published_parsed first
        if "published_parsed" in entry and entry["published_parsed"]:
            try:
                return datetime(*entry["published_parsed"][:6])
            except (ValueError, TypeError):
                pass

        # Try updated_parsed
        if "updated_parsed" in entry and entry["updated_parsed"]:
            try:
                return datetime(*entry["updated_parsed"][:6])
            except (ValueError, TypeError):
                pass

        # Fall back to current time
        return datetime.utcnow()

    def _clean_text(self, text: str) -> str:
        """Clean text by normalizing whitespace."""
        # Replace multiple whitespace with single space
        text = re.sub(r"\s+", " ", text)
        return text.strip()
