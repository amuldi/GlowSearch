# GlowSearch

Production-oriented cosmetics search platform using FastAPI and Next.js. The backend collects Olive Young product data, parses only source-provided fields, normalizes the response, and returns `null` for missing values.

## Folder Structure

```text
GlowSearch/
  backend/
    app/
      api/              FastAPI routes
      cache/            TTL cache
      core/             settings
      data_collector/   Olive Young source adapters
      models/           response/source schemas
      normalizer/       brand/product normalization
      parser/           source parsers
      service/          search orchestration
    data/
      brand_registry.json
    tests/
  frontend/
    src/app/            Next.js app router UI
    src/lib/            API client
    src/types/          shared frontend types
```

## Data Strategy

- Primary source: Korean Olive Young search page. The collector requests 48-item pages and paginates up to the configured result limit.
- Local fallback: Playwright opens Olive Young search/detail pages in Chromium when direct HTTP collection is blocked.
- Optional managed fallback: Apify Olive Young search actor when `GLOWSEARCH_APIFY_TOKEN` is configured.
- Musinsa product fallback: when Olive Young live collection is blocked, Musinsa's public product search endpoint can return verified product name, normal price, image URL, and source URL for brands/products listed there.
- Source merge: fast Olive Young sources and Musinsa are merged with duplicate removal instead of stopping at the first successful source.
- Brand English name is resolved only when:
  - Olive Young already returns a Latin brand name, or
  - `backend/data/brand_registry.json` contains a verified mapping from Musinsa, Instagram, or the official brand website.
- Musinsa brand fallback: when a Korean brand name is parsed from Olive Young but is not in the local registry, the backend queries Musinsa's public brand search endpoint and uses `brandNameEng` only on an exact brand match.
- Browser detail enrichment follows smaller Olive Young result sets to improve official product name, displayed official price, image, and source URL without exhausting the free deployment memory limit.
- Results are returned only when the core fields `brand_en`, `product_name_ko`, and `price` are all verified. Other missing values are returned as `null`. Values are never guessed.
- When Olive Young blocks live collection, `backend/data/verified_products.json` is used as a last-resort verified cache. This cache contains only products previously observed from Olive Young responses and should be expanded from verified source data, not guessed.
- If Olive Young blocks both direct HTTP and browser access, the API returns an empty result set with `source_errors`; it never fabricates product data.

Example brand registry entry:

```json
{
  "entries": [
    {
      "official_en": "BE READY",
      "aliases": ["비레디"],
      "sources": ["https://www.instagram.com/bereadyofficial/"]
    }
  ]
}
```

## Backend

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

API-key-free local mode is enabled by default:

```bash
GLOWSEARCH_BROWSER_COLLECTOR_ENABLED=true
GLOWSEARCH_BROWSER_HEADLESS=true
GLOWSEARCH_BROWSER_TIMEOUT_SECONDS=25
GLOWSEARCH_MUSINSA_BRAND_LOOKUP_ENABLED=true
GLOWSEARCH_MUSINSA_PRODUCT_COLLECTOR_ENABLED=true
GLOWSEARCH_MUSINSA_TIMEOUT_SECONDS=2.5
```

Set `GLOWSEARCH_BROWSER_HEADLESS=false` if you want to see the Chromium window during local debugging.

Search endpoint:

```bash
curl 'http://localhost:8000/search?q=틴트&has_shade=true'
```

Supported query params:

- `q` or `keyword`: search keyword
- `brand`: English brand filter
- `min_price`: minimum KRW price
- `max_price`: maximum KRW price
- `has_shade`: `true` or `false`
- `limit`: `1` to `200`

Example API response:

```json
{
  "query": "없는검색어",
  "count": 0,
  "results": [],
  "source_errors": []
}
```

Each result uses this shape. Values come only from the live source or verified brand registry:

```json
{
  "brand_en": "string | null",
  "product_name_ko": "string | null",
  "price": "number | null",
  "shade": "string | null",
  "image_url": "string | null",
  "source_url": "string | null",
  "source": "oliveyoung"
}
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

Set `NEXT_PUBLIC_API_BASE_URL` if the backend is not running on `http://localhost:8000`.

## Deployment

Recommended deployment split:

- Backend: Render Docker web service
- Frontend: Vercel Next.js app

This project includes:

- `backend/Dockerfile`: FastAPI runtime with Playwright Chromium support
- `render.yaml`: Render blueprint for the backend
- `frontend/.env.example`: frontend API URL example

### 1. Push The Project To GitHub

Render and Vercel both deploy most easily from a GitHub repository.

### 2. Deploy Backend On Render

Use Render's Blueprint or create a Docker web service manually.

If using the Blueprint, Render reads `render.yaml`.

If creating manually:

- Root directory: `backend`
- Environment: Docker
- Health check path: `/health`

Render provides the `PORT` environment variable automatically. The Dockerfile starts:

```bash
uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Recommended backend environment variables:

```bash
GLOWSEARCH_BROWSER_COLLECTOR_ENABLED=true
GLOWSEARCH_BROWSER_HEADLESS=true
GLOWSEARCH_BROWSER_TIMEOUT_SECONDS=25
GLOWSEARCH_MUSINSA_BRAND_LOOKUP_ENABLED=true
GLOWSEARCH_MUSINSA_PRODUCT_COLLECTOR_ENABLED=true
GLOWSEARCH_MUSINSA_BEAUTY_CATEGORY_CODE=104
GLOWSEARCH_CORS_ORIGINS=https://your-frontend-domain.vercel.app
```

After deploy, verify:

```bash
curl https://your-backend-domain.onrender.com/health
curl 'https://your-backend-domain.onrender.com/search?q=컨실러&limit=3'
```

### 3. Deploy Frontend On Vercel

Import the same GitHub repository into Vercel.

Set:

- Root Directory: `frontend`
- Framework Preset: Next.js
- Build Command: `npm run build`

Add this Vercel environment variable:

```bash
NEXT_PUBLIC_API_BASE_URL=https://your-backend-domain.onrender.com
```

Redeploy the frontend after changing `NEXT_PUBLIC_API_BASE_URL`.

### 4. Update Backend CORS

After Vercel gives you the final frontend URL, update the Render backend:

```bash
GLOWSEARCH_CORS_ORIGINS=https://your-frontend-domain.vercel.app
```

If you also need local development:

```bash
GLOWSEARCH_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,https://your-frontend-domain.vercel.app
```

### Deployment Limits

This app uses live public source collection. Olive Young or Musinsa can rate-limit, block, or change markup/API responses. The app does not fabricate missing values; blocked or missing source data can return empty results.

## Validation

```bash
cd backend
pytest
ruff check app tests

cd ../frontend
npm run typecheck
npm run build
```
