# Admin Papers Page Design

**Date:** 2026-04-16  
**Status:** Approved  
**Type:** Feature Addition

## Overview

Add a web-based admin page for viewing today's paper list and retrying failed AI processing tasks (summary generation and deep analysis).

## Requirements

### Functional Requirements

1. **Paper List View**
   - Display papers fetched today (default) or a specific date
   - Show paper metadata: title (Chinese if available), original title, authors, date, categories
   - Display AI processing status: summary (✅/❌), deep analysis (✅/❌)
   - Sort by published date (newest first)

2. **Retry Operations**
   - Retry AI summary generation for papers without summaries
   - Retry PDF deep analysis for papers without deep analysis
   - Both operations should be independently triggerable

3. **Authentication**
   - Require authentication (API Key or JWT)
   - Personal admin backend (not public)

4. **Navigation**
   - Links to arXiv abstract page
   - Links to PDF download
   - Links to view deep analysis (if available)

### Non-Functional Requirements

- Responsive design (mobile-friendly)
- Dark mode support
- Consistent with existing `analysis_view.html` design language
- Minimal JavaScript (progressive enhancement)

## Technical Design

### Architecture

**Approach:** Server-side rendering with FastAPI + Jinja2

**Rationale:**
- Zero frontend build tooling required
- Consistent with existing codebase (`analysis_view.html`)
- Reuses existing API routes and authentication
- Suitable for personal admin backend use case

### Routes

#### 1. Admin Page Route

```
GET /admin/papers
```

**Query Parameters:**
- `date` (optional): View papers from specific date (format: `YYYY-MM-DD`)

**Authentication:** Required (`require_auth` dependency)

**Response:** HTML page rendered from `admin_papers.html` template

**Logic:**
1. Parse `date` parameter or default to today (UTC)
2. Call `storage.get_papers_by_date(start, end)`
3. Sort by `published_at` descending
4. Render template with paper list

#### 2. Retry Summary Endpoint

```
POST /api/admin/papers/{arxiv_id}/retry-summary
```

**Authentication:** Required

**Logic:**
1. Validate `arxiv_id` format
2. Fetch paper from storage
3. Call `summarize_paper(paper)`
4. Update database with `storage.update_summary(guid, summary)`
5. Return JSON: `{"status": "success", "message": "Summary generated"}`

**Error Handling:**
- 400: Invalid arXiv ID format
- 404: Paper not found
- 500: AI processing failed (return error message)

#### 3. Retry Deep Analysis Endpoint

```
POST /api/admin/papers/{arxiv_id}/retry-analysis
```

**Authentication:** Required

**Logic:**
1. Validate `arxiv_id` format
2. Fetch paper from storage
3. Call `pdf_service.analyze_paper(arxiv_id, force=True)`
4. Return JSON: `{"status": "success", "message": "Deep analysis completed"}`

**Error Handling:**
- 400: Invalid arXiv ID format
- 404: Paper not found
- 500: PDF analysis failed (return error message)

### Data Flow

```
User → GET /admin/papers
  ↓
require_auth (API Key / JWT)
  ↓
storage.get_papers_by_date(today)
  ↓
Jinja2 render admin_papers.html
  ↓
User clicks "🔄 重试摘要"
  ↓
JavaScript POST /api/admin/papers/{arxiv_id}/retry-summary
  ↓
summarize_paper() → storage.update_summary()
  ↓
Return JSON {"status": "success"}
  ↓
Frontend: location.reload()
```

### Frontend Implementation

**Template:** `src/citeo/api/templates/admin_papers.html`

**Layout:** Compact list (approved design)

**Structure:**
```html
<header>
  <h1>Citeo 论文管理</h1>
  <input type="date" id="dateFilter" />
  <div class="stats">今天共 X 篇 | Y 篇有摘要 | Z 篇有深度分析</div>
</header>

<main>
  {% for paper in papers %}
  <article class="paper-item">
    <h3>{{ paper.summary.title_zh or paper.title }}</h3>
    <p class="original-title">{{ paper.title }}</p>
    <div class="meta">
      📅 {{ paper.published_at }} | 
      👤 {{ paper.authors[:3]|join(', ') }} | 
      🏷️ {{ paper.categories[:3]|join(', ') }}
    </div>
    <div class="status">
      {% if paper.summary %}
        <span class="badge success">✅ 摘要</span>
      {% else %}
        <span class="badge error">❌ 摘要</span>
      {% endif %}
      
      {% if paper.summary and paper.summary.deep_analysis %}
        <span class="badge success">✅ 深度分析</span>
      {% else %}
        <span class="badge error">❌ 深度分析</span>
      {% endif %}
    </div>
    <div class="actions">
      <a href="{{ paper.abs_url }}" target="_blank">arXiv</a>
      <a href="{{ paper.pdf_url }}" target="_blank">PDF</a>
      
      {% if not paper.summary %}
        <button onclick="retrySummary('{{ paper.arxiv_id }}')">🔄 重试摘要</button>
      {% endif %}
      
      {% if not (paper.summary and paper.summary.deep_analysis) %}
        <button onclick="retryAnalysis('{{ paper.arxiv_id }}')">🔄 重试深度分析</button>
      {% endif %}
      
      {% if paper.summary and paper.summary.deep_analysis %}
        <a href="/api/view/{{ paper.arxiv_id }}">📖 查看深度分析</a>
      {% endif %}
    </div>
  </article>
  {% endfor %}
</main>
```

