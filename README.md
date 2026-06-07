# GlowSearch

Olive Young 상품을 빠르게 검색하고 브랜드명, 영문명, 원가, 할인가, 할인율, 이미지, 원본 링크를 확인하는 검색 앱입니다.

서비스 주소: [https://glow-search.vercel.app/](https://glow-search.vercel.app/)

## 현재 방향

- 검색 결과는 Olive Young 상품만 반환합니다.
- 원본에서 확인하지 못한 값은 만들지 않고 `null`로 둡니다.
- 빠른 소스는 병렬로 실행하고, 브라우저 수집은 모든 빠른 소스가 실패하거나 비었을 때만 사용합니다.
- 같은 Olive Young `goodsNo`는 하나의 상품으로 합칩니다.
- 브랜드 영문명은 `backend/data/brand_registry.json`의 공식 alias를 기준으로 정규화합니다.

## 검색 파이프라인

```text
Next.js 검색 화면
  -> FastAPI /search
  -> SearchService
  -> 빠른 수집기 병렬 실행
       - OliveYoungCollector: 올리브영 HTML 검색
       - OliveYoungPublicApiCollector: public API 가격/이미지
       - LocalVerifiedCatalogCollector: 검증된 로컬 보조 데이터
       - ApifyOliveYoungCollector: APIFY_TOKEN이 있을 때만 사용
  -> 결과가 없으면 BrowserOliveYoungCollector fallback
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
      models/           API 응답/수집 스키마
      normalizer/       브랜드/상품 정규화
      parser/           HTML 파서
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
      "source": "oliveyoung"
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
GLOWSEARCH_MAX_RESULTS=24
GLOWSEARCH_SOURCE_TIME_BUDGET_SECONDS=2.5
GLOWSEARCH_MANAGED_SCRAPING_TIME_BUDGET_SECONDS=4.0

GLOWSEARCH_OLIVEYOUNG_PUBLIC_API_ENABLED=true
GLOWSEARCH_OLIVEYOUNG_PUBLIC_API_BASE_URL=https://mcp.aka.page
GLOWSEARCH_OLIVEYOUNG_PUBLIC_API_TIMEOUT_SECONDS=4.0

GLOWSEARCH_BROWSER_COLLECTOR_ENABLED=true
GLOWSEARCH_BROWSER_HEADLESS=true
GLOWSEARCH_BROWSER_TIMEOUT_SECONDS=25

# Optional managed Olive Young fallback
GLOWSEARCH_APIFY_TOKEN=
GLOWSEARCH_APIFY_ACTOR_ID=kitschy_marigold/oliveyoung-search-scraper
```

Frontend:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## 데이터 원칙

- 상품 데이터는 Olive Young HTML, Olive Young public API, 검증 카탈로그, 선택형 Apify 결과에서만 가져옵니다.
- 상품명, 가격, 이미지, 링크는 원본에 없으면 임의로 채우지 않습니다.
- 영문 브랜드명이 없으면 `brand_registry.json`에 alias를 추가해 보강합니다.
- 실시간 가격을 우선하므로 영구 제품 인덱스는 현재 검색 경로에 두지 않습니다.

## 배포

- Frontend: Vercel
- Backend: Render Docker web service

프론트 배포 환경에는 다음 값을 둡니다.

```bash
NEXT_PUBLIC_API_BASE_URL=https://glowsearch-backend.onrender.com
```

Render backend에는 Backend 환경 변수를 등록합니다. `render.yaml`은 현재 Olive Young 전용 파이프라인 기준입니다.

## 검증

```bash
cd backend
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .

cd ../frontend
npm run typecheck
npm run build
```
