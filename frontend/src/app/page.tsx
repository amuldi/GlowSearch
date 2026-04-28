"use client";

import { Check, Copy, Search, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { searchProducts } from "@/lib/api";
import type { Product, SearchResponse } from "@/types/product";

const currencyFormatter = new Intl.NumberFormat("ko-KR", {
  style: "currency",
  currency: "KRW",
  maximumFractionDigits: 0,
});

const usdFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

const jpyFormatter = new Intl.NumberFormat("ja-JP", {
  style: "currency",
  currency: "JPY",
  maximumFractionDigits: 0,
});

const DEFAULT_RESULT_LIMIT = 48;
const MAX_RESULT_LIMIT = 480;

export default function Home() {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [searchRun, setSearchRun] = useState(0);
  const [brand, setBrand] = useState("");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [hasShade, setHasShade] = useState(false);
  const [resultLimit, setResultLimit] = useState(DEFAULT_RESULT_LIMIT);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const trimmedQuery = query.trim();
  const trimmedSubmittedQuery = submittedQuery.trim();
  const queryTerms = useMemo(
    () => query.split(/\r?\n/).map((line) => line.trim()).filter(Boolean),
    [query],
  );
  const submittedQueryTerms = useMemo(
    () => submittedQuery.split(/\r?\n/).map((line) => line.trim()).filter(Boolean),
    [submittedQuery],
  );
  const queryCount = queryTerms.length;
  const submittedQueryCount = submittedQueryTerms.length;
  const isInputBatchQuery = queryCount > 1;
  const isSubmittedBatchQuery = submittedQueryCount > 1;
  const hasActiveFilters = Boolean(brand || minPrice || maxPrice || hasShade);
  const canLoadMore = Boolean(
    response && !isSubmittedBatchQuery && response.count >= resultLimit && resultLimit < MAX_RESULT_LIMIT,
  );

  useEffect(() => {
    setResultLimit(DEFAULT_RESULT_LIMIT);
  }, [brand, hasShade, maxPrice, minPrice, trimmedSubmittedQuery]);

  useEffect(() => {
    if (!trimmedSubmittedQuery || trimmedQuery !== trimmedSubmittedQuery) {
      setResponse(null);
      setIsLoading(false);
      setErrorMessage(null);
      return;
    }

    const controller = new AbortController();
    const runSearch = async () => {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const data = await searchProducts(
          {
            query: trimmedSubmittedQuery,
            brand: brand.trim() || undefined,
            minPrice: minPrice || undefined,
            maxPrice: maxPrice || undefined,
            hasShade: hasShade ? true : undefined,
            limit: isSubmittedBatchQuery ? Math.min(submittedQueryCount, MAX_RESULT_LIMIT) : resultLimit,
          },
          controller.signal,
        );
        setResponse(data);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setErrorMessage("검색 중 문제가 발생했습니다.");
        setResponse(null);
      } finally {
        setIsLoading(false);
      }
    };
    void runSearch();

    return () => {
      controller.abort();
    };
  }, [
    brand,
    hasShade,
    isSubmittedBatchQuery,
    maxPrice,
    minPrice,
    resultLimit,
    searchRun,
    submittedQueryCount,
    trimmedQuery,
    trimmedSubmittedQuery,
  ]);

  const statusText = useMemo(() => {
    if (!trimmedSubmittedQuery || trimmedQuery !== trimmedSubmittedQuery) return "";
    if (isLoading) return "검색 중입니다.";
    if (errorMessage) return errorMessage;
    if (response && response.count === 0) return "검색 결과가 없습니다.";
    if (response && isSubmittedBatchQuery) {
      return `${submittedQueryCount.toLocaleString("ko-KR")}개 검색어 중 ${response.count.toLocaleString("ko-KR")}개 결과`;
    }
    if (response && !isSubmittedBatchQuery && response.count >= resultLimit) {
      return `${response.count.toLocaleString("ko-KR")}개 결과 표시 중`;
    }
    if (response) return `${response.count.toLocaleString("ko-KR")}개 결과`;
    return "";
  }, [
    errorMessage,
    isLoading,
    isSubmittedBatchQuery,
    response,
    resultLimit,
    submittedQueryCount,
    trimmedQuery,
    trimmedSubmittedQuery,
  ]);

  const clearFilters = () => {
    setBrand("");
    setMinPrice("");
    setMaxPrice("");
    setHasShade(false);
  };

  const clearSearch = () => {
    setQuery("");
    setSubmittedQuery("");
    setResponse(null);
    setErrorMessage(null);
    setIsLoading(false);
    setResultLimit(DEFAULT_RESULT_LIMIT);
  };

  const submitSearch = () => {
    if (!trimmedQuery) {
      clearSearch();
      return;
    }
    setSubmittedQuery(trimmedQuery);
    setResultLimit(DEFAULT_RESULT_LIMIT);
    setSearchRun((current) => current + 1);
  };

  return (
    <main className="min-h-screen bg-[#fafafa] px-4 py-8 text-ink sm:px-6 lg:px-8">
      <section className="mx-auto flex w-full max-w-3xl flex-col items-center gap-5 pt-6 sm:pt-10">
        <div className="flex w-full items-start gap-2 rounded-lg border border-line bg-white px-4 py-3 shadow-soft">
          <Search className="mt-2.5 h-5 w-5 shrink-0 text-mint" aria-hidden="true" />
          <textarea
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            rows={isInputBatchQuery ? Math.min(queryCount, 6) : 1}
            placeholder="관련 검색어"
            className="min-h-10 min-w-0 flex-1 resize-y border-0 bg-transparent py-2 text-base leading-6 outline-none placeholder:text-neutral-400"
            aria-label="관련 검색어"
          />
          {query ? (
            <button
              type="button"
              onClick={clearSearch}
              className="grid h-9 w-9 place-items-center rounded-md text-neutral-500 hover:bg-neutral-100"
              aria-label="검색어 지우기"
              title="검색어 지우기"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          ) : null}
          <button
            type="button"
            onClick={submitSearch}
            disabled={!trimmedQuery || isLoading}
            className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md bg-mint px-3 text-sm font-semibold text-white hover:bg-[#26765f] disabled:cursor-not-allowed disabled:bg-neutral-300"
            aria-label="검색"
            title="검색"
          >
            <Search className="h-4 w-4" aria-hidden="true" />
            검색
          </button>
        </div>

        <div className="w-full rounded-lg border border-line bg-white p-3">
          <div className="flex items-center gap-2 pb-3 text-sm font-medium">
            <SlidersHorizontal className="h-4 w-4 text-mint" aria-hidden="true" />
            <span>필터</span>
            {hasActiveFilters ? (
              <button
                type="button"
                onClick={clearFilters}
                className="ml-auto grid h-8 w-8 place-items-center rounded-md text-neutral-500 hover:bg-neutral-100"
                aria-label="필터 지우기"
                title="필터 지우기"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            ) : null}
          </div>
          <div className="grid gap-2 sm:grid-cols-[1fr_120px_120px_auto]">
            <input
              value={brand}
              onChange={(event) => setBrand(event.target.value)}
              placeholder="브랜드"
              className="h-10 rounded-md border border-line px-3 text-sm outline-none focus:border-mint"
              aria-label="브랜드 필터"
            />
            <input
              value={minPrice}
              onChange={(event) => setMinPrice(event.target.value.replace(/[^\d]/g, ""))}
              placeholder="최소가"
              inputMode="numeric"
              className="h-10 rounded-md border border-line px-3 text-sm outline-none focus:border-mint"
              aria-label="최소 가격"
            />
            <input
              value={maxPrice}
              onChange={(event) => setMaxPrice(event.target.value.replace(/[^\d]/g, ""))}
              placeholder="최대가"
              inputMode="numeric"
              className="h-10 rounded-md border border-line px-3 text-sm outline-none focus:border-mint"
              aria-label="최대 가격"
            />
            <label className="flex h-10 items-center gap-2 rounded-md border border-line px-3 text-sm">
              <input
                type="checkbox"
                checked={hasShade}
                onChange={(event) => setHasShade(event.target.checked)}
                className="h-4 w-4 accent-mint"
              />
              색상 있음
            </label>
          </div>
        </div>
      </section>

      <section className="mx-auto mt-8 w-full max-w-5xl">
        <div className="mb-4 min-h-6 text-sm text-neutral-600">{statusText}</div>

        {response?.source_errors.length ? (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            원본 사이트에서 상품 정보를 가져오지 못했습니다.
          </div>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {response?.results.map((product, index) => (
            <ProductCard key={`${product.source}-${product.product_name_ko ?? index}`} product={product} />
          ))}
        </div>

        {canLoadMore ? (
          <div className="mt-5 flex justify-center">
            <button
              type="button"
              onClick={() => setResultLimit((current) => Math.min(current + 48, MAX_RESULT_LIMIT))}
              className="h-10 rounded-md border border-line bg-white px-4 text-sm font-medium text-neutral-800 hover:border-mint hover:text-mint"
            >
              더 보기
            </button>
          </div>
        ) : null}
      </section>
    </main>
  );
}

function ProductCard({ product }: { product: Product }) {
  const [copied, setCopied] = useState(false);
  const priceText = formatPrice(product.price, product.currency);
  const copyText = [
    `브랜드명: ${product.brand_en ?? ""}`,
    `제품명: ${product.product_name_ko ?? ""}`,
    `가격: ${priceText}`,
    product.shade ? `호수: ${product.shade}` : null,
  ]
    .filter(Boolean)
    .join("\n");

  const copyProductInfo = async () => {
    try {
      await navigator.clipboard.writeText(copyText);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = copyText;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };

  const image = (
    <div className="h-24 w-24 overflow-hidden rounded-md bg-neutral-100">
      {product.image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={product.image_url}
          alt={product.product_name_ko ?? "상품 이미지"}
          className="h-full w-full object-cover transition-transform duration-150 group-hover:scale-[1.03]"
          loading="lazy"
        />
      ) : (
        <div className="grid h-full w-full place-items-center text-xs text-neutral-400">이미지 없음</div>
      )}
    </div>
  );

  const name = (
    <h2 className="line-clamp-2 text-sm font-medium leading-5">
      {product.product_name_ko ?? "상품명 미확인"}
    </h2>
  );

  return (
    <article className="grid grid-cols-[96px_1fr] gap-4 rounded-lg border border-line bg-white p-3 shadow-soft">
      {product.source_url ? (
        <a
          href={product.source_url}
          target="_blank"
          rel="noreferrer"
          className="group block"
          aria-label={`${product.product_name_ko ?? "상품"} 원본 페이지 열기`}
        >
          {image}
        </a>
      ) : (
        image
      )}

      <div className="min-w-0">
        <div className="flex items-start gap-2">
          <dl className="min-w-0 flex-1 space-y-1">
            <div>
              <dt className="text-[11px] font-medium text-neutral-500">브랜드명</dt>
              <dd className="truncate text-sm font-semibold text-mint">{product.brand_en ?? "브랜드 미확인"}</dd>
            </div>
            <div>
              <dt className="text-[11px] font-medium text-neutral-500">제품명</dt>
              <dd>
                {product.source_url ? (
                  <a
                    href={product.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="block underline-offset-2 hover:text-mint hover:underline"
                    aria-label={`${product.product_name_ko ?? "상품"} 원본 페이지 열기`}
                  >
                    {name}
                  </a>
                ) : (
                  name
                )}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] font-medium text-neutral-500">가격</dt>
              <dd className="text-sm font-semibold">{priceText}</dd>
            </div>
            {product.shade ? (
              <div>
                <dt className="text-[11px] font-medium text-neutral-500">호수</dt>
                <dd className="line-clamp-2 text-xs text-neutral-700">{product.shade}</dd>
              </div>
            ) : null}
          </dl>

          <button
            type="button"
            onClick={copyProductInfo}
            className="inline-flex h-8 shrink-0 items-center gap-1 rounded-md border border-line px-2 text-xs font-medium text-neutral-700 hover:border-mint hover:text-mint"
            aria-label="상품 정보 복사"
            title="상품 정보 복사"
          >
            {copied ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
            {copied ? "복사됨" : "복사"}
          </button>
        </div>
      </div>
    </article>
  );
}

function formatPrice(price: number | null, currency?: string | null) {
  if (price === null) return "가격 미확인";
  if (currency === "USD") return usdFormatter.format(price);
  if (currency === "JPY") return jpyFormatter.format(price);
  return currencyFormatter.format(price);
}
