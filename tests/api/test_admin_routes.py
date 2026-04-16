"""Tests for admin paper management routes."""

import os
from datetime import datetime

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from citeo.api.admin_routes import admin_api_router, admin_page_router
from citeo.auth.dependencies import require_auth
from citeo.auth.models import AuthUser
from citeo.models.paper import Paper, PaperSummary


class FakeStorage:
    def __init__(self, papers: list[Paper]):
        self.papers = papers
        self.summary_updates: list[tuple[str, PaperSummary]] = []

    async def get_papers_by_fetched_date(self, start_date, end_date):
        return self.papers

    async def get_paper_by_arxiv_id(self, arxiv_id: str):
        return next((p for p in self.papers if p.arxiv_id == arxiv_id), None)

    async def update_summary(self, guid: str, summary: PaperSummary) -> None:
        self.summary_updates.append((guid, summary))


def make_paper(arxiv_id: str, *, title: str) -> Paper:
    return Paper(
        guid=f"oai:arXiv.org:{arxiv_id}v1",
        arxiv_id=arxiv_id,
        title=title,
        abstract="Test abstract",
        authors=["Alice", "Bob"],
        categories=["cs.AI"],
        announce_type="new",
        published_at=datetime(2026, 4, 16, 9, 0, 0),
        abs_url=f"https://arxiv.org/abs/{arxiv_id}",
        source_id="arxiv.cs.AI",
        fetched_at=datetime(2026, 4, 16, 10, 0, 0),
    )


def build_app(monkeypatch, storage: FakeStorage) -> FastAPI:
    from citeo.api import admin_routes

    app = FastAPI()
    app.include_router(admin_page_router)
    app.dependency_overrides[require_auth] = lambda: AuthUser(
        user_id="tester", auth_method="api_key"
    )
    monkeypatch.setattr(admin_routes, "get_storage", lambda: storage)
    return app


def build_full_app(monkeypatch, storage: FakeStorage) -> FastAPI:
    from citeo.api import admin_routes

    app = FastAPI()
    app.include_router(admin_page_router)
    app.include_router(admin_api_router)
    app.dependency_overrides[require_auth] = lambda: AuthUser(
        user_id="tester", auth_method="api_key"
    )
    monkeypatch.setattr(admin_routes, "get_storage", lambda: storage)
    return app


def test_admin_papers_page_requires_auth() -> None:
    app = FastAPI()
    app.include_router(admin_page_router)

    response = TestClient(app).get("/admin/papers")

    assert response.status_code == 401


def test_admin_papers_page_lists_fetched_papers(monkeypatch) -> None:
    storage = FakeStorage([make_paper("2604.00001", title="Admin Paper")])
    app = build_app(monkeypatch, storage)

    response = TestClient(app).get("/admin/papers?api_key=browser-key")

    assert response.status_code == 200
    assert "Citeo 论文管理" in response.text
    assert "Admin Paper" in response.text
    assert "🔄 重试摘要" in response.text
    assert "browser-key" in response.text
