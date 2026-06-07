"use client";

import { Check, Copy, Loader2, Search, X } from "lucide-react";
import type { KeyboardEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

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

const RESULT_PAGE_SIZE = 24;
const DEFAULT_RESULT_LIMIT = RESULT_PAGE_SIZE;
const MAX_RESULT_LIMIT = 480;
const MIN_LOADING_MS = 700;

export default function Home() {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [searchRun, setSearchRun] = useState(0);
  const [resultLimit, setResultLimit] = useState(DEFAULT_RESULT_LIMIT);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSearchButtonPressed, setIsSearchButtonPressed] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const searchButtonTimerRef = useRef<number | null>(null);
  const searchRequestIdRef = useRef(0);

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
  const canLoadMore = Boolean(
    response && !isSubmittedBatchQuery && response.count >= resultLimit && resultLimit < MAX_RESULT_LIMIT,
  );

  useEffect(() => {
    return () => {
      if (searchButtonTimerRef.current) {
        window.clearTimeout(searchButtonTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    setResultLimit(DEFAULT_RESULT_LIMIT);
  }, [trimmedSubmittedQuery]);

  useEffect(() => {
    if (!trimmedSubmittedQuery) {
      searchRequestIdRef.current += 1;
      setIsLoading(false);
      setErrorMessage(null);
      return;
    }

    const controller = new AbortController();
    const requestId = searchRequestIdRef.current + 1;
    searchRequestIdRef.current = requestId;
    const runSearch = async () => {
      const startedAt = Date.now();
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const data = await searchProducts(
          {
            query: trimmedSubmittedQuery,
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
        const remainingLoadingTime = MIN_LOADING_MS - (Date.now() - startedAt);
        if (remainingLoadingTime > 0) {
          await new Promise((resolve) => window.setTimeout(resolve, remainingLoadingTime));
        }
        if (searchRequestIdRef.current === requestId) {
          setIsLoading(false);
        }
      }
    };
    void runSearch();

    return () => {
      controller.abort();
    };
  }, [
    isSubmittedBatchQuery,
    resultLimit,
    searchRun,
    submittedQueryCount,
    trimmedSubmittedQuery,
  ]);

  const statusText = useMemo(() => {
    if (!trimmedSubmittedQuery) return "";
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
    trimmedSubmittedQuery,
  ]);

  const clearSearchInput = () => {
    setQuery("");
  };

  const triggerSearchButtonMotion = () => {
    if (searchButtonTimerRef.current) {
      window.clearTimeout(searchButtonTimerRef.current);
    }
    setIsSearchButtonPressed(true);
    searchButtonTimerRef.current = window.setTimeout(() => {
      setIsSearchButtonPressed(false);
      searchButtonTimerRef.current = null;
    }, 170);
  };

  const submitSearch = () => {
    if (!trimmedQuery || isLoading) {
      return;
    }
    triggerSearchButtonMotion();
    setIsLoading(true);
    setErrorMessage(null);
    setResponse(null);
    setSubmittedQuery(trimmedQuery);
    setResultLimit(DEFAULT_RESULT_LIMIT);
    setSearchRun((current) => current + 1);
  };

  const handleSearchKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey) {
      return;
    }
    event.preventDefault();
    submitSearch();
  };

  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#fff7f6_0%,#fbfffb_46%,#ffffff_100%)] px-4 py-7 text-ink sm:px-6 lg:px-8">
      <section className="mx-auto flex w-full max-w-3xl flex-col items-center gap-4 pt-4 sm:pt-8">
        <div className="flex items-center gap-2.5 rounded-full bg-white/70 px-4 py-2 text-lg font-bold text-rosewood shadow-[0_10px_30px_rgba(159,63,85,0.10)] sm:text-xl">
          <BrandIcon className="h-7 w-7" />
          GlowSearch
        </div>

        <div
          className="flex w-full items-start gap-2 rounded-[22px] border border-blush/55 bg-white/92 px-4 py-3 shadow-glow ring-1 ring-white/80 transition focus-within:border-rose/70 focus-within:shadow-[0_18px_60px_rgba(159,63,85,0.16)] sm:px-5"
          aria-busy={isLoading}
        >
          <Search className="mt-2.5 h-5 w-5 shrink-0 text-rosewood" aria-hidden="true" />
          <textarea
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={handleSearchKeyDown}
            rows={isInputBatchQuery ? Math.min(queryCount, 6) : 1}
            placeholder="관련 검색어"
            className="min-h-10 min-w-0 flex-1 resize-y border-0 bg-transparent py-2 text-lg font-medium leading-6 text-ink outline-none placeholder:text-neutral-400 sm:text-xl"
            aria-label="관련 검색어"
          />
          {query ? (
            <button
              type="button"
              onClick={clearSearchInput}
              className="grid h-10 w-10 place-items-center rounded-full text-neutral-500 transition hover:bg-blush-soft hover:text-rosewood focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blush"
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
            className={[
              "inline-flex h-10 shrink-0 items-center gap-1.5 rounded-full px-4 text-sm font-semibold text-white transition duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose sm:px-5",
              !trimmedQuery && !isLoading
                ? "cursor-not-allowed bg-neutral-300 shadow-none"
                : isLoading
                  ? "cursor-progress bg-rosewood shadow-[0_10px_22px_rgba(159,63,85,0.28)]"
                  : "bg-rosewood shadow-[0_10px_22px_rgba(159,63,85,0.28)] hover:bg-[#873247]",
              isSearchButtonPressed ? "translate-y-px scale-[0.97]" : "translate-y-0 scale-100",
            ].join(" ")}
            aria-label="검색"
            title="검색"
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Search className="h-4 w-4" aria-hidden="true" />
            )}
            {isLoading ? "검색중" : "검색"}
          </button>
        </div>

        {isLoading ? (
          <div className="inline-flex items-center gap-2 rounded-full bg-white/85 px-4 py-2 text-sm font-semibold text-rosewood shadow-[0_10px_26px_rgba(159,63,85,0.10)]">
            <Loader2 className="h-4 w-4 animate-spin text-rose" aria-hidden="true" />
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose opacity-70" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-rose" />
            </span>
            올리브영 상품 정보를 불러오는 중
          </div>
        ) : null}
      </section>

      <section className="mx-auto mt-8 w-full max-w-5xl">
        <div className="mb-4 flex min-h-6 items-center gap-2 text-sm font-medium text-neutral-600">
          {isLoading ? <Loader2 className="h-4 w-4 animate-spin text-rosewood" aria-hidden="true" /> : null}
          <span>{statusText}</span>
        </div>

        {response?.source_errors.length ? (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            원본 사이트에서 상품 정보를 가져오지 못했습니다.
          </div>
        ) : null}

        {!response && isLoading ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <ProductSkeleton key={index} />
            ))}
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
              onClick={() => setResultLimit((current) => Math.min(current + RESULT_PAGE_SIZE, MAX_RESULT_LIMIT))}
              className="h-10 rounded-full border border-line bg-white px-5 text-sm font-semibold text-neutral-800 shadow-sm transition hover:border-rose hover:text-rosewood"
            >
              더 보기
            </button>
          </div>
        ) : null}
      </section>
    </main>
  );
}

function BrandIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 96 96"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <rect width="96" height="96" rx="24" fill="#FFF0F3" />
      <circle cx="48" cy="42" r="28" fill="#FFFFFF" />
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M48 18C34.745 18 24 28.745 24 42C24 55.255 34.745 66 48 66C61.255 66 72 55.255 72 42C72 28.745 61.255 18 48 18ZM48 31C41.925 31 37 35.925 37 42C37 48.075 41.925 53 48 53C54.075 53 59 48.075 59 42C59 35.925 54.075 31 48 31Z"
        fill="#9F3F55"
      />
      <rect x="62" y="56" width="8" height="25" rx="4" transform="rotate(-45 62 56)" fill="#9F3F55" />
      <path d="M29 57L39 48L49 58L39 77L29 57Z" fill="#D76580" />
      <path d="M38 49L44 43L51 50L49 58L39 59L38 49Z" fill="#F7A5B5" />
      <path d="M28 17L31 27L41 31L31 35L28 45L25 35L15 31L25 27L28 17Z" fill="#D76580" />
      <path d="M72 16L74 23L81 26L74 29L72 36L70 29L63 26L70 23L72 16Z" fill="#F0A7B5" />
    </svg>
  );
}

function ProductCard({ product }: { product: Product }) {
  const [copied, setCopied] = useState(false);
  const originalPriceText = formatPrice(product.original_price ?? product.price, product.currency);
  const hasDiscount = Boolean(
    product.sale_price !== null
    && product.sale_price !== undefined
    && product.original_price !== null
    && product.original_price !== undefined
    && product.sale_price < product.original_price,
  );
  const salePriceText = hasDiscount && product.sale_price != null
    ? formatPrice(product.sale_price, product.currency)
    : null;
  const copyText = [
    `브랜드명: ${product.brand_ko ?? ""}`,
    `영문명: ${product.brand_en ?? ""}`,
    `제품명: ${product.product_name_ko ?? ""}`,
    `원가: ${originalPriceText}`,
    hasDiscount ? `할인가: ${salePriceText}` : null,
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
    <div className="h-24 w-24 overflow-hidden rounded-lg bg-blush-soft">
      {product.image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={product.image_url}
          alt={product.product_name_ko ?? "상품 이미지"}
          className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.04]"
          loading="lazy"
        />
      ) : (
        <div className="grid h-full w-full place-items-center text-xs text-neutral-400">이미지 없음</div>
      )}
    </div>
  );

  const name = (
    <h2 className="line-clamp-2 text-sm font-semibold leading-5 text-ink">
      {product.product_name_ko ?? "상품명 미확인"}
    </h2>
  );

  return (
    <article className="grid grid-cols-[96px_1fr] gap-4 rounded-lg border border-blush/45 bg-white p-3 shadow-soft transition duration-150 hover:-translate-y-0.5 hover:border-rose/45 hover:shadow-[0_14px_36px_rgba(74,54,63,0.10)]">
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
              <dd className="truncate text-sm font-bold text-rosewood">{product.brand_ko ?? "브랜드 미확인"}</dd>
            </div>
            <div>
              <dt className="text-[11px] font-medium text-neutral-500">영문명</dt>
              <dd className="truncate text-xs font-medium text-neutral-700">{product.brand_en ?? "영문명 미확인"}</dd>
            </div>
            <div>
              <dt className="text-[11px] font-medium text-neutral-500">제품명</dt>
              <dd>
                {product.source_url ? (
                  <a
                    href={product.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="block underline-offset-2 hover:text-rosewood hover:underline"
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
              <dt className="text-[11px] font-medium text-neutral-500">원가</dt>
              <dd className={hasDiscount ? "text-xs text-neutral-500 line-through" : "text-sm font-semibold"}>
                {originalPriceText}
              </dd>
            </div>
            {hasDiscount ? (
              <div>
                <dt className="text-[11px] font-medium text-neutral-500">할인가</dt>
                <dd className="text-sm font-bold text-rosewood">
                  {salePriceText}
                  {product.discount_rate ? (
                    <span className="ml-1 rounded-full bg-blush-soft px-1.5 py-0.5 text-[11px] font-bold text-rosewood">
                      {product.discount_rate}%
                    </span>
                  ) : null}
                </dd>
              </div>
            ) : null}
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
            className="inline-flex h-8 shrink-0 items-center gap-1 rounded-full border border-line bg-white px-2.5 text-xs font-semibold text-neutral-700 transition hover:border-rose hover:bg-blush-soft hover:text-rosewood"
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

function ProductSkeleton() {
  return (
    <article className="grid grid-cols-[96px_1fr] gap-4 rounded-lg border border-blush/45 bg-white p-3 shadow-soft">
      <div className="h-24 w-24 animate-pulse rounded-lg bg-blush-soft" />
      <div className="min-w-0 space-y-3 py-1">
        <div className="h-3 w-20 animate-pulse rounded-full bg-blush-soft" />
        <div className="h-4 w-28 animate-pulse rounded-full bg-neutral-100" />
        <div className="h-4 w-full animate-pulse rounded-full bg-neutral-100" />
        <div className="h-4 w-2/3 animate-pulse rounded-full bg-neutral-100" />
        <div className="h-5 w-24 animate-pulse rounded-full bg-blush-soft" />
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
