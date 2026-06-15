"use client";

import { Check, ChevronRight, Copy, ExternalLink, Loader2, Search, X } from "lucide-react";
import type { KeyboardEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import { confirmEditorCandidate, fetchSearchSuggestions, organizeEditorBatch, searchProducts } from "@/lib/api";
import type {
  EditorBatchItem,
  EditorBatchResponse,
  EditorConfirmRequest,
  Product,
  ProductOffer,
  SearchResponse,
} from "@/types/product";

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

const RESULT_PAGE_SIZE = 48;
const DEFAULT_RESULT_LIMIT = RESULT_PAGE_SIZE;
const MAX_RESULT_LIMIT = 480;
const MAX_PAGE_COUNT = MAX_RESULT_LIMIT / RESULT_PAGE_SIZE;
const MIN_LOADING_MS = 180;
const EMPTY_SEARCH_SUGGESTIONS = ["선크림", "틴트", "쿠션", "롬앤", "too cool", "정샘물"];
const EDITOR_SAMPLE_TEXT = [
  "헤라 파우더 #13N1",
  "어반디케이 파우더",
  "롬앤 쉐딩 #그레이쿨",
  "페리페라 스키니브로우",
  "클리오 치즈냥이",
  "키스미 아이브로우",
  "뮤드 브로우카라",
  "하밍 젤리 에어 치크 7호",
  "캔메이크 아라 카푸치노",
  "홀리카 팔레트 #핑크올로지",
  "어반디케이 문더스트 #글림락",
  "하트퍼센트 립베이스",
  "페리페라 포근 픽싱 틴트 19호",
  "아멜리 하이라이터 #432",
  "오프라 하이라이터",
  "머지 더블 글레이즈 #브레이브미",
  "비디비치 틴트밤 #카라멜허그",
].join("\n");

export default function Home() {
  const [mode, setMode] = useState<"search" | "editor">("search");
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [searchRun, setSearchRun] = useState(0);
  const [resultLimit, setResultLimit] = useState(DEFAULT_RESULT_LIMIT);
  const [currentPage, setCurrentPage] = useState(1);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSearchButtonPressed, setIsSearchButtonPressed] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [isSuggestionsOpen, setIsSuggestionsOpen] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const searchButtonTimerRef = useRef<number | null>(null);
  const searchRequestIdRef = useRef(0);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("mode") === "editor") {
      setMode("editor");
    }
  }, []);

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
  const loadedResultCount = response?.results.length ?? 0;
  const loadedPageCount = Math.max(1, Math.ceil(Math.max(loadedResultCount, 1) / RESULT_PAGE_SIZE));
  const mayHaveMorePages = Boolean(
    response && !isSubmittedBatchQuery && response.count >= resultLimit && resultLimit < MAX_RESULT_LIMIT,
  );
  const totalPageCount = response && !isSubmittedBatchQuery && loadedResultCount > 0
    ? mayHaveMorePages
      ? MAX_PAGE_COUNT
      : loadedPageCount
    : 0;
  const boundedCurrentPage = Math.min(currentPage, Math.max(totalPageCount, 1));
  const visibleStartIndex = (boundedCurrentPage - 1) * RESULT_PAGE_SIZE;
  const visibleEndIndex = visibleStartIndex + RESULT_PAGE_SIZE;
  const visibleResults = response?.results.slice(visibleStartIndex, visibleEndIndex) ?? [];
  const canShowSuggestions = Boolean(
    isSuggestionsOpen && trimmedQuery && !isInputBatchQuery && suggestions.length > 0,
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
    setCurrentPage(1);
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

  useEffect(() => {
    if (!trimmedQuery || isInputBatchQuery) {
      setSuggestions([]);
      setActiveSuggestionIndex(-1);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      fetchSearchSuggestions(trimmedQuery, controller.signal)
        .then((data) => {
          setSuggestions(data.suggestions.filter((suggestion) => suggestion !== trimmedQuery));
          setActiveSuggestionIndex(-1);
        })
        .catch((error) => {
          if (error instanceof DOMException && error.name === "AbortError") return;
          setSuggestions([]);
          setActiveSuggestionIndex(-1);
        });
    }, 120);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [isInputBatchQuery, trimmedQuery]);

  const statusText = useMemo(() => {
    if (!trimmedSubmittedQuery) return "";
    if (isLoading) return "검색 중입니다.";
    if (errorMessage) return errorMessage;
    if (response && response.count === 0) return "검색 결과가 없습니다.";
    if (response && isSubmittedBatchQuery) {
      return `${submittedQueryCount.toLocaleString("ko-KR")}개 검색어 중 ${response.count.toLocaleString("ko-KR")}개 결과`;
    }
    if (response && !isSubmittedBatchQuery && response.count > 0) {
      const end = Math.min(visibleEndIndex, response.count);
      return `${response.count.toLocaleString("ko-KR")}개 결과 중 ${(visibleStartIndex + 1).toLocaleString("ko-KR")}-${end.toLocaleString("ko-KR")} 표시`;
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
    visibleEndIndex,
    visibleStartIndex,
  ]);

  const clearSearchInput = () => {
    setQuery("");
    setSuggestions([]);
    setIsSuggestionsOpen(false);
    setActiveSuggestionIndex(-1);
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

  const submitSearch = (nextQuery?: string) => {
    const searchQuery = (nextQuery ?? query).trim();
    if (!searchQuery || isLoading) {
      return;
    }
    triggerSearchButtonMotion();
    setIsLoading(true);
    setErrorMessage(null);
    setResponse(null);
    setQuery(searchQuery);
    setSubmittedQuery(searchQuery);
    setIsSuggestionsOpen(false);
    setActiveSuggestionIndex(-1);
    setResultLimit(DEFAULT_RESULT_LIMIT);
    setCurrentPage(1);
    setSearchRun((current) => current + 1);
  };

  const chooseSuggestion = (suggestion: string) => {
    submitSearch(suggestion);
  };

  const goToPage = (page: number) => {
    const nextPage = Math.min(Math.max(page, 1), MAX_PAGE_COUNT);
    setCurrentPage(nextPage);
    const nextLimit = nextPage * RESULT_PAGE_SIZE;
    if (nextLimit > resultLimit) {
      setResultLimit(Math.min(nextLimit, MAX_RESULT_LIMIT));
    }
  };

  const handleSearchKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.nativeEvent.isComposing) {
      return;
    }
    if (canShowSuggestions && event.key === "ArrowDown") {
      event.preventDefault();
      setActiveSuggestionIndex((current) => (current + 1) % suggestions.length);
      return;
    }
    if (canShowSuggestions && event.key === "ArrowUp") {
      event.preventDefault();
      setActiveSuggestionIndex((current) => (
        current <= 0 ? suggestions.length - 1 : current - 1
      ));
      return;
    }
    if (event.key !== "Enter" || event.shiftKey) {
      return;
    }
    event.preventDefault();
    if (canShowSuggestions && activeSuggestionIndex >= 0) {
      chooseSuggestion(suggestions[activeSuggestionIndex]);
      return;
    }
    submitSearch();
  };

  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#fff7f6_0%,#fbfffb_46%,#ffffff_100%)] px-4 py-7 text-ink sm:px-6 lg:px-8">
      <section className="mx-auto flex w-full max-w-3xl flex-col items-center gap-4 pt-4 sm:pt-8">
        <div className="text-4xl font-extrabold text-rosewood sm:text-5xl">
          GlowSearch
        </div>

        <div className="inline-flex rounded-full border border-blush/70 bg-white p-1 shadow-soft" aria-label="작업 모드">
          <button
            type="button"
            onClick={() => setMode("search")}
            className={[
              "rounded-full px-4 py-2 text-sm font-bold transition",
              mode === "search" ? "bg-rosewood text-white shadow-sm" : "text-neutral-600 hover:bg-blush-soft hover:text-rosewood",
            ].join(" ")}
            aria-pressed={mode === "search"}
          >
            제품 검색
          </button>
          <button
            type="button"
            onClick={() => setMode("editor")}
            className={[
              "rounded-full px-4 py-2 text-sm font-bold transition",
              mode === "editor" ? "bg-rosewood text-white shadow-sm" : "text-neutral-600 hover:bg-blush-soft hover:text-rosewood",
            ].join(" ")}
            aria-pressed={mode === "editor"}
          >
            편집자 일괄 정리
          </button>
        </div>

        {mode === "search" ? (
          <>
        <div className="relative w-full">
          <div
            className="flex w-full items-start gap-2 rounded-[22px] border border-blush/55 bg-white/92 px-4 py-3 shadow-glow ring-1 ring-white/80 transition focus-within:border-rose/70 focus-within:shadow-[0_18px_60px_rgba(159,63,85,0.16)] sm:px-5"
            aria-busy={isLoading}
          >
            <Search className="mt-2.5 h-5 w-5 shrink-0 text-rosewood" aria-hidden="true" />
            <textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={handleSearchKeyDown}
              onFocus={() => setIsSuggestionsOpen(true)}
              onBlur={() => {
                window.setTimeout(() => setIsSuggestionsOpen(false), 120);
              }}
              rows={isInputBatchQuery ? Math.min(queryCount, 6) : 1}
              placeholder="브랜드, 제품명, 성분 검색"
              className="min-h-10 min-w-0 flex-1 resize-y border-0 bg-transparent py-2 text-lg font-medium leading-6 text-ink outline-none placeholder:text-neutral-400 sm:text-xl"
              aria-label="브랜드, 제품명, 성분 검색"
              aria-expanded={canShowSuggestions}
              aria-controls={canShowSuggestions ? "search-suggestions" : undefined}
              aria-activedescendant={
                canShowSuggestions && activeSuggestionIndex >= 0
                  ? `search-suggestion-${activeSuggestionIndex}`
                  : undefined
              }
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
              onClick={() => submitSearch()}
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

          {canShowSuggestions ? (
            <SuggestionDropdown
              activeIndex={activeSuggestionIndex}
              query={trimmedQuery}
              suggestions={suggestions}
              onChoose={chooseSuggestion}
            />
          ) : null}
        </div>

        {isInputBatchQuery ? (
          <div className="text-xs font-semibold text-neutral-500">
            {queryCount.toLocaleString("ko-KR")}개 검색어 배치 검색
          </div>
        ) : null}

        {isLoading ? (
          <div className="inline-flex items-center gap-2 rounded-full bg-white/85 px-4 py-2 text-sm font-semibold text-rosewood shadow-[0_10px_26px_rgba(159,63,85,0.10)]">
            <Loader2 className="h-4 w-4 animate-spin text-rose" aria-hidden="true" />
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose opacity-70" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-rose" />
            </span>
            상품과 브랜드 정보를 찾는 중
          </div>
        ) : null}
          </>
        ) : null}
      </section>

      {mode === "editor" ? (
        <EditorBatchWorkspace />
      ) : (
        <section className="mx-auto mt-8 w-full max-w-5xl">
        <div className="mb-4 flex min-h-6 items-center gap-2 text-sm font-medium text-neutral-600">
          {isLoading ? <Loader2 className="h-4 w-4 animate-spin text-rosewood" aria-hidden="true" /> : null}
          <span>{statusText}</span>
        </div>

        {response?.source_errors.length && response.results.length ? (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            일부 소스가 지연되어 확인 가능한 결과부터 표시합니다.
          </div>
        ) : null}

        {(!response || (isLoading && visibleResults.length === 0)) && isLoading ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <ProductSkeleton key={index} />
            ))}
          </div>
        ) : null}

        {response && response.results.length === 0 && !isLoading ? (
          <EmptySearchState onChoose={submitSearch} />
        ) : null}

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {visibleResults.map((product, index) => (
            <ProductCard key={`${product.source}-${product.product_name_ko ?? index}`} product={product} />
          ))}
        </div>

        {totalPageCount > 1 ? (
          <Pagination
            currentPage={boundedCurrentPage}
            totalPageCount={totalPageCount}
            isLoading={isLoading}
            onPageChange={goToPage}
          />
        ) : null}
        </section>
      )}
    </main>
  );
}

