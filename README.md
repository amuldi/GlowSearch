# GlowSearch

화장품 상품 정보를 빠르게 검색하고, 브랜드명/상품명/가격/이미지/원본 링크를 한 화면에서 확인하기 위한 검색 서비스입니다.  
프론트엔드는 검색어 입력과 결과 확인에 집중하고, 백엔드는 Olive Young, Musinsa, 검증된 로컬 캐시를 조합해 원본에서 확인 가능한 데이터만 반환합니다.

## 한눈에 보기

- **검색 중심 UI**: 필터 입력을 제거하고 검색어 입력, 결과 목록, 복사 기능에 집중했습니다.
- **빠른 첫 응답**: 첫 검색은 24개 결과부터 가져오고, 더 필요한 경우 `더 보기`로 추가 조회합니다.
- **원본 기반 데이터**: 상품 정보는 라이브 소스나 검증된 로컬 데이터에서만 가져오며, 값이 없으면 추측하지 않습니다.
- **브랜드 정규화**: 한국어 브랜드명을 영문 공식 표기로 정규화하기 위해 로컬 브랜드 레지스트리와 Musinsa 브랜드 조회를 함께 사용합니다.
- **차단 대응**: Olive Young 직접 요청이 막힐 수 있어 브라우저 수집, Musinsa fallback, 검증 캐시를 단계적으로 둡니다.

## 기술 스택

| 영역 | 기술 |
| --- | --- |
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| Backend | FastAPI, Pydantic, httpx |
| Browser fallback | Playwright Chromium |
| Data parsing | BeautifulSoup 기반 HTML 파서 |
| Test | pytest, pytest-asyncio, TypeScript typecheck |
| Deploy | Render backend, Vercel frontend |

## 프로젝트를 만든 여정

### 1. 시작점: 흩어진 화장품 정보를 한 번에 보고 싶었다

처음 목표는 단순했습니다. 화장품을 찾을 때 브랜드명, 한국어 상품명, 가격, 이미지, 원본 링크를 매번 여러 사이트에서 직접 확인해야 했고, 이 과정을 검색창 하나로 줄이고 싶었습니다.

그래서 GlowSearch는 처음부터 “검색어를 넣으면 바로 비교 가능한 상품 카드가 나온다”는 방향으로 설계했습니다. 화면은 검색창과 결과 카드 중심으로 두고, 상품 카드는 실무적으로 필요한 항목만 보여주도록 만들었습니다.

### 2. 첫 번째 문제: 검색 결과는 빨라야 하지만 정확해야 했다

단순히 검색 결과를 많이 가져오는 것보다 중요한 것은 **원본에서 확인된 값만 보여주는 것**이었습니다. 그래서 백엔드는 다음 원칙을 갖게 됐습니다.

- 브랜드명과 상품명은 원본 응답이나 검증된 레지스트리에서 확인합니다.
- 가격, 이미지, 원본 링크는 소스가 제공하지 않으면 비워 둡니다.
- 모르는 값을 그럴듯하게 만들지 않습니다.
- 같은 상품이 여러 소스에서 나오면 중복을 제거합니다.

이 원칙 때문에 코드가 조금 더 복잡해졌지만, 결과를 신뢰할 수 있게 만드는 쪽을 선택했습니다.

### 3. Olive Young 수집기부터 시작했다

가장 먼저 붙인 데이터 소스는 Olive Young 검색 페이지입니다.  
`backend/app/data_collector/oliveyoung.py`에서 검색 페이지를 요청하고, `backend/app/parser/oliveyoung_html.py`에서 다양한 HTML 구조를 파싱합니다.

Olive Young 페이지는 기존 마크업, 현대적인 카드형 마크업, 스크립트 안에 들어 있는 상품 데이터 등 여러 형태로 응답할 수 있습니다. 그래서 파서는 하나의 선택자에만 의존하지 않고 여러 패턴을 순서대로 시도하도록 만들었습니다.

### 4. 브랜드명 정규화가 필요해졌다

검색 결과에는 한국어 브랜드명과 영문 브랜드명이 섞여 나옵니다. GitHub에 올릴 수 있는 완성도 있는 검색 결과를 만들려면 `롬앤`, `메디힐`, `더샘` 같은 표기를 공식 영문명으로 정리해야 했습니다.

이를 위해 `backend/data/brand_registry.json`을 만들고, 다음 흐름을 추가했습니다.

- 로컬 브랜드 레지스트리에서 먼저 공식 영문명을 찾습니다.
- 레지스트리에 없고 한국어 브랜드명만 있을 때는 Musinsa 브랜드 API를 정확 일치 기준으로 조회합니다.
- 애매한 값은 영문명으로 확정하지 않습니다.

이 과정을 통해 결과 카드의 브랜드 표기가 더 일관되게 정리되었습니다.

### 5. 실제 서비스 환경에서는 차단과 빈 결과가 생겼다

라이브 소스 수집은 항상 성공하지 않습니다. Olive Young이 직접 HTTP 요청을 차단하거나, HTML 구조가 바뀌거나, 특정 검색어에 결과가 적게 나올 수 있습니다.

그래서 수집 전략을 단계적으로 확장했습니다.