**JavaScript (minimal):**
```javascript
// Get auth token from sessionStorage or cookie
function getAuthToken() {
  return sessionStorage.getItem('api_key') || 
         localStorage.getItem('jwt_token') ||
         getCookie('access_token');
}

async function retrySummary(arxivId) {
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = '处理中...';
  
  try {
    const response = await fetch(`/api/admin/papers/${arxivId}/retry-summary`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${getAuthToken()}`,
        'Content-Type': 'application/json'
      }
    });
    
    if (response.ok) {
      location.reload();
    } else {
      const error = await response.json();
      alert(`重试失败: ${error.detail}`);
      btn.disabled = false;
      btn.textContent = '🔄 重试摘要';
    }
  } catch (err) {
    alert(`网络错误: ${err.message}`);
    btn.disabled = false;
    btn.textContent = '🔄 重试摘要';
  }
}

async function retryAnalysis(arxivId) {
  // Similar logic to retrySummary
}

// Date filter
document.getElementById('dateFilter').addEventListener('change', (e) => {
  const date = e.target.value;
  window.location.href = `/admin/papers?date=${date}`;
});
```

**CSS:**
- Reuse CSS variables from `analysis_view.html`
- Compact list styling with clear visual hierarchy
- Status badges with color coding (green = success, red = error)
- Responsive button layout

### Status Detection Logic

**Summary Status:**
```python
has_summary = paper.summary is not None
```

**Deep Analysis Status:**
```python
has_deep_analysis = (
    paper.summary is not None and 
    paper.summary.deep_analysis is not None
)
```

### Security

1. **Authentication:** All admin routes require `require_auth` dependency
2. **Input Validation:** Reuse existing `_validate_arxiv_id()` function
3. **CSRF Protection:** JWT tokens include CSRF protection
4. **Rate Limiting:** Apply existing rate limiter to retry endpoints (reuse `/analyze` config)

### Error Handling

**Frontend:**
- 401 Unauthorized → Redirect to login or prompt for API key
- 404 Not Found → Display "论文不存在" message
- 500 Server Error → Display error message with retry button

**Backend:**
- Wrap AI calls in try-except
- Log errors with structlog
- Return meaningful error messages in JSON response

## Implementation Plan

### Phase 1: Backend Routes
1. Add `GET /admin/papers` route handler
2. Add `POST /api/admin/papers/{arxiv_id}/retry-summary` endpoint
3. Add `POST /api/admin/papers/{arxiv_id}/retry-analysis` endpoint
4. Add input validation and error handling

### Phase 2: Frontend Template
1. Create `admin_papers.html` template
2. Implement compact list layout
3. Add status badges and action buttons
4. Style with CSS (reuse existing design system)

### Phase 3: JavaScript Interactions
1. Implement `retrySummary()` function
2. Implement `retryAnalysis()` function
3. Add date filter handler
4. Add authentication token handling

### Phase 4: Testing
1. Test with papers in different states (no summary, no analysis, both)
2. Test retry operations (success and failure cases)
3. Test authentication (API Key and JWT)
4. Test date filtering
5. Test responsive layout on mobile

## Open Questions

None - design approved by user.

## Future Enhancements (Out of Scope)

- Batch retry operations (select multiple papers)
- Filter by status (show only failed papers)
- Search by keyword or category
- Export paper list to CSV
- Real-time status updates (WebSocket)

## References

- Existing template: `src/citeo/api/templates/analysis_view.html`
- Existing routes: `src/citeo/api/routes.py`
- Storage interface: `src/citeo/storage/base.py`
- AI services: `src/citeo/ai/summarizer.py`, `src/citeo/services/pdf_service.py`
