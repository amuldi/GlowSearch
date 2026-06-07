# GlowSearch

화장품 상품 정보를 빠르게 검색하고, 브랜드명·상품명·가격·이미지·원본 링크를 한 화면에서 확인하는 검색 서비스입니다.

**서비스 주소:** [https://glow-search.vercel.app/](https://glow-search.vercel.app/)

## 프로젝트 소개

GlowSearch는 화장품 정보를 찾을 때 여러 쇼핑몰과 브랜드 페이지를 오가며 확인해야 하는 과정을 줄이기 위해 만든 프로젝트입니다.

사용자는 검색어만 입력하면 상품 카드 형태로 결과를 확인할 수 있고, 백엔드는 Olive Young, Musinsa, 검증된 로컬 캐시를 조합해 원본에서 확인 가능한 데이터만 반환합니다. 확인되지 않은 값은 추측하지 않고 비워 두는 것을 기본 원칙으로 삼았습니다.

## 핵심 기능

- **검색 중심 UI**: 필터 입력을 제거하고 검색어 입력, 결과 목록, 상품 정보 복사에 집중했습니다.

- **빠른 첫 응답**: 첫 검색은 24개 결과부터 가져오고, 더 필요한 경우 `더 보기`로 24개씩 추가 조회합니다.

- **인덱스 우선 검색**: 검증 카탈로그와 런타임 수집 결과를 로컬 제품 인덱스에서 먼저 찾고, 있으면 외부 요청을 기다리지 않고 바로 반환합니다.

- **원본 기반 상품 정보**: 브랜드명, 상품명, 가격, 이미지, 원본 링크는 라이브 소스나 검증된 데이터에서만 가져옵니다.

- **브랜드명 정규화**: 한국어 브랜드명을 공식 영문 표기로 맞추기 위해 로컬 브랜드 레지스트리와 Musinsa 브랜드 조회를 함께 사용합니다.

- **수집 실패 대응**: Olive Young 직접 요청이 막히거나 결과가 부족할 수 있어 Musinsa, 공식 브랜드 사이트, 브라우저 수집, 검증 캐시를 보조 경로로 둡니다.

- **확장 가능한 소스 어댑터**: SerpAPI, Bright Data, Bing Web Search, Google Programmable Search, Open Beauty Facts, Barcode Lookup, UPCitemDB를 env flag 뒤에 둔 선택형 어댑터로 연결할 수 있습니다.

## 기술 스택

| 영역 | 기술 |
| --- | --- |
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| Backend | FastAPI, Pydantic, httpx |
| Parsing | BeautifulSoup 기반 HTML 파서 |
| Browser Fallback | Playwright Chromium |
| Index | 로컬 JSON 인덱스, Postgres full-text search 권장 |
| Test | pytest, pytest-asyncio, TypeScript typecheck |
| Deploy | Vercel frontend, Render backend |

## 만든 과정

### 1. 검색 경험부터 단순하게 잡기

처음 목표는 “화장품 상품 정보를 검색창 하나로 빠르게 확인하자”였습니다.

그래서 첫 화면은 별도의 랜딩 페이지가 아니라 바로 검색할 수 있는 화면으로 만들었습니다. 상품 카드는 반복적으로 비교하기 좋은 정보만 남겼습니다.

- 브랜드명
- 상품명
- 가격
- 색상/호수 정보
- 상품 이미지
- 원본 링크
- 복사용 상품 정보

### 2. 원본에서 확인된 값만 보여주기

검색 서비스는 빠른 것도 중요하지만, 상품 정보가 틀리면 의미가 없습니다.

그래서 백엔드에는 다음 원칙을 적용했습니다.

- 모르는 값을 임의로 만들지 않습니다.
- 브랜드명과 상품명은 원본 응답이나 검증 데이터로만 확정합니다.
- 가격이 없으면 `null`로 둡니다.
- 같은 상품은 중복 제거합니다.
- 수집 실패는 `source_errors`로 남깁니다.

### 3. 수집 소스 확장하기

처음에는 Olive Young 검색 페이지를 중심으로 수집했습니다. 하지만 실제 운영 환경에서는 요청 차단, HTML 구조 변경, 빈 결과 같은 문제가 생길 수 있습니다.

그래서 수집 경로를 단계적으로 늘렸습니다.

| 수집 경로 | 역할 |
| --- | --- |
| Olive Young direct collector | 기본 상품 검색 |
| Local verified catalog | 검증된 상품의 빠른 fallback |
| Musinsa product collector | Olive Young 결과가 부족할 때 보조 검색 |
| Official brand site collector | 브랜드 공식 사이트 보조 확인 |
| Browser collector | 직접 요청이 막힐 때 Playwright로 브라우저 수집 |

### 4. 브랜드 정규화하기

화장품 검색 결과에는 `롬앤`, `메디힐`, `더샘`처럼 한국어 브랜드명이 자주 나옵니다.

결과를 일관되게 보여주기 위해 `backend/data/brand_registry.json`에 공식 영문명과 alias를 관리했습니다.

흐름은 단순합니다.

1. 로컬 브랜드 레지스트리에서 먼저 찾습니다.
2. 없으면 Musinsa 브랜드 API에서 정확 일치만 사용합니다.
3. 애매한 값은 영문명으로 확정하지 않습니다.

### 5. 검색 속도 다시 줄이기

초기에는 결과를 최대한 많이 채우는 방향이었지만, 사용자가 느끼는 속도는 느려졌습니다.

그래서 최근에는 “일단 빠르게 보여주고, 필요하면 더 가져오기”로 바꿨습니다.

- 기본 검색 결과 수를 48개에서 24개로 줄였습니다.
- 빠른 수집기에서 결과가 있으면 브라우저 보강 수집을 기다리지 않습니다.
- 상세 페이지 enrichment는 기본 비활성화했습니다.
- 프론트 필터 UI를 제거해 검색 흐름을 단순화했습니다.

## 동작 구조

```text
사용자 검색어
  -> Next.js frontend
  -> FastAPI /search
  -> 제품 인덱스/검증 캐시 확인
  -> 여러 수집기 실행
  -> HTML/API 응답 파싱
  -> 브랜드명 정규화
  -> 중복 제거 및 랭킹
  -> 상품 카드 렌더링
```

요청 시점에는 인덱스에 있는 결과를 먼저 반환합니다. 인덱스 결과가 오래됐으면 stale 값을 즉시 반환한 뒤 백그라운드에서 재수집합니다. 인덱스가 비어 있을 때만 빠른 외부 수집기를 병렬로 호출하고, Playwright 브라우저 수집은 빠른 소스가 모두 실패하거나 결과가 없을 때만 사용합니다.

자세한 확장 구조는 [검색 아키텍처 노트](docs/search-architecture.md)를 참고합니다.

## 폴더 구조

```text
GlowSearch/
  backend/
    app/
      api/              FastAPI 라우트
      agents/           발견, 수집, 정규화, 검색, 평가 모듈
      cache/            TTL 캐시
      core/             설정
      data_collector/   Olive Young, Musinsa, 브라우저 수집기
      index/            로컬 제품 인덱스 저장소
      models/           응답/소스 스키마
      normalizer/       브랜드/상품 정규화
      parser/           HTML 파서
      service/          검색 오케스트레이션
      source_adapters/  선택형 외부 API 어댑터
    scripts/
      benchmark_search.py
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

### Backend

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

상태 확인:

```bash
curl http://localhost:8000/health
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 엽니다.

```text
http://localhost:3000
```

백엔드 주소가 다르면 `frontend/.env.local`에 설정합니다.

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## API

### Search

```bash
curl 'http://localhost:8000/search?q=틴트&limit=24'
```

지원 파라미터:

| 파라미터 | 설명 |
| --- | --- |
| `q` | 검색어 |
| `keyword` | `q`와 같은 역할의 alias |
| `brand` | 브랜드 필터 |
| `min_price` | 최소 가격 |
| `max_price` | 최대 가격 |
| `has_shade` | 색상/호수 존재 여부 |
| `limit` | 반환 개수, 1~480 |

응답 예시:

```json
{
  "query": "틴트",
  "count": 1,
  "results": [
    {
      "brand_en": "rom&nd",
      "product_name_ko": "롬앤 글래스팅 컬러 글로스",
      "price": 13000,
      "currency": "KRW",
      "shade": null,
      "image_url": "https://example.com/item.jpg",
      "source_url": "https://example.com/product",
      "source": "oliveyoung"
    }
  ],
  "source_errors": []
}
```

## 데이터 원칙

- 원본에서 확인하지 못한 값은 `null`로 둡니다.
- 브랜드 영문명은 로컬 레지스트리나 정확한 외부 조회로만 확정합니다.
- 가격이 없는 상품도 브랜드명과 상품명이 확인되면 결과로 유지할 수 있습니다.
- 소스가 막히면 빈 결과나 `source_errors`를 반환합니다.
- 같은 상품은 브랜드명과 상품명을 기준으로 중복 제거합니다.

## 배포

현재 서비스 주소:

```text
https://glow-search.vercel.app/
```

권장 배포 구조:

- **Frontend:** Vercel
- **Backend:** Render Docker web service

프론트 환경 변수:

```bash
NEXT_PUBLIC_API_BASE_URL=https://your-backend-domain.onrender.com
```

백엔드 권장 환경 변수:

```bash
GLOWSEARCH_BROWSER_COLLECTOR_ENABLED=true
GLOWSEARCH_BROWSER_HEADLESS=true
GLOWSEARCH_BROWSER_TIMEOUT_SECONDS=25
GLOWSEARCH_SOURCE_TIME_BUDGET_SECONDS=2.5
GLOWSEARCH_MANAGED_SCRAPING_TIME_BUDGET_SECONDS=4.0
GLOWSEARCH_PRODUCT_INDEX_ENABLED=true
GLOWSEARCH_PRODUCT_INDEX_PATH=data/product_index.json
GLOWSEARCH_PRODUCT_INDEX_SEED_VERIFIED_CATALOG=true
GLOWSEARCH_PRODUCT_INDEX_FRESH_TTL_SECONDS=3600
GLOWSEARCH_PRODUCT_INDEX_STALE_TTL_SECONDS=604800
GLOWSEARCH_STALE_REVALIDATE_ENABLED=true
GLOWSEARCH_MUSINSA_BRAND_LOOKUP_ENABLED=true
GLOWSEARCH_MUSINSA_PRODUCT_COLLECTOR_ENABLED=true
GLOWSEARCH_MUSINSA_BEAUTY_CATEGORY_CODE=104
GLOWSEARCH_CORS_ORIGINS=https://glow-search.vercel.app
```

선택형 전역 커버리지 어댑터:

```bash
# Managed scraping / discovery
GLOWSEARCH_APIFY_TOKEN=
GLOWSEARCH_APIFY_ACTOR_ID=kitschy_marigold/oliveyoung-search-scraper
GLOWSEARCH_BRIGHTDATA_SERP_ENABLED=false
GLOWSEARCH_BRIGHTDATA_API_KEY=
GLOWSEARCH_BRIGHTDATA_SERP_ZONE=serp_api1
GLOWSEARCH_BRIGHTDATA_COUNTRY=us

# Product/source discovery
GLOWSEARCH_SERPAPI_ENABLED=false
GLOWSEARCH_SERPAPI_API_KEY=
GLOWSEARCH_SERPAPI_GL=us
GLOWSEARCH_SERPAPI_HL=en
GLOWSEARCH_BING_WEB_SEARCH_ENABLED=false
GLOWSEARCH_BING_WEB_SEARCH_API_KEY=
GLOWSEARCH_BING_WEB_SEARCH_MARKET=en-US
GLOWSEARCH_GOOGLE_PROGRAMMABLE_SEARCH_ENABLED=false
GLOWSEARCH_GOOGLE_PROGRAMMABLE_SEARCH_API_KEY=
GLOWSEARCH_GOOGLE_PROGRAMMABLE_SEARCH_ENGINE_ID=

# Barcode / GTIN lookup
GLOWSEARCH_OPEN_BEAUTY_FACTS_ENABLED=true
GLOWSEARCH_BARCODE_LOOKUP_ENABLED=false
GLOWSEARCH_BARCODE_LOOKUP_API_KEY=
GLOWSEARCH_UPCITEMDB_ENABLED=false
GLOWSEARCH_UPCITEMDB_API_KEY=
```

운영 인덱스는 Postgres + full-text search를 먼저 권장합니다. 트래픽이나 랭킹 요구가 커지면 같은 `ProductIndexStore` 계약 뒤에 Meilisearch, Typesense, OpenSearch를 붙이는 방식이 안전합니다.

## 검증

```bash
cd backend
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python scripts/benchmark_search.py --query 믹순 --iterations 1 --limit 5

cd ../frontend
npm run typecheck
npm run build
```

최근 확인한 검증:

- Backend: `49 passed`
- Backend: Ruff 통과
- Benchmark smoke: p50/p95 약 1.5ms, source failure rate 0.0
- Frontend: TypeScript typecheck 통과
- Frontend: production build 통과

## 개선할 점

- 검증 상품 캐시 확장
- 브랜드 레지스트리 자동 보강 도구 추가
- 수집 소스별 응답 시간 로깅
- Postgres full-text search 기반 영구 제품 인덱스 전환
- 배포 환경에서 수집 실패 원인을 확인하는 상태 화면
- API 필터를 고급 검색 화면으로 분리
