"""Lightweight HTML validation UI — superseded by the React web UI in Phase 6.

.. deprecated::
    This module is retained for reference only.  The ``enable_ui`` parameter
    was removed from :func:`~semantic_search.runtime.api.create_app` in
    Phase 6.  Use the React frontend in ``frontend/`` instead, which serves
    both Standard and Premium tiers with tier-gated analytics.

    ``mount_ui`` may be invoked manually on any FastAPI app instance if a
    quick fallback HTML interface is needed, but it is not recommended for
    production use.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Semantic Search &mdash; Validation UI</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      max-width: 860px; margin: 0 auto; padding: 32px 16px;
      background: #f8f9fa; color: #212529;
    }
    h1  { font-size: 1.4rem; font-weight: 600; margin: 0 0 4px; }
    .subtitle { color: #6c757d; font-size: 0.85rem; margin: 0 0 24px; }
    .search-row { display: flex; gap: 8px; margin-bottom: 16px; }
    #query {
      flex: 1; padding: 10px 14px; font-size: 1rem;
      border: 1px solid #ced4da; border-radius: 6px; background: #fff;
    }
    #query:focus {
      outline: none; border-color: #0d6efd;
      box-shadow: 0 0 0 3px rgba(13,110,253,.15);
    }
    .topk-label {
      display: flex; align-items: center; gap: 6px;
      font-size: 0.9rem; color: #495057; white-space: nowrap;
    }
    #top-k {
      width: 70px; padding: 10px 8px; font-size: 0.9rem;
      border: 1px solid #ced4da; border-radius: 6px; text-align: center;
    }
    #search-btn {
      padding: 10px 20px; background: #0d6efd; color: #fff;
      border: none; border-radius: 6px; cursor: pointer;
      font-size: 1rem; font-weight: 500; transition: background 0.15s;
      white-space: nowrap;
    }
    #search-btn:hover   { background: #0b5ed7; }
    #search-btn:disabled { background: #6ea8fe; cursor: not-allowed; }
    #status { min-height: 22px; font-size: 0.85rem; color: #6c757d; margin-bottom: 12px; }
    .error-msg { color: #dc3545; }
    #results { list-style: none; padding: 0; margin: 0; }
    .result-card {
      background: #fff; border: 1px solid #dee2e6; border-radius: 8px;
      padding: 14px 16px; margin-bottom: 10px;
    }
    .result-header { display: flex; align-items: baseline; gap: 10px; }
    .rank          { font-size: 0.8rem; color: #adb5bd; min-width: 24px; }
    .record-id     { font-weight: 600; font-size: 0.95rem; word-break: break-all; }
    .score-badge   {
      margin-left: auto; background: #e7f1ff; color: #0d6efd;
      font-size: 0.78rem; padding: 2px 8px; border-radius: 20px; white-space: nowrap;
    }
    .metadata-row  {
      margin-top: 8px; font-size: 0.8rem; color: #6c757d;
      display: flex; flex-wrap: wrap; gap: 6px;
    }
    .meta-tag { background: #f1f3f5; border-radius: 4px; padding: 2px 7px; }
    .no-results { color: #6c757d; font-style: italic; text-align: center; padding: 24px 0; }
  </style>
</head>
<body>
  <h1>Semantic Search Validation UI</h1>
  <p class="subtitle">
    Issues queries directly against the running
    <code>/v1/search</code> endpoint.
  </p>
  <form id="search-form">
    <div class="search-row">
      <input
        id="query"
        type="text"
        placeholder="Enter a natural-language query&hellip;"
        autocomplete="off"
        required
      />
      <label class="topk-label">
        Top&#8209;K
        <input id="top-k" type="number" min="1" max="200" value="10" />
      </label>
      <button id="search-btn" type="submit">Search</button>
    </div>
  </form>
  <div id="status"></div>
  <ul id="results"></ul>

  <script>
    var form    = document.getElementById('search-form');
    var qInput  = document.getElementById('query');
    var kInput  = document.getElementById('top-k');
    var btn     = document.getElementById('search-btn');
    var status  = document.getElementById('status');
    var results = document.getElementById('results');

    function esc(str) {
      return String(str).replace(/[&<>"']/g, function(c) {
        return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
      });
    }

    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      var query = qInput.value.trim();
      var topK  = Math.max(1, Math.min(200, parseInt(kInput.value, 10) || 10));
      if (!query) { return; }

      btn.disabled    = true;
      status.innerHTML = 'Searching&hellip;';
      results.innerHTML = '';

      try {
        var resp = await fetch('/v1/search', {
          method:  'POST',
          headers: {'Content-Type': 'application/json'},
          body:    JSON.stringify({query: query, top_k: topK})
        });
        var data = await resp.json();

        if (!resp.ok) {
          status.innerHTML =
            '<span class="error-msg">Error ' + resp.status + ': ' +
            esc(data.detail || 'Unknown error') + '</span>';
          return;
        }

        var parts = [
          data.total_results + ' result(s)',
          data.elapsed_ms.toFixed(1) + '&nbsp;ms'
        ];
        if (data.embedding_model) {
          parts.push('model: ' + esc(data.embedding_model));
        }
        status.innerHTML = parts.join(' &nbsp;&middot;&nbsp; ');

        if (data.results.length === 0) {
          results.innerHTML =
            '<li class="no-results">No matches found for this query.</li>';
          return;
        }

        data.results.forEach(function (item, idx) {
          var li      = document.createElement('li');
          li.className = 'result-card';
          var entries  = Object.entries(item.metadata || {});
          var metaHtml = entries.length
            ? '<div class="metadata-row">' +
              entries.map(function(kv) {
                return '<span class="meta-tag">' +
                       esc(kv[0]) + ': ' + esc(String(kv[1])) +
                       '</span>';
              }).join('') + '</div>'
            : '';
          li.innerHTML =
            '<div class="result-header">' +
              '<span class="rank">#' + (idx + 1) + '</span>' +
              '<span class="record-id">' + esc(item.record_id) + '</span>' +
              '<span class="score-badge">score&nbsp;' +
                item.score.toFixed(4) + '</span>' +
            '</div>' + metaHtml;
          results.appendChild(li);
        });

      } catch (err) {
        status.innerHTML =
          '<span class="error-msg">Request failed: ' +
          esc(err.message) + '</span>';
      } finally {
        btn.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def mount_ui(app: FastAPI, *, path: str = "/ui") -> None:
    """Register the validation UI route on a FastAPI application.

    The route renders a single-page HTML interface that submits queries to the
    ``/v1/search`` endpoint via JavaScript ``fetch``.  It is excluded from the
    OpenAPI schema so it does not appear in auto-generated API docs.

    Args:
        app: FastAPI application instance on which the route is registered.
        path: URL path at which the UI is served.  Defaults to ``"/ui"``.
            Must start with ``"/"``; must not conflict with existing routes.

    Raises:
        ValueError: If ``path`` does not start with ``"/"``.

    Example::

        from fastapi import FastAPI
        from semantic_search.runtime.ui import mount_ui

        app = FastAPI()
        mount_ui(app, path="/ui")
    """
    if not path.startswith("/"):
        raise ValueError(f"UI path must start with '/'; got {path!r}")

    @app.get(
        path,
        response_class=HTMLResponse,
        include_in_schema=False,
        summary="Validation UI",
    )
    def _serve_ui() -> HTMLResponse:  # noqa: WPS430 — nested function is intentional
        """Serve the single-page validation UI."""
        return HTMLResponse(content=_HTML_TEMPLATE)


__all__ = ["mount_ui"]