- **Olive Young direct collector**: 가장 먼저 시도하는 기본 수집기
- **Local verified catalog**: 이미 검증한 상품을 빠르게 찾는 로컬 캐시
- **Musinsa product collector**: Olive Young이 막힐 때 보조로 쓰는 상품 검색
- **Official brand site collector**: 브랜드 공식 사이트에서 보조 확인
- **Browser collector**: 정말 필요할 때 Playwright로 브라우저를 열어 수집

초기에는 결과를 최대한 채우기 위해 브라우저 보강을 자주 실행했지만, 체감 속도가 느려지는 문제가 있었습니다.

### 6. UX를 단순화했다

처음 화면에는 브랜드, 최소가, 최대가, 색상 여부 필터가 있었습니다. 기능은 있었지만 검색을 빠르게 해보려는 흐름에는 오히려 방해가 됐습니다.

그래서 현재 프론트엔드는 필터 UI를 제거하고 검색어 중심으로 바꿨습니다.

- 검색창
- 검색 버튼
- 결과 상태 문구
- 상품 카드
- 상품 정보 복사 버튼
- 더 보기 버튼

사용자는 검색어만 넣고 바로 결과를 볼 수 있습니다. API에는 필터 파라미터가 남아 있어 나중에 관리자용 화면이나 고급 검색을 다시 만들 수도 있습니다.

### 7. 검색 속도를 다시 조정했다

검색이 느리게 느껴지는 원인은 두 가지였습니다.

- 첫 요청에서 너무 많은 결과를 가져옴
- 빠른 수집 결과가 있어도 브라우저 보강 수집을 기다림

그래서 최근 구조는 다음처럼 바꿨습니다.

- 첫 검색 결과 수를 48개에서 24개로 줄였습니다.
- 추가 결과는 `더 보기`로 24개씩 가져옵니다.
- 빠른 수집기에서 결과가 있으면 브라우저 보강을 기다리지 않습니다.
- 상세 페이지 enrichment는 기본 비활성화해 첫 응답을 가볍게 했습니다.

이 변경으로 사용자는 “일단 결과가 뜨는 속도”를 더 빠르게 느낄 수 있습니다.

## 폴더 구조

```text
GlowSearch/
  backend/
    app/
      api/              FastAPI 라우트
      cache/            TTL 캐시
      core/             설정
      data_collector/   Olive Young, Musinsa, 브라우저 수집기
      models/           응답/소스 스키마
      normalizer/       브랜드/상품 정규화
      parser/           HTML 파서
      service/          검색 오케스트레이션
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

정상 실행 확인:

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

GlowSearch는 검색 결과를 보기 좋게 만드는 것보다, 확인되지 않은 값을 만들지 않는 것을 우선합니다.

- 원본에서 찾지 못한 값은 `null`로 둡니다.
- 브랜드 영문명은 로컬 레지스트리나 정확한 외부 조회로만 확정합니다.
- 가격이 없는 품절/공식 상품도 브랜드명과 상품명이 확인되면 결과로 유지할 수 있습니다.
- 소스가 막히면 빈 결과나 `source_errors`를 반환합니다.
- 같은 상품은 브랜드명과 상품명을 기준으로 중복 제거합니다.

## 배포

권장 배포 구조:

- Backend: Render Docker web service
- Frontend: Vercel Next.js app

포함된 배포 파일:

- `backend/Dockerfile`
- `render.yaml`
- `frontend/.env.example`

### Render backend

Render에서 Blueprint를 사용하거나 Docker web service를 직접 생성합니다.

주요 설정:

```text
Root Directory: backend
Environment: Docker
Health Check Path: /health
```

권장 환경 변수:

```bash
GLOWSEARCH_BROWSER_COLLECTOR_ENABLED=true
GLOWSEARCH_BROWSER_HEADLESS=true
GLOWSEARCH_BROWSER_TIMEOUT_SECONDS=25
GLOWSEARCH_MUSINSA_BRAND_LOOKUP_ENABLED=true
GLOWSEARCH_MUSINSA_PRODUCT_COLLECTOR_ENABLED=true
GLOWSEARCH_MUSINSA_BEAUTY_CATEGORY_CODE=104
GLOWSEARCH_CORS_ORIGINS=https://your-frontend-domain.vercel.app
```

### Vercel frontend

Vercel에서 같은 GitHub 저장소를 import합니다.

```text
Root Directory: frontend
Framework Preset: Next.js
Build Command: npm run build
```

프론트 환경 변수:

```bash
NEXT_PUBLIC_API_BASE_URL=https://your-backend-domain.onrender.com
```

## 검증 명령어

```bash
cd backend
pytest

cd ../frontend
npm run typecheck
npm run build
```

현재 확인한 검증:

- Backend: `39 passed`
- Frontend: TypeScript typecheck 통과
- Frontend: production build 통과

## 앞으로 개선할 점

- 검색 결과 품질을 위한 검증 상품 캐시 확장
- 브랜드 레지스트리 자동 보강 도구 추가
- API 필터를 별도 고급 검색 화면으로 분리
- 수집 소스별 응답 시간 측정 및 로깅
- 배포 환경에서 차단/빈 결과 원인을 더 쉽게 확인하는 관리자용 상태 화면
