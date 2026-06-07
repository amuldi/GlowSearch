# GlowSearch

Olive Young을 우선 소스로 사용하면서 Musinsa, 공식 브랜드 사이트, managed scraping API, barcode/GTIN API, global discovery API를 같은 검색 파이프라인에 붙일 수 있는 화장품 검색 앱입니다.

서비스 주소: [https://glow-search.vercel.app/](https://glow-search.vercel.app/)

## 현재 방향

- 검색 결과는 Olive Young을 최우선으로 보지만, source policy가 허용한 Musinsa, 공식 브랜드, managed API, barcode/GTIN, discovery API 결과도 같은 `/search` 응답으로 반환할 수 있습니다.
- 원본에서 확인하지 못한 값은 만들지 않고 `null`로 둡니다.
- 검색은 캐시와 SQLite 제품 인덱스에서 먼저 빠르게 반환하고, 부족하면 빠른 live source를 병렬 보강합니다.
- 실시간 수집 결과는 백그라운드에서 상세 페이지로 보강한 뒤 인덱스에 저장되어 다음 검색부터 빠르게 재사용됩니다.
- 기본 검색은 인덱스/캐시 우선입니다. `GLOWSEARCH_OLIVEYOUNG_LIVE_SEARCH_REQUIRED=true`일 때만 매 요청에서 실시간 공식 검색을 강제합니다.
- 빠른 소스는 병렬로 실행하고, 브라우저 수집은 기본 비활성화합니다. 꼭 필요할 때만 `GLOWSEARCH_BROWSER_COLLECTOR_ENABLED=true`로 켭니다.
- 같은 Olive Young `goodsNo`는 하나의 상품으로 합칩니다. 다른 source는 source attribution과 priority를 유지합니다.
- 브랜드 영문명은 `backend/data/brand_registry.json`의 공식 alias를 기준으로 정규화합니다.

## 검색 파이프라인

```text
Next.js 검색 화면
  -> FastAPI /search
  -> SearchService
  -> SQLiteProductIndexStore에서 후보 조회
       - 저장된 Olive Young 공식 검색 순서(query rank)를 유지
       - 공식 검색 실패/부족 시 상품명/브랜드/호수 텍스트 인덱스를 사용
  -> 인덱스에 충분한 결과가 있으면 즉시 반환하고 백그라운드 refresh 예약
  -> 인덱스가 부족하거나 live 강제 모드면 빠른 수집기 병렬 실행
  -> 빠른 수집기 병렬 실행
       - OliveYoungCollector: 올리브영 HTML 검색
       - OliveYoungPublicApiCollector: public API 가격/이미지
       - LocalVerifiedCatalogCollector: 검증된 로컬 보조 데이터
       - ApifyOliveYoungCollector: APIFY_TOKEN이 있을 때만 사용
       - JsonApiProductCollector: configured managed/search/barcode API normalized JSON adapter
  -> SourcePolicy가 source allow-list, label, priority를 적용
  -> 공식 HTML 결과가 있으면 해당 순서를 보존하고 보조 소스는 같은 상품 보강 또는 뒤쪽 보충에 사용
  -> 브라우저 수집은 기본 검색 경로에서 제외하고, 환경변수로 명시적으로 켠 경우에만 fallback
  -> ProductIngestionAgent가 live 결과를 OliveYoungDetailEnrichmentAgent로 상세 보강
  -> SQLite 인덱스에 상품과 쿼리별 공식 검색 순서 저장
  -> ProductNormalizer
  -> 중복 제거, 필터, 랭킹
  -> ProductSearchResult 반환
```

## 폴더 구조

```text
GlowSearch/
  backend/
    app/
      api/              FastAPI 라우트
      cache/            TTL 응답 캐시
      core/             환경 설정
      data_collector/   Olive Young 수집기와 fallback
      indexing/         제품 인덱스 저장소와 수집 에이전트
      models/           API 응답/수집 스키마
      normalizer/       브랜드/상품 정규화
      observability/    검색/소스/인덱스 메트릭
      parser/           HTML 파서
      search/           검색 동의어와 key 정규화
      service/          검색 흐름 조립
    data/
      brand_registry.json
      verified_products.json
    tests/
  frontend/
    src/app/            Next.js 화면
    src/lib/            API 클라이언트
    src/types/          프론트 타입
```

## 로컬 실행

Backend:

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

프론트에서 사용할 백엔드 주소:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## API

```bash
curl 'http://localhost:8000/search?q=선크림&limit=24'
```

지원 파라미터:

| 파라미터 | 설명 |
| --- | --- |
| `q` | 검색어 |
| `keyword` | `q`와 같은 alias |
| `brand` | 브랜드 필터 |
| `min_price` | 최소 가격 |
| `max_price` | 최대 가격 |
| `has_shade` | 색상/호수 존재 여부 |
| `limit` | 반환 개수, 1~480 |

응답 예시:

```json
{
  "query": "선크림",
  "count": 1,
  "results": [
    {
      "brand_ko": "라운드랩",
      "brand_en": "ROUND LAB",
      "product_name_ko": "라운드랩 자작나무 수분 선크림",
      "price": 17800,
      "original_price": 25000,
      "sale_price": 17800,
      "discount_rate": 28,
      "currency": "KRW",
      "shade": null,
      "image_url": "https://...",
      "source_url": "https://www.oliveyoung.co.kr/...",
      "source": "oliveyoung",
      "source_label": "Olive Young",
      "source_priority": 10
    }
  ],
  "source_errors": []
}
```

## 환경 변수

Backend:

```bash
GLOWSEARCH_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
GLOWSEARCH_CACHE_TTL_SECONDS=180
GLOWSEARCH_MAX_RESULTS=480
GLOWSEARCH_SOURCE_TIME_BUDGET_SECONDS=2.5
GLOWSEARCH_MANAGED_SCRAPING_TIME_BUDGET_SECONDS=4.0
GLOWSEARCH_RESULT_SOURCE_PREFIXES=oliveyoung,official,musinsa,managed,barcode,discovery,external

GLOWSEARCH_OLIVEYOUNG_PUBLIC_API_ENABLED=true
GLOWSEARCH_OLIVEYOUNG_PUBLIC_API_BASE_URL=https://mcp.aka.page
GLOWSEARCH_OLIVEYOUNG_PUBLIC_API_TIMEOUT_SECONDS=6.0
GLOWSEARCH_OLIVEYOUNG_OFFICIAL_ORDER_ENABLED=true
GLOWSEARCH_OLIVEYOUNG_LIVE_SEARCH_REQUIRED=false

GLOWSEARCH_BROWSER_COLLECTOR_ENABLED=false
GLOWSEARCH_BROWSER_HEADLESS=true
GLOWSEARCH_BROWSER_TIMEOUT_SECONDS=25

# Optional managed Olive Young fallback
GLOWSEARCH_APIFY_TOKEN=
GLOWSEARCH_APIFY_ACTOR_ID=kitschy_marigold/oliveyoung-search-scraper

# Optional normalized JSON adapters.
# These should return real source-backed product JSON; GlowSearch does not fabricate fields.
GLOWSEARCH_MANAGED_SEARCH_API_ENABLED=false
GLOWSEARCH_MANAGED_SEARCH_API_BASE_URL=
GLOWSEARCH_MANAGED_SEARCH_API_SOURCE=managed:json-api
GLOWSEARCH_MANAGED_SEARCH_API_TIMEOUT_SECONDS=4.0
GLOWSEARCH_GLOBAL_DISCOVERY_API_ENABLED=false
GLOWSEARCH_GLOBAL_DISCOVERY_API_BASE_URL=
GLOWSEARCH_GLOBAL_DISCOVERY_API_SOURCE=discovery:json-api
GLOWSEARCH_GLOBAL_DISCOVERY_API_TIMEOUT_SECONDS=3.0
GLOWSEARCH_BARCODE_LOOKUP_API_ENABLED=false
GLOWSEARCH_BARCODE_LOOKUP_API_BASE_URL=
GLOWSEARCH_BARCODE_LOOKUP_API_SOURCE=barcode:lookup
GLOWSEARCH_BARCODE_LOOKUP_API_TIMEOUT_SECONDS=3.0

# Product index
GLOWSEARCH_PRODUCT_INDEX_ENABLED=true
GLOWSEARCH_PRODUCT_INDEX_PATH=backend/data/product_index.sqlite3
GLOWSEARCH_PRODUCT_INDEX_ADMIN_TOKEN=
GLOWSEARCH_PRODUCT_INDEX_MIN_RESULTS=1
GLOWSEARCH_PRODUCT_INDEX_BACKGROUND_REFRESH_ENABLED=true
GLOWSEARCH_PRODUCT_INDEX_WARMUP_ON_STARTUP=false
GLOWSEARCH_PRODUCT_INDEX_WARMUP_LIMIT=48
GLOWSEARCH_PRODUCT_INDEX_WARMUP_CONCURRENCY=2
GLOWSEARCH_PRODUCT_INDEX_MAX_SEED_QUERIES=180
GLOWSEARCH_PRODUCT_INDEX_BRAND_REGISTRY_WARMUP_ENABLED=true
GLOWSEARCH_PRODUCT_INDEX_BRAND_REGISTRY_WARMUP_LIMIT=80
GLOWSEARCH_PRODUCT_INDEX_DETAIL_ENRICHMENT_ENABLED=true
GLOWSEARCH_PRODUCT_INDEX_DETAIL_ENRICHMENT_MAX_RECORDS=12
GLOWSEARCH_PRODUCT_INDEX_SEED_QUERIES=선크림,틴트,쿠션,마스카라,토너패드,클렌징오일,젤,뮤드,메디힐,라운드랩
GLOWSEARCH_PRODUCT_INDEX_CATEGORY_QUERIES=선크림,톤업선크림,쿠션,파운데이션,컨실러,파우더,틴트,립밤,립스틱,아이섀도우,아이라이너,마스카라,클렌징오일,클렌징폼,클렌징젤,필링젤,젤,수딩젤,젤크림,젤네일,마사지젤,토너,세럼,크림,토너패드,히알루론산,시카,병풀,레티놀,비타민C,나이아신아마이드,세라마이드,판테놀,콜라겐,PDRN,어성초,티트리,알로에
GLOWSEARCH_PRODUCT_INDEX_BRAND_QUERIES=뮤드,메디힐,라운드랩,컬러그램,롬앤,클리오,페리페라,에뛰드,웨이크메이크,어뮤즈,토리든,아누아,정샘물,비긴스 바이 정샘물
```

Frontend:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## 데이터 원칙

- 상품 데이터는 원본 source가 제공한 값만 사용합니다. 현재 기본 source는 Olive Young HTML/public API, 검증 카탈로그, 선택형 Apify이고, 추가 source는 normalized JSON adapter 뒤에 둡니다.
- 상품명, 가격, 이미지, 링크는 원본에 없으면 임의로 채우지 않습니다.
- 영문 브랜드명이 없으면 `brand_registry.json`에 alias를 추가해 보강합니다.
- SQLite 제품 인덱스는 검색 속도와 커버리지를 위한 저장소입니다. 가격/할인 정보는 live refresh 결과로 계속 갱신합니다.
- 시작 시 warmup은 기본 비활성화합니다. 운영에서는 `/index/warm`을 Render Cron 또는 수동 admin job으로 호출해 live 검색과 경쟁하지 않게 합니다.
- 인덱스 저장 전 `OliveYoungDetailEnrichmentAgent`가 상품 상세 페이지를 가져와 브랜드명, 상품명, 가격, 이미지 정보를 보강합니다.
- `GLOWSEARCH_OLIVEYOUNG_OFFICIAL_ORDER_ENABLED=true`이면 live 결과와 쿼리별 인덱스 결과가 Olive Young 공식 검색 순서를 보존합니다.
- `GLOWSEARCH_OLIVEYOUNG_LIVE_SEARCH_REQUIRED=true`이면 속도보다 공식 live 일치를 우선해 캐시/인덱스 즉시 반환을 건너뜁니다. 기본값은 `false`입니다.
- 쿼리별 인덱스 순서는 Olive Young 공식 검색 수집 순서를 보존합니다. 공식 검색이 실패하거나 결과가 부족하면 인덱스와 보조 소스로 보강합니다.
- 운영에서 인덱스를 오래 유지하려면 Render persistent disk를 `GLOWSEARCH_PRODUCT_INDEX_PATH`에 연결하거나, 다음 단계에서 Postgres + full-text search로 이전합니다.

## 인덱스 운영

상태 확인:

```bash
curl https://glowsearch-backend.onrender.com/index/status
curl https://glowsearch-backend.onrender.com/diagnostics
```

간단한 검색 지연 벤치마크는 다음처럼 실행합니다.

```bash
cd backend
.venv/bin/python scripts/benchmark_search.py --base-url http://localhost:8000 --repeat 3
.venv/bin/python scripts/benchmark_search.py --base-url https://glowsearch-backend.onrender.com --repeat 3
```

Render에서 `GLOWSEARCH_PRODUCT_INDEX_ADMIN_TOKEN`을 설정하면 워밍업을 수동 또는 Cron으로 트리거할 수 있습니다.

```bash
curl -X POST "https://glowsearch-backend.onrender.com/index/warm?token=$GLOWSEARCH_PRODUCT_INDEX_ADMIN_TOKEN&limit=48"
curl -X POST "https://glowsearch-backend.onrender.com/index/warm?token=$GLOWSEARCH_PRODUCT_INDEX_ADMIN_TOKEN&q=뮤드&q=롬앤&limit=48&wait=true"
```

목표는 “검색 요청에서 모든 상품을 실시간으로 긁기”가 아니라, 카테고리/브랜드/상품 검색어를 백그라운드로 계속 수집해 DB에 쌓고 검색은 DB에서 즉시 반환하는 구조입니다. 전체 커버리지를 안정적으로 올리려면 SQLite에 Render persistent disk를 붙이거나 Postgres로 이전해야 합니다.

## 아키텍처 노트와 롤아웃

1. 현재 단계: SQLite index + TTL cache + SourcePolicy
   - `/search` API는 그대로 유지합니다.
   - 캐시 hit와 index hit는 즉시 반환하고 background refresh를 예약합니다.
   - live source 실패는 사용자에게 과하게 노출하지 않고 `/diagnostics`에 source별 failure/timeout으로 남깁니다.

2. 운영 저장소 1차 권장안: Render persistent disk
   - 현재 SQLite를 유지하면서 `GLOWSEARCH_PRODUCT_INDEX_PATH`를 persistent disk 경로로 옮기면 재배포/재시작 후에도 warm index를 유지할 수 있습니다.
   - 무료/소규모 운영에서는 가장 단순하고 안정적입니다.

3. 운영 저장소 2차 권장안: Postgres full-text search
   - 상품 수와 source가 늘면 Postgres로 `products`, `product_sources`, `query_products`, `brand_aliases`를 분리합니다.
   - `tsvector` + trigram index로 한글/영문 alias, 오타, 상품명 variation을 검색합니다.

4. 검색 전문 엔진 후보
   - Meilisearch/Typesense: 빠른 prefix/typo search와 운영 단순성이 필요할 때.
   - OpenSearch: 대규모 로그/검색 분석과 복잡한 ranking이 필요할 때.

5. 추가 source rollout
   - Musinsa/공식몰/managed scraping/barcode/global discovery는 먼저 normalized JSON adapter 뒤에 붙입니다.
   - source prefix는 `musinsa`, `official`, `managed`, `barcode`, `discovery` 중 하나로 시작하게 둡니다.
   - `GLOWSEARCH_RESULT_SOURCE_PREFIXES`와 `SourcePolicy` priority로 노출 여부와 표시 label을 통제합니다.

## 배포

- Frontend: Vercel
- Backend: Render Docker web service

프론트 배포 환경에는 다음 값을 둡니다.

```bash
NEXT_PUBLIC_API_BASE_URL=https://glowsearch-backend.onrender.com
```

Render backend에는 Backend 환경 변수를 등록합니다. `render.yaml`은 현재 Olive Young 전용 파이프라인 기준입니다.

### Render 자동 배포 보강

Render 서비스가 GitHub push를 바로 반영하지 않으면 deploy hook으로 강제 트리거합니다.

1. Render Dashboard에서 backend service를 엽니다.
2. Settings의 Deploy Hook URL을 복사합니다.
3. GitHub repository Settings > Secrets and variables > Actions에 `RENDER_DEPLOY_HOOK_URL` secret을 추가합니다.
4. 이후 `main`에 backend 변경이 push되면 `.github/workflows/deploy-render-backend.yml`이 해당 커밋 SHA로 Render deploy hook을 호출합니다.

배포된 백엔드 커밋은 health 응답에서 확인합니다.

```bash
curl https://glowsearch-backend.onrender.com/health
```

## 검증

```bash
cd backend
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .

cd ../frontend
npm run typecheck
npm run build
```
