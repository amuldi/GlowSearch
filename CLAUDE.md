# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend (Python / FastAPI)
```bash
cd backend

# Dev server
.venv/bin/uvicorn app.main:app --reload

# Run all tests
.venv/bin/pytest

# Run a single test file
.venv/bin/pytest tests/test_service.py

# Run a single test
.venv/bin/pytest tests/test_service.py::test_search_returns_results

# Lint
.venv/bin/ruff check .
.venv/bin/ruff format .
```

### Frontend (Next.js / TypeScript)
```bash
cd frontend

npm run dev        # dev server (port 3000)
npm run build      # production build
npm run typecheck  # tsc --noEmit
npm run lint       # eslint
```

## Architecture

### Request Flow

```
User search query
  → GET /search?q=...  (FastAPI, routes.py)
  → SearchService.search()
      1. Check AsyncTTLCache (180s TTL)
      2. Read SQLite FTS5 index (ProductIndexStore) — fast path
      3. If index thin: kick off live collectors in background
  → Normalize results (ProductNormalizer + BrandRegistry)
  → Return ProductSearchResult[]
```

### Key Layers

**`app/search_engine/`** — SQLite FTS5 index abstraction.
- `sqlite_provider.py` is the live implementation; `typesense_provider.py` is unused.
- `document.py` defines `SearchDocument` (the indexed shape).
- `query.py` / `ranking.py` / `intent.py` handle query parsing and result scoring.

**`app/service/search_service.py`** — Orchestrator. Merges index results with live collector results, manages background refresh, deduplication, and ranking. All search logic lives here.

**`app/data_collector/`** — Source adapters. `base.py` defines `ProductCollector` protocol. Active ones: `oliveyoung.py`, `oliveyoung_api.py` (public API via `mcp.aka.page`), `local_catalog.py` (reads verified_products.json). Most others are gated by settings flags.

**`app/normalizer/`** — `ProductNormalizer` applies brand registry lookups, display name cleaning (strips volume/SPF/bundle suffixes), and canonical ID assignment. Called on every ingest and search result.

**`app/indexing/`** — `ProductIngestionAgent` writes collected records into the SQLite index. `SourceDiscoveryAgent` schedules background coverage queries.

**`app/ingestion/`** — Pipeline logic for catalog enrichment: quality checks, coverage tracking, and the Olive Young ingestion pipeline.

**`app/editor/`** — Editor batch mode: parses free-text lines (extracts brand, product name, shade code) then matches each against the search index.

### Data Files (`backend/data/`)

| File | Purpose |
|---|---|
| `product_index.sqlite3` | Main FTS5 search index (runtime) |
| `verified_products.json` | Manually curated canonical product catalog — source of truth for display names and English names |
| `brand_registry.json` | Brand Korean↔English name + official domain mappings |
| `search_synonyms.json` | Query expansion synonyms |
| `search_intents.json` | Category intent mappings |

### Frontend

Single-page app (`frontend/src/app/page.tsx`). Two modes toggled by UI:
- **Search mode** — standard search with autocomplete and pagination.
- **Editor mode** (`?mode=editor`) — paste multi-line product list → per-line batch matching via `/editor/batch`. Results show ranked candidates per line.

API client is in `frontend/src/lib/api.ts`. Types in `frontend/src/types/product.ts`.

### Settings / Environment

All backend settings live in `app/core/config.py` (`Settings` class, `pydantic-settings`). Env vars are prefixed `GLOWSEARCH_`. Local overrides go in `backend/.env`. Most external source adapters (Musinsa, OliveYoung Global, Apify, etc.) are disabled by default and require both an `_enabled=true` flag and a `_base_url`.

### Deployment

- Frontend → Vercel (`frontend/.vercel/`)
- Backend → Render (`render.yaml`, `backend/Dockerfile`)
- Release SHA exposed at `GET /health` → `release_sha` field
