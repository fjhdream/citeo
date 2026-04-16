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


# --- Task 2: Retry summary ---


def test_retry_summary_updates_storage(monkeypatch) -> None:
    storage = FakeStorage([make_paper("2604.00002", title="Retry Summary Paper")])

    async def fake_summarize_paper(paper: Paper) -> PaperSummary:
        return PaperSummary(
            title_zh="重试成功",
            abstract_zh="中文摘要",
            key_points=["要点 1"],
            relevance_score=8.5,
        )

    from citeo.api import admin_routes

    monkeypatch.setattr(admin_routes, "summarize_paper", fake_summarize_paper)
    app = build_full_app(monkeypatch, storage)

    response = TestClient(app).post("/api/admin/papers/2604.00002/retry-summary")

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert storage.summary_updates[0][0] == "oai:arXiv.org:2604.00002v1"
    assert storage.summary_updates[0][1].title_zh == "重试成功"


def test_retry_summary_returns_500_when_ai_fails(monkeypatch) -> None:
    from citeo.exceptions import AIProcessingError

    storage = FakeStorage([make_paper("2604.00003", title="Broken Summary")])

    async def fake_summarize_paper(paper: Paper) -> PaperSummary:
        raise AIProcessingError(paper.guid, "summary crashed")

    from citeo.api import admin_routes

    monkeypatch.setattr(admin_routes, "summarize_paper", fake_summarize_paper)
    app = build_full_app(monkeypatch, storage)

    response = TestClient(app).post("/api/admin/papers/2604.00003/retry-summary")

    assert response.status_code == 500
    assert "summary crashed" in response.json()["detail"]


# --- Task 3: Retry analysis ---


class FakePDFService:
    def __init__(self, result: dict):
        self.result = result
        self.calls: list[tuple[str, bool, bool]] = []

    async def analyze_paper(
        self, arxiv_id: str, force: bool = False, skip_notification: bool = False
    ):
        self.calls.append((arxiv_id, force, skip_notification))
        return self.result


def test_retry_analysis_forces_reanalysis_without_notification(monkeypatch) -> None:
    storage = FakeStorage([make_paper("2604.00004", title="Retry Analysis Paper")])
    pdf_service = FakePDFService(
        {"arxiv_id": "2604.00004", "status": "completed", "analysis": "done"}
    )

    from citeo.api import admin_routes

    monkeypatch.setattr(admin_routes, "get_pdf_service", lambda: pdf_service)
    app = build_full_app(monkeypatch, storage)

    response = TestClient(app).post("/api/admin/papers/2604.00004/retry-analysis")

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert pdf_service.calls == [("2604.00004", True, True)]


def test_retry_analysis_returns_500_on_service_error(monkeypatch) -> None:
    storage = FakeStorage([make_paper("2604.00005", title="Retry Analysis Error")])
    pdf_service = FakePDFService(
        {"arxiv_id": "2604.00005", "status": "error", "error": "pdf failed"}
    )

    from citeo.api import admin_routes

    monkeypatch.setattr(admin_routes, "get_pdf_service", lambda: pdf_service)
    app = build_full_app(monkeypatch, storage)

    response = TestClient(app).post("/api/admin/papers/2604.00005/retry-analysis")

    assert response.status_code == 500
    assert response.json()["detail"] == "pdf failed"


# --- Task 4: Stats and conditional buttons ---


def test_admin_page_shows_stats_and_conditional_actions(monkeypatch) -> None:
    no_summary = make_paper("2604.00006", title="Needs Summary")
    summary_only = make_paper("2604.00007", title="Needs Analysis")
    summary_only.summary = PaperSummary(
        title_zh="已有摘要",
        abstract_zh="中文摘要",
        key_points=["点 1"],
        relevance_score=7.5,
    )
    complete = make_paper("2604.00008", title="Complete Paper")
    complete.summary = PaperSummary(
        title_zh="完整论文",
        abstract_zh="中文摘要",
        key_points=["点 1"],
        relevance_score=9.2,
        deep_analysis="# Deep Analysis\n\nDone",
    )

    storage = FakeStorage([no_summary, summary_only, complete])
    app = build_full_app(monkeypatch, storage)

    response = TestClient(app).get("/admin/papers?api_key=browser-key&date=2026-04-16")

    assert response.status_code == 200
    assert "今天共 3 篇" in response.text
    assert "2 篇有摘要" in response.text
    assert "1 篇有深度分析" in response.text
    assert "🔄 重试摘要" in response.text
    assert "🔄 重试深度分析" in response.text
    assert "📖 查看深度分析" in response.text
    assert 'data-api-key="browser-key"' in response.text
    assert 'value="2026-04-16"' in response.text


# --- Task 5: Date filtering ---


def test_admin_page_keeps_selected_date_in_form(monkeypatch) -> None:
    storage = FakeStorage([make_paper("2604.00009", title="Date Filter Paper")])
    app = build_full_app(monkeypatch, storage)

    response = TestClient(app).get("/admin/papers?api_key=browser-key&date=2026-04-15")

    assert response.status_code == 200
    assert 'value="2026-04-15"' in response.text
    assert 'name="api_key" value="browser-key"' in response.text
