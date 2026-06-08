# GlowSearch

GlowSearch는 화장품 상품을 빠르게 찾기 위한 Next.js + FastAPI 검색 앱입니다. 현재는 Olive Young 상품 검색을 중심으로 동작하지만, Musinsa, 공식 브랜드몰, managed scraping API, barcode/GTIN API, global discovery API를 같은 검색 파이프라인에 붙일 수 있게 설계했습니다.

서비스는 “검색 요청마다 모든 상품을 실시간으로 긁는 방식”이 아니라, 검증 가능한 source에서 상품을 수집하고 인덱스에 저장한 뒤 검색은 캐시/인덱스에서 먼저 빠르게 반환하는 방식으로 갑니다.

## 현재 배포

- Frontend: [https://glow-search.vercel.app/](https://glow-search.vercel.app/)
- Backend health: [https://glowsearch-backend.onrender.com/health](https://glowsearch-backend.onrender.com/health)
- Search API 예시: [https://glowsearch-backend.onrender.com/search?q=%EC%A0%A4&limit=2](https://glowsearch-backend.onrender.com/search?q=%EC%A0%A4&limit=2)

현재 배포 중인 백엔드 commit은 `/health`의 `release_sha`로 확인합니다.

## 지금까지 구현한 내용

- Next.js 검색 UI를 GlowSearch 브랜드에 맞게 정리했습니다.
- 검색 입력 UX를 개선하고, Enter 검색/검색 버튼 loading 상태/결과 카드 source badge를 붙일 수 있는 구조를 유지했습니다.
- FastAPI `/search` API 호환성을 유지했습니다.
- Olive Young 공개 JSON adapter를 기본 빠른 source로 사용합니다.
- 공식 Olive Young HTML collector와 browser collector는 준수/차단 리스크 때문에 기본 비활성화했습니다.
- 캐시와 SQLite product index를 먼저 조회하고, 부족하면 live source를 병렬로 보강합니다.
- `젤` 같은 넓은 단일 검색어는 verified-cache 1건에서 멈추지 않고 공개 adapter 결과를 기다리도록 보완했습니다.
- 넓은 단일 검색어의 관련 확장어는 첫 응답을 늦추지 않도록 background refresh로 넘깁니다.
- 단, `로션`처럼 1차 단어가 0개를 반환하는 경우에는 짧은 deadline 안에서 관련 확장어를 즉시 보강해 빈 화면을 줄입니다.
- live 결과는 백그라운드에서 인덱스에 저장되어 다음 검색부터 빠르게 재사용됩니다.
- 상품 record에 category, rating, review_count, description, options, sold_out, updated_at 필드를 추가했습니다.
- 원가와 현재가가 같으면 `sale_price`와 `discount_rate`를 노출하지 않습니다.
- source attribution, source label, source priority를 유지합니다.
- 안전 수집 CLI와 CSV export를 추가했습니다.
- diagnostics와 index status endpoint로 운영 상태를 확인할 수 있습니다.
- 결과가 많으면 프론트에서 48개씩 페이지 번호로 나눠 표시합니다.

## 중요한 데이터 원칙

- 상품 데이터는 원본 source가 제공한 값만 사용합니다.
- 원본에서 확인하지 못한 상품명, 가격, 이미지, 링크, 리뷰 수, 옵션은 만들지 않고 `null`로 둡니다.
- 같은 Olive Young `goodsNo`는 하나의 상품으로 dedupe합니다.
- 브랜드 영문명은 `backend/data/brand_registry.json`의 alias registry로 정규화합니다.
- source별 장애는 사용자에게 과하게 노출하지 않고 diagnostics에 남깁니다.
- anti-bot, Cloudflare, captcha, login wall, 403, 429, 503이 보이면 우회하지 않고 backoff 또는 중단합니다.

## Olive Young 조사 결과

- 공식 공개 Olive Young 상품 API나 공식 개발자 문서는 확인하지 못했습니다.
- `https://www.oliveyoung.co.kr/store/search/getSearchMain.do?query=...`와 상품 상세 URL은 웹 화면에서 쓰는 HTML 경로입니다. 공개 API 계약이 아니므로 대량 호출 대상으로 보지 않습니다.
- `https://www.oliveyoung.co.kr/robots.txt`는 named bot별 허용/지연 규칙이 있지만 `User-agent: *`는 전체 disallow입니다. 그래서 공식 HTML collector는 기본값에서 꺼져 있습니다.
- `https://us.oliveyoung.com/robots.txt`는 `/search`를 disallow하므로 US 검색 페이지 수집은 피합니다.
- 안전하게 접근 가능한 공개 GraphQL endpoint는 확인하지 못했습니다.
- 현재 기본 adapter는 기존 프로젝트가 사용하던 `https://mcp.aka.page/api/oliveyoung/products` 형식의 공개 JSON adapter입니다. 운영에서는 장애와 데이터 지연 가능성을 감안해야 합니다.

## 아키텍처

```text
Next.js UI
  -> FastAPI /search
  -> SearchService
  -> TTL cache 조회
  -> SQLiteProductIndexStore 조회
       - query별 rank 유지
       - 상품명/브랜드/카테고리/설명/옵션 search_text fallback
  -> 부족하면 primary query만 빠른 source로 병렬 실행
       - OliveYoungPublicApiCollector
       - LocalVerifiedCatalogCollector
       - ApifyOliveYoungCollector, optional
       - JsonApiProductCollector, optional managed/discovery/barcode adapter
       - OliveYoungCollector, opt-in HTML fallback
       - BrowserOliveYoungCollector, opt-in browser fallback
  -> SourcePolicy 적용
  -> ProductNormalizer 적용
  -> dedupe, filter, ranking
  -> SearchResponse 반환
  -> live 결과와 관련 확장어 refresh는 ProductIngestionAgent가 SQLite index에 저장
```

## 주요 모듈

```text
backend/app/
  api/              FastAPI route, health, diagnostics, index warmup
  cache/            TTL response cache
  core/             환경 설정
  data_collector/   source adapter
  indexing/         SQLite product index, ingestion agents
  ingestion/        safe rate limit/retry/backoff, ingestion pipeline, CSV export
  models/           ProductSourceRecord, ProductSearchResult
  normalizer/       브랜드/상품 정규화
  observability/    latency, cache/index/source metrics
  parser/           conservative Olive Young HTML parser
  search/           synonyms/search key
  service/          SearchService orchestration

backend/scripts/
  benchmark_search.py
  ingest_oliveyoung.py

frontend/src/
  app/              Next.js app UI
  lib/              API client
  types/            response types
```

## API

검색:

```bash
curl 'http://localhost:8000/search?q=젤&limit=24'
```

지원 파라미터:

| 파라미터 | 설명 |
| --- | --- |
| `q` | 검색어 |
| `keyword` | `q` alias |
| `brand` | 브랜드 필터 |
| `min_price` | 최소 가격 |
| `max_price` | 최대 가격 |
| `has_shade` | 색상/호수 존재 여부 |
| `limit` | 반환 개수, 1~480 |

응답 예시:

```json
{
  "query": "젤",
  "count": 2,
  "results": [
    {
      "brand_ko": "홀리카홀리카",
      "brand_en": "HOLIKA HOLIKA",
      "product_name_ko": "[NEW젤테일] 홀리카홀리카 마이페이브 피스 아이섀도우/젤테일/피스 빔/피스 밤",
      "category": null,
      "price": 4900,
      "original_price": 6000,
      "sale_price": 4900,
      "discount_rate": 18,
      "rating": null,
      "review_count": null,
      "currency": "KRW",
      "shade": null,
      "image_url": "https://...",
      "description": null,
      "options": null,
      "sold_out": false,
      "source_url": "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000174309",
      "source": "oliveyoung",
      "source_label": "Olive Young",
      "source_priority": 10,
      "updated_at": null
    }
  ],
  "source_errors": []
}
```

운영 상태:

```bash
curl https://glowsearch-backend.onrender.com/index/status
curl https://glowsearch-backend.onrender.com/diagnostics
```

## 로컬 실행

Backend:

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

Playwright fallback을 명시적으로 켤 때만 browser 설치가 필요합니다.

```bash
playwright install chromium
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

프론트 로컬 환경:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## 핵심 환경 변수

Backend:

```bash
GLOWSEARCH_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
GLOWSEARCH_CACHE_TTL_SECONDS=180
GLOWSEARCH_MAX_RESULTS=480
GLOWSEARCH_SOURCE_TIME_BUDGET_SECONDS=2.5
GLOWSEARCH_LIVE_COLLECT_DEADLINE_SECONDS=3.2
GLOWSEARCH_LIVE_FIRST_RESULT_GRACE_SECONDS=0.8
GLOWSEARCH_BACKGROUND_COLLECT_DEADLINE_SECONDS=18.0
GLOWSEARCH_RESULT_SOURCE_PREFIXES=oliveyoung,official,musinsa,managed,barcode,discovery,external

GLOWSEARCH_OLIVEYOUNG_PUBLIC_API_ENABLED=true
GLOWSEARCH_OLIVEYOUNG_PUBLIC_API_BASE_URL=https://mcp.aka.page
GLOWSEARCH_OLIVEYOUNG_PUBLIC_API_TIMEOUT_SECONDS=6.0
GLOWSEARCH_OLIVEYOUNG_PUBLIC_API_RETRY_ATTEMPTS=2
GLOWSEARCH_OLIVEYOUNG_PUBLIC_API_RETRY_BASE_DELAY_SECONDS=0.5
GLOWSEARCH_OLIVEYOUNG_PUBLIC_API_RETRY_MAX_DELAY_SECONDS=4.0
GLOWSEARCH_OLIVEYOUNG_PUBLIC_API_RATE_LIMIT_PER_SECOND=1.0
GLOWSEARCH_OLIVEYOUNG_HTML_COLLECTOR_ENABLED=false
GLOWSEARCH_OLIVEYOUNG_OFFICIAL_ORDER_ENABLED=true
GLOWSEARCH_OLIVEYOUNG_LIVE_SEARCH_REQUIRED=false

GLOWSEARCH_BROWSER_COLLECTOR_ENABLED=false
GLOWSEARCH_BROWSER_HEADLESS=true
GLOWSEARCH_BROWSER_TIMEOUT_SECONDS=25

GLOWSEARCH_PRODUCT_INDEX_ENABLED=true
GLOWSEARCH_PRODUCT_INDEX_PATH=backend/data/product_index.sqlite3
GLOWSEARCH_PRODUCT_INDEX_ADMIN_TOKEN=
GLOWSEARCH_PRODUCT_INDEX_MIN_RESULTS=1
GLOWSEARCH_PRODUCT_INDEX_BACKGROUND_REFRESH_ENABLED=true
GLOWSEARCH_PRODUCT_INDEX_WARMUP_ON_STARTUP=false
GLOWSEARCH_PRODUCT_INDEX_WARMUP_LIMIT=48
GLOWSEARCH_PRODUCT_INDEX_WARMUP_CONCURRENCY=2
GLOWSEARCH_PRODUCT_INDEX_MAX_SEED_QUERIES=80
GLOWSEARCH_PRODUCT_INDEX_DETAIL_ENRICHMENT_ENABLED=true
GLOWSEARCH_PRODUCT_INDEX_DETAIL_ENRICHMENT_MAX_RECORDS=12

GLOWSEARCH_APIFY_TOKEN=
GLOWSEARCH_APIFY_ACTOR_ID=kitschy_marigold/oliveyoung-search-scraper

GLOWSEARCH_MANAGED_SEARCH_API_ENABLED=false
GLOWSEARCH_MANAGED_SEARCH_API_BASE_URL=
GLOWSEARCH_GLOBAL_DISCOVERY_API_ENABLED=false
GLOWSEARCH_GLOBAL_DISCOVERY_API_BASE_URL=
GLOWSEARCH_BARCODE_LOOKUP_API_ENABLED=false
GLOWSEARCH_BARCODE_LOOKUP_API_BASE_URL=
```

Frontend:

```bash
NEXT_PUBLIC_API_BASE_URL=https://glowsearch-backend.onrender.com
```

## 안전 수집 CLI

로컬 개발이나 운영 job에서 공개 JSON adapter 기반으로 seed query를 수집하고 SQLite/CSV로 확인할 수 있습니다.

```bash
cd backend
.venv/bin/python scripts/ingest_oliveyoung.py --query 젤 --limit 48 --db-path data/product_index.sqlite3 --csv data/oliveyoung_export.csv
.venv/bin/python scripts/ingest_oliveyoung.py --use-default-seeds --max-queries 50 --limit 48 --db-path data/product_index.sqlite3
```

옵션:

| 옵션 | 설명 |
| --- | --- |
| `--query` | 수집할 검색어. 여러 번 지정 가능 |
| `--use-default-seeds` | 설정의 seed/category/brand query 사용 |
| `--max-queries` | 처리할 query 수 제한 |
| `--limit` | query별 수집 개수 |
| `--db-path` | SQLite index 경로 |
| `--csv` | CSV export 경로 |
| `--rate-limit` | 공개 adapter 초당 요청 수 |
| `--enrich-details` | 공식 상세 페이지 보강 opt-in |

기본 수집은 query별 48개, 초당 1 요청입니다. 180개 seed를 한 페이지씩 수집하면 raw 후보는 최대 8,640개이고 dedupe 후 실제 상품 수는 더 작습니다. `limit=480`은 query별 최대 10페이지까지 수집하므로 coverage는 늘지만 수집 시간과 source 부하도 같이 늘어납니다.

## 인덱스 운영

현재 SQLite는 로컬/소규모 운영용입니다.

Render free plan의 일반 filesystem은 ephemeral입니다. 현재처럼 `/tmp`에 SQLite를 두면 재배포, 재시작, cold start 이후 인덱스가 비거나 작아질 수 있습니다. 이 경우 검색 요청이 매번 live source를 기다리므로 느리고, source timeout이 나면 결과가 적게 나옵니다.

권장 순서:

1. Render paid service로 올리고 persistent disk를 `/var/data`에 연결
2. 상품 수와 source가 늘면 Postgres full-text search로 이전
3. prefix/typo search가 중요해지면 Meilisearch 또는 Typesense 검토
4. 대규모 검색/분석이 필요해지면 OpenSearch 검토

Persistent disk를 붙이면 backend 환경 변수는 다음처럼 바꿉니다.

```bash
GLOWSEARCH_PRODUCT_INDEX_PATH=/var/data/glowsearch/product_index.sqlite3
```

Render Dashboard 절차:

1. Backend service를 paid plan으로 변경합니다.
2. Disks에서 persistent disk를 추가합니다.
3. Mount path를 `/var/data`로 설정합니다.
4. `GLOWSEARCH_PRODUCT_INDEX_PATH`를 `/var/data/glowsearch/product_index.sqlite3`로 설정합니다.
5. 배포 후 `/index/warm` 또는 startup warmup으로 seed index를 채웁니다.

Render docs 기준 persistent disk는 유료 web service, private service, background worker에 붙일 수 있고, 지정한 mount path 아래 데이터만 재배포/재시작 후 보존됩니다.

Render에서 `GLOWSEARCH_PRODUCT_INDEX_ADMIN_TOKEN`을 설정하면 warmup을 수동 또는 Cron으로 실행할 수 있습니다.

```bash
curl -X POST "https://glowsearch-backend.onrender.com/index/warm?token=$GLOWSEARCH_PRODUCT_INDEX_ADMIN_TOKEN&limit=48"
curl -X POST "https://glowsearch-backend.onrender.com/index/warm?token=$GLOWSEARCH_PRODUCT_INDEX_ADMIN_TOKEN&q=뮤드&q=롬앤&limit=48&wait=true"
```

현재 `render.yaml`은 cold start 이후에도 최소 coverage를 만들기 위해 낮은 부하의 startup warmup을 켭니다.

```bash
GLOWSEARCH_PRODUCT_INDEX_WARMUP_ON_STARTUP=true
GLOWSEARCH_PRODUCT_INDEX_WARMUP_CONCURRENCY=1
GLOWSEARCH_PRODUCT_INDEX_MAX_SEED_QUERIES=80
GLOWSEARCH_PRODUCT_INDEX_WARMUP_LIMIT=48
```

이 설정은 persistent disk를 붙이기 전 임시 보완입니다. 장기적으로는 persistent disk 또는 Postgres가 필요합니다.

## 운영/법무 주의

- robots.txt, 약관, rate limit, 제휴/사용 권한을 확인하지 않은 대량 수집은 실행하지 않습니다.
- 403, 429, 503, Cloudflare, captcha, login wall이 보이면 우회하지 않습니다.
- Playwright/Selenium은 endpoint discovery 또는 보수적 fallback 용도만 허용합니다.
- fingerprint 우회, captcha 우회, anti-bot 회피 코드는 넣지 않습니다.
- production-grade 전체 Olive Young coverage는 공식/제휴 데이터, managed scraping API, 또는 명시적으로 허용된 데이터 공급자를 우선 검토합니다.

## 배포

- Frontend: Vercel
- Backend: Render Docker web service

프론트 배포 환경:

```bash
NEXT_PUBLIC_API_BASE_URL=https://glowsearch-backend.onrender.com
```

Render backend에는 Backend 환경 변수를 등록합니다.

Render 자동 배포가 GitHub push를 바로 반영하지 않으면 deploy hook을 사용합니다.

1. Render Dashboard에서 backend service를 엽니다.
2. Settings의 Deploy Hook URL을 복사합니다.
3. GitHub repository Settings > Secrets and variables > Actions에 `RENDER_DEPLOY_HOOK_URL` secret을 추가합니다.
4. 이후 `main` push 후 deploy hook 또는 GitHub Action으로 Render 배포를 트리거합니다.

배포 확인:

```bash
curl https://glowsearch-backend.onrender.com/health
```

## 검증

Backend:

```bash
cd backend
.venv/bin/python -m ruff check app tests scripts
.venv/bin/python -m pytest
```

Frontend:

```bash
cd frontend
npm run typecheck
npm run build
```

Benchmark:

```bash
cd backend
.venv/bin/python scripts/benchmark_search.py --base-url http://localhost:8000 --repeat 3
.venv/bin/python scripts/benchmark_search.py --base-url https://glowsearch-backend.onrender.com --repeat 3
```

최근 검증 결과:

- backend ruff 통과
- backend pytest 86 passed
- frontend typecheck 통과
- frontend build 통과
- Render health의 `release_sha`로 현재 배포 commit 확인
- `젤`, `로션` 검색에서 Olive Young source 결과 반환 확인