function EmptySearchState({ onChoose }: { onChoose: (query: string) => void }) {
  return (
    <div className="rounded-lg border border-blush/55 bg-white/88 px-5 py-8 text-center shadow-soft">
      <p className="text-base font-bold text-rosewood">검색 결과가 없습니다.</p>
      <p className="mt-2 text-sm text-neutral-600">
        다른 표기나 대표 카테고리로 다시 검색해 보세요.
      </p>
      <div className="mt-5 flex flex-wrap justify-center gap-2">
        {EMPTY_SEARCH_SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            onClick={() => onChoose(suggestion)}
            className="rounded-full border border-blush/70 bg-blush-soft px-3 py-1.5 text-sm font-semibold text-rosewood transition hover:border-rose hover:bg-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}

function EditorBatchWorkspace() {
  const [text, setText] = useState("");
  const [response, setResponse] = useState<EditorBatchResponse | null>(null);
  const [selected, setSelected] = useState<Record<number, number>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [copiedFormat, setCopiedFormat] = useState<string | null>(null);
  const [savedRows, setSavedRows] = useState<Record<number, boolean>>({});
  const [savingRows, setSavingRows] = useState<Record<number, boolean>>({});
  const requestIdRef = useRef(0);

  const lineCount = useMemo(
    () => text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).length,
    [text],
  );
  const canSubmit = Boolean(text.trim()) && !isLoading;

  const runBatch = async () => {
    const input = text.trim();
    if (!input || isLoading) return;
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const data = await organizeEditorBatch(input);
      if (requestIdRef.current !== requestId) return;
      setResponse(data);
      setSelected(initialEditorSelection(data));
      setSavedRows({});
      setSavingRows({});
    } catch (error) {
      if (requestIdRef.current !== requestId) return;
      setErrorMessage("일괄 정리 중 문제가 발생했습니다.");
      setResponse(null);
      setSelected({});
      setSavedRows({});
      setSavingRows({});
    } finally {
      if (requestIdRef.current === requestId) {
        setIsLoading(false);
      }
    }
  };

  const copyEditorFormat = async (format: "ko" | "en" | "description" | "tsv" | "csv") => {
    if (!response) return;
    const payload = editorCopyPayload(response.items, selected, format);
    if (!payload) return;
    await copyToClipboard(payload);
    setCopiedFormat(format);
    window.setTimeout(() => setCopiedFormat(null), 1200);
  };

  const confirmSelection = async (index: number) => {
    const item = response?.items[index];
    const product = item ? selectedEditorProduct(item, selected, index) : null;
    if (!item || !product || savingRows[index]) return;
    setSavingRows((current) => ({ ...current, [index]: true }));
    try {
      await confirmEditorCandidate(editorConfirmPayload(item, product));
      setSavedRows((current) => ({ ...current, [index]: true }));
    } catch {
      setErrorMessage("정답 저장 중 문제가 발생했습니다.");
    } finally {
      setSavingRows((current) => ({ ...current, [index]: false }));
    }
  };

  return (
    <section className="mx-auto mt-8 w-full max-w-6xl">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <div className="min-w-0 rounded-lg border border-blush/55 bg-white/92 p-4 shadow-soft">
          <label htmlFor="editor-batch-input" className="text-sm font-bold text-rosewood">
            러프 제품 리스트
          </label>
          <textarea
            id="editor-batch-input"
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={14}
            placeholder={EDITOR_SAMPLE_TEXT}
            className="mt-3 min-h-72 w-full resize-y rounded-lg border border-line bg-white p-3 text-sm font-medium leading-6 text-ink outline-none transition placeholder:text-neutral-400 focus:border-rose"
            aria-label="편집자 일괄 정리 입력"
          />
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <span className="text-xs font-semibold text-neutral-500">
              {lineCount ? `${lineCount.toLocaleString("ko-KR")}개 라인` : "여러 줄을 붙여넣으세요"}
            </span>
            <div className="flex min-w-0 flex-wrap gap-2 sm:justify-end">
              <button
                type="button"
                onClick={() => setText(EDITOR_SAMPLE_TEXT)}
                className="min-w-0 rounded-full border border-line bg-white px-3 py-2 text-xs font-bold text-neutral-700 transition hover:border-rose hover:bg-blush-soft hover:text-rosewood"
              >
                예시 넣기
              </button>
              <button
                type="button"
                onClick={runBatch}
                disabled={!canSubmit}
                className="inline-flex min-w-0 items-center gap-1.5 rounded-full bg-rosewood px-4 py-2 text-sm font-bold text-white transition hover:bg-[#873247] disabled:cursor-not-allowed disabled:bg-neutral-300"
              >
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Search className="h-4 w-4" aria-hidden="true" />}
                정리하기
              </button>
            </div>
          </div>
          {errorMessage ? (
            <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              {errorMessage}
            </div>
          ) : null}
        </div>

        <div className="min-w-0 rounded-lg border border-blush/55 bg-white/92 p-4 shadow-soft">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-base font-extrabold text-rosewood">정리 결과</h2>
              <p className="mt-1 text-xs font-medium text-neutral-500">
                source URL이 있는 후보만 표시합니다.
              </p>
            </div>
            <div className="grid min-w-0 grid-cols-1 gap-1.5 sm:flex sm:flex-wrap sm:justify-end">
              {[
                ["ko", "한글 자막"],
                ["en", "영문 자막"],
                ["description", "더보기란"],
                ["tsv", "TSV"],
                ["csv", "CSV"],
              ].map(([format, label]) => (
                <button
                  key={format}
                  type="button"
                  onClick={() => copyEditorFormat(format as "ko" | "en" | "description" | "tsv" | "csv")}
                  disabled={!response}
                  className="inline-flex min-w-0 items-center justify-center gap-1 rounded-full border border-line bg-white px-2.5 py-1.5 text-xs font-bold text-neutral-700 transition hover:border-rose hover:bg-blush-soft hover:text-rosewood disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {copiedFormat === format ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-4 max-h-[68vh] space-y-3 overflow-y-auto pr-1 lg:max-h-[640px]">
            {isLoading ? (
              <div className="flex items-center gap-2 rounded-lg bg-blush-soft px-3 py-4 text-sm font-bold text-rosewood">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                후보를 찾는 중
              </div>
            ) : null}
            {!response && !isLoading ? (
              <div className="rounded-lg border border-dashed border-blush/70 px-4 py-8 text-center text-sm font-medium text-neutral-500">
                제품 리스트를 붙여넣고 정리하면 행별 후보가 표시됩니다.
              </div>
            ) : null}
            {response?.items.map((item, index) => (
              <EditorBatchRow
                key={`${item.raw_text}-${index}`}
                item={item}
                index={index}
                selectedIndex={selected[index]}
                isSaved={Boolean(savedRows[index])}
                isSaving={Boolean(savingRows[index])}
                onSelect={(candidateIndex) => {
                  setSelected((current) => ({ ...current, [index]: candidateIndex }));
                  setSavedRows((current) => ({ ...current, [index]: false }));
                }}
                onConfirm={() => confirmSelection(index)}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function EditorBatchRow({
  item,
  index,
  selectedIndex,
  isSaved,
  isSaving,
  onSelect,
  onConfirm,
}: {
  item: EditorBatchItem;
  index: number;
  selectedIndex?: number;
  isSaved: boolean;
  isSaving: boolean;
  onSelect: (candidateIndex: number) => void;
  onConfirm: () => void;
}) {
  const selectedCandidate = selectedIndex !== undefined ? item.candidates[selectedIndex] : undefined;
  const selectedProduct = selectedCandidate?.product;
  const status = isSaved ? "확인됨" : item.status;
  const shadeCode = item.parsed.shade_code;
  const shadeName = selectedProduct?.shade ?? item.parsed.shade_name;
  const brandKo = selectedProduct?.brand_ko ?? item.parsed.brand_query;
  const brandEn = selectedProduct?.brand_en ?? item.parsed.brand_en;
  const selectedOriginalPrice = selectedProduct
    ? formatPrice(selectedProduct.original_price ?? selectedProduct.price, selectedProduct.currency)
    : null;
  const selectedSalePrice = selectedProduct?.sale_price != null
    ? formatPrice(selectedProduct.sale_price, selectedProduct.currency)
    : null;

  return (
    <article className="rounded-lg border border-line bg-white p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[11px] font-bold text-neutral-500">원문 입력</div>
          <div className="break-words text-sm font-bold text-ink">{item.raw_text}</div>
        </div>
        <StatusBadge status={status} />
      </div>

      <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
        <Field label="브랜드명" value={brandKo} />
        <Field label="영문 브랜드명" value={brandEn} />
        <Field label="제품명" value={selectedProduct?.product_name_ko} />
        <Field label="영문 제품명" value={selectedProduct?.product_name_en} />
        <Field label="호수 번호" value={shadeCode} />
        <Field label="호수명 / 컬러명" value={shadeName} />
      </dl>

      {selectedProduct ? (
        <div className="mt-3 grid gap-3 rounded-lg bg-blush-soft/45 p-3 sm:grid-cols-[72px_1fr]">
          {selectedProduct.image_url ? (
            <div className="h-[72px] w-[72px] overflow-hidden rounded-lg bg-white">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={selectedProduct.image_url}
                alt={selectedProduct.product_name_ko ?? item.raw_text}
                className="h-full w-full object-cover"
                loading="lazy"
              />
            </div>
          ) : null}
          <dl className="grid min-w-0 gap-2 text-xs sm:grid-cols-2">
            <Field label="가격" value={selectedOriginalPrice} />
            <Field label="할인가" value={selectedSalePrice} />
            <Field label="이미지 URL" value={selectedProduct.image_url} />
          </dl>
        </div>
      ) : null}

      {selectedProduct ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {sourceLinksForEditorProduct(selectedProduct).map((link) => (
            <a
              key={`${link.source}-${link.source_url}`}
              href={link.source_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex max-w-full items-center gap-1 rounded-full border border-line bg-white px-2.5 py-1 text-xs font-bold text-neutral-700 transition hover:border-rose hover:bg-blush-soft hover:text-rosewood"
            >
              <span className="truncate">{sourceLabel(link)}</span>
              <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
            </a>
          ))}
          <button
            type="button"
            onClick={onConfirm}
            disabled={isSaving || isSaved}
            className="inline-flex max-w-full items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-700 transition hover:border-emerald-300 hover:bg-white disabled:cursor-default disabled:opacity-70"
          >
            {isSaving ? <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" /> : <Check className="h-3 w-3" aria-hidden="true" />}
            {isSaved ? "저장됨" : "정답 저장"}
          </button>
        </div>
      ) : null}

      {item.candidates.length ? (
        <div className="mt-3 space-y-2">
          <div className="text-[11px] font-bold text-neutral-500">후보</div>
          {item.candidates.map((candidate, candidateIndex) => (
            <button
              key={`${candidate.product.source}-${candidate.product.source_product_id ?? candidateIndex}`}
              type="button"
              onClick={() => onSelect(candidateIndex)}
              className={[
                "w-full rounded-lg border px-3 py-2 text-left transition",
                selectedIndex === candidateIndex
                  ? "border-rose bg-blush-soft"
                  : "border-line bg-white hover:border-rose/70 hover:bg-blush-soft/60",
              ].join(" ")}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="break-words text-sm font-bold text-ink">
                  {[candidate.product.brand_ko, candidate.product.product_name_ko].filter(Boolean).join(" / ")}
                </span>
                <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-bold text-neutral-600">
                  후보 {candidateIndex + 1}
                </span>
              </div>
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-neutral-600">
                {candidate.product.brand_en ? <span>{candidate.product.brand_en}</span> : null}
                {candidate.product.product_name_en ? <span>{candidate.product.product_name_en}</span> : null}
                {candidate.product.shade ? <span>{candidate.product.shade}</span> : null}
                {candidatePriceText(candidate.product) ? <span>{candidatePriceText(candidate.product)}</span> : null}
                <span>{sourceLabel(candidate.product)}</span>
              </div>
            </button>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function Field({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div className="min-w-0">
      <dt className="font-bold text-neutral-500">{label}</dt>
      <dd className="break-words font-semibold text-neutral-800">{value}</dd>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const className = status === "확인됨"
    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
    : status === "후보 있음"
      ? "border-amber-200 bg-amber-50 text-amber-800"
      : "border-neutral-200 bg-neutral-50 text-neutral-600";
  return (
    <span className={`rounded-full border px-2.5 py-1 text-xs font-extrabold ${className}`}>
      {status}
    </span>
  );
}

function SuggestionDropdown({
  suggestions,
  query,
  activeIndex,
  onChoose,
}: {
  suggestions: string[];
  query: string;
  activeIndex: number;
  onChoose: (suggestion: string) => void;
}) {
  return (
    <div className="absolute left-0 right-0 top-[calc(100%+0.5rem)] z-20 max-h-[min(420px,60vh)] overflow-y-auto rounded-[22px] border border-blush/55 bg-white/96 py-3 shadow-[0_24px_70px_rgba(74,54,63,0.13)] ring-1 ring-white/80 backdrop-blur">
      <ul id="search-suggestions" role="listbox" aria-label="관련 검색어">
        {suggestions.map((suggestion, index) => {
          const isActive = index === activeIndex;
          return (
            <li key={suggestion}>
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => onChoose(suggestion)}
                className={[
                  "flex w-full items-center break-words px-6 py-3 text-left text-base font-semibold transition sm:px-8 sm:text-lg",
                  isActive
                    ? "bg-blush-soft text-rosewood"
                    : "text-ink hover:bg-blush-soft/70 hover:text-rosewood",
                ].join(" ")}
                id={`search-suggestion-${index}`}
                role="option"
                aria-selected={isActive}
              >
                <HighlightedSuggestion value={suggestion} query={query} />
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function HighlightedSuggestion({ value, query }: { value: string; query: string }) {
  const trimmedQuery = query.trim();
  if (!trimmedQuery) return <>{value}</>;

  const index = value.toLocaleLowerCase().indexOf(trimmedQuery.toLocaleLowerCase());
  if (index < 0) return <>{value}</>;

  const before = value.slice(0, index);
  const match = value.slice(index, index + trimmedQuery.length);
  const after = value.slice(index + trimmedQuery.length);

  return (
    <>
      {before}
      <span className="font-extrabold text-[#45B316]">{match}</span>
      {after}
    </>
  );
}

function Pagination({
  currentPage,
  totalPageCount,
  isLoading,
  onPageChange,
}: {
  currentPage: number;
  totalPageCount: number;
  isLoading: boolean;
  onPageChange: (page: number) => void;
}) {
  const pages = Array.from({ length: totalPageCount }, (_, index) => index + 1);
  return (
    <nav className="mt-9 flex items-center justify-center gap-5 text-neutral-700" aria-label="검색 결과 페이지">
      {pages.map((page) => {
        const isActive = page === currentPage;
        return (
          <button
            key={page}
            type="button"
            onClick={() => onPageChange(page)}
            disabled={isLoading && !isActive}
            className={[
              "grid h-9 w-9 place-items-center text-xl transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose",
              isActive
                ? "font-extrabold text-ink"
                : "font-medium text-neutral-600 hover:text-rosewood",
              isLoading && !isActive ? "cursor-wait opacity-50" : "",
            ].join(" ")}
            aria-current={isActive ? "page" : undefined}
            aria-label={`${page}페이지`}
          >
            {page}
          </button>
        );
      })}
      <button
        type="button"
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage >= totalPageCount || isLoading}
        className="grid h-9 w-9 place-items-center text-ink transition hover:text-rosewood disabled:cursor-not-allowed disabled:opacity-30"
        aria-label="다음 페이지"
      >
        <ChevronRight className="h-7 w-7" aria-hidden="true" />
      </button>
    </nav>
  );
}

function ProductCard({ product }: { product: Product }) {
  const [copied, setCopied] = useState(false);
  const productNameEn = distinctText(product.product_name_en, product.product_name_ko);
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
    product.brand_ko ? `브랜드명: ${product.brand_ko}` : null,
    product.brand_en ? `영문 브랜드명: ${product.brand_en}` : null,
    product.product_name_ko ? `제품명: ${product.product_name_ko}` : null,
    productNameEn ? `영문 제품명: ${productNameEn}` : null,
    originalPriceText ? `원가: ${originalPriceText}` : null,
    hasDiscount ? `할인가: ${salePriceText}` : null,
    product.shade ? `호수: ${product.shade}` : null,
    `출처: ${sourceLabel(product)}`,
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
      {product.product_name_ko}
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
        <div className="mb-2 flex items-center justify-between gap-2">
          <SourceBadge product={product} />
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
        <div>
          {(product.brand_ko || product.brand_en) ? (
            <div className="mb-2 min-w-0">
              <div className="text-[11px] font-medium text-neutral-500">브랜드</div>
              <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
                {product.brand_ko ? (
                  <span className="whitespace-normal break-words text-sm font-bold leading-5 text-rosewood">
                    {product.brand_ko}
                  </span>
                ) : null}
                {product.brand_en ? (
                  <span className="whitespace-normal break-words text-xs font-semibold leading-4 text-neutral-700">
                    {product.brand_en}
                  </span>
                ) : null}
              </div>
            </div>
          ) : null}
          <dl className="min-w-0 space-y-1">
            {product.product_name_ko ? (
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
            ) : null}
            {productNameEn ? (
              <div>
                <dt className="text-[11px] font-medium text-neutral-500">영문 제품명</dt>
                <dd className="whitespace-normal break-words text-xs font-medium leading-4 text-neutral-700">{productNameEn}</dd>
              </div>
            ) : null}
            {originalPriceText ? (
              <div>
                <dt className="text-[11px] font-medium text-neutral-500">원가</dt>
                <dd className={hasDiscount ? "text-xs text-neutral-500 line-through" : "text-sm font-semibold"}>
                  {originalPriceText}
                </dd>
              </div>
            ) : null}
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
        </div>
      </div>
    </article>
  );
}

function distinctText(value?: string | null, compareTo?: string | null) {
  if (!value) return null;
  if (!compareTo) return value;
  return value.trim().toLocaleLowerCase() === compareTo.trim().toLocaleLowerCase() ? null : value;
}

function SourceBadge({ product }: { product: Product }) {
  return (
    <span className="inline-flex max-w-full items-center rounded-full border border-blush/60 bg-blush-soft/70 px-2 py-0.5 text-[11px] font-bold text-rosewood">
      <span className="truncate">{sourceLabel(product)}</span>
    </span>
  );
}

function initialEditorSelection(response: EditorBatchResponse) {
  return response.items.reduce<Record<number, number>>((selected, item, index) => {
    if (item.candidates.length) {
      selected[index] = 0;
    }
    return selected;
  }, {});
}

function selectedEditorProduct(
  item: EditorBatchItem,
  selected: Record<number, number>,
  index: number,
) {
  const selectedIndex = selected[index];
  if (selectedIndex === undefined) return null;
  return item.candidates[selectedIndex]?.product ?? null;
}

function editorCopyPayload(
  items: EditorBatchItem[],
  selected: Record<number, number>,
  format: "ko" | "en" | "description" | "tsv" | "csv",
) {
  const rows = items.map((item, index) => ({
    item,
    product: selectedEditorProduct(item, selected, index),
  }));

  if (format === "tsv") {
    return editorDelimitedPayload(rows, "\t");
  }

  if (format === "csv") {
    return editorDelimitedPayload(rows, ",");
  }

  const lines = rows
    .map(({ item, product }) => {
      if (!product) return null;
      const shade = product.shade ?? item.parsed.shade_name ?? item.parsed.shade_code;
      if (format === "ko") {
        return [product.brand_ko, product.product_name_ko, shade].filter(Boolean).join(" / ");
      }
      if (format === "en") {
        return [product.brand_en ?? item.parsed.brand_en, product.product_name_en, shade].filter(Boolean).join(" / ");
      }
      const title = [product.brand_ko, product.product_name_ko, shade].filter(Boolean).join(" - ");
      const link = bestEditorSourceUrl(product);
      return [title, link].filter(Boolean).join("\n");
    })
    .filter(Boolean);
  return lines.join(format === "description" ? "\n\n" : "\n");
}

function editorDelimitedPayload(
  rows: Array<{ item: EditorBatchItem; product: Product | null }>,
  delimiter: "\t" | ",",
) {
  const header = [
    "원문 입력",
    "브랜드명",
    "영문 브랜드명",
    "제품명",
    "영문 제품명",
    "호수 번호",
    "호수명 / 컬러명",
    "가격",
    "할인가",
    "이미지 URL",
    "source 링크",
    "상태",
  ];
  return [
    editorDelimitedRow(header, delimiter),
    ...rows.map(({ item, product }) => editorDelimitedRow([
      item.raw_text,
      product?.brand_ko ?? item.parsed.brand_query ?? "",
      product?.brand_en ?? item.parsed.brand_en ?? "",
      product?.product_name_ko ?? "",
      product?.product_name_en ?? "",
      item.parsed.shade_code ?? "",
      product?.shade ?? item.parsed.shade_name ?? "",
      formatPrice(product?.original_price ?? product?.price ?? null, product?.currency) ?? "",
      product?.sale_price != null ? formatPrice(product.sale_price, product.currency) ?? "" : "",
      product?.image_url ?? "",
      bestEditorSourceUrl(product) ?? "",
      item.status,
    ], delimiter)),
  ].join("\n");
}

function editorDelimitedRow(values: string[], delimiter: "\t" | ",") {
  if (delimiter === "\t") return values.join("\t");
  return values.map(csvEscape).join(",");
}

function csvEscape(value: string) {
  if (!/[",\n\r]/.test(value)) return value;
  return `"${value.replaceAll("\"", "\"\"")}"`;
}

function editorConfirmPayload(item: EditorBatchItem, product: Product): EditorConfirmRequest {
  return {
    raw_text: item.raw_text,
    normalized_query: item.parsed.normalized_query,
    canonical_product_id: product.canonical_product_id,
    source: product.source,
    source_url: bestEditorSourceUrl(product),
    source_product_id: product.source_product_id,
    brand_ko: product.brand_ko,
    brand_en: product.brand_en ?? item.parsed.brand_en,
    product_name_ko: product.product_name_ko,
    product_name_en: product.product_name_en,
    shade: product.shade ?? item.parsed.shade_name ?? item.parsed.shade_code,
  };
}

async function copyToClipboard(value: string) {
  try {
    await navigator.clipboard.writeText(value);
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
  }
}

function sourceLinksForEditorProduct(product: Product): Array<Pick<ProductOffer, "source" | "source_label" | "source_url">> {
  const links = (product.offers ?? [])
    .filter((offer) => offer.source_url)
    .map((offer) => ({
      source: offer.source,
      source_label: offer.source_label,
      source_url: offer.source_url,
    }));
  if (links.length) return links;
  if (!product.source_url) return [];
  return [
    {
      source: product.source,
      source_label: product.source_label,
      source_url: product.source_url,
    },
  ];
}

function bestEditorSourceUrl(product: Product | null) {
  if (!product) return null;
  return sourceLinksForEditorProduct(product)[0]?.source_url ?? null;
}

function candidatePriceText(product: Product) {
  const salePrice = product.sale_price != null ? formatPrice(product.sale_price, product.currency) : null;
  if (salePrice) return salePrice;
  return formatPrice(product.price ?? product.original_price ?? null, product.currency);
}

function sourceLabel(sourceInfo: { source: string; source_label?: string | null }) {
  if (sourceInfo.source_label) return sourceInfo.source_label;
  if (sourceInfo.source === "oliveyoung" || sourceInfo.source.startsWith("oliveyoung:")) return "Olive Young";
  if (sourceInfo.source === "oliveyoung-global" || sourceInfo.source.startsWith("oliveyoung-global:")) return "Olive Young Global";
  if (sourceInfo.source === "musinsa" || sourceInfo.source.startsWith("musinsa:")) return "Musinsa";
  if (sourceInfo.source === "official" || sourceInfo.source.startsWith("official:")) return "Official brand";
  if (sourceInfo.source === "barcode" || sourceInfo.source.startsWith("barcode:")) return "Barcode/GTIN";
  if (sourceInfo.source === "discovery" || sourceInfo.source.startsWith("discovery:")) return "Discovery";
  return sourceInfo.source;
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
  if (price === null) return null;
  if (currency === "USD") return usdFormatter.format(price);
  if (currency === "JPY") return jpyFormatter.format(price);
  return currencyFormatter.format(price);
}
