"use client";

import { AlertTriangle, CheckCircle2, ExternalLink, Loader2, RotateCcw, Search, X, XCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  AdminReviewApiError,
  AdminReviewMalformedResponseError,
  AdminReviewNetworkError,
  AdminReviewTimeoutError,
  fetchMatchDetail,
  fetchPendingMatches,
  reviewMatch,
} from "@/lib/adminReviewApi";
import type {
  MatchDetail,
  MatchOfferSummary,
  MatchReviewDecision,
  MatchReviewState,
  MatchTargetSummary,
  PendingMatchSummary,
} from "@/types/review";

const PAGE_SIZE = 20;
const REVIEWER_STORAGE_KEY = "glowsearch_admin_reviewer_name";

type Banner = { tone: "success" | "conflict" | "error"; text: string };
type SortMode = "queue" | "confidence-asc" | "confidence-desc";

const REVIEW_STATE_LABELS: Record<MatchReviewState, string> = {
  verified: "검증됨",
  pending_review: "검토 대기",
  rejected: "거부됨",
  invalid: "무효 처리됨",
};

/**
 * One place to turn any error this page can encounter into a message a
 * reviewer can act on. Distinguishes what `adminReviewApi.ts` distinguishes
 * — a real HTTP status vs. a timeout vs. "never got a response at all" vs.
 * "got a response that isn't valid JSON" — rather than collapsing
 * everything into one generic string (§6: timeout / network / malformed /
 * unauthorized all need to read differently to a reviewer deciding whether
 * to retry).
 */
function describeError(error: unknown, context: "list" | "detail" | "review"): string {
  if (error instanceof AdminReviewTimeoutError) {
    return "요청이 시간 초과됐습니다. 네트워크 상태를 확인하고 다시 시도해주세요.";
  }
  if (error instanceof AdminReviewNetworkError) {
    return "서버에 연결할 수 없습니다. 네트워크 상태를 확인해주세요.";
  }
  if (error instanceof AdminReviewMalformedResponseError) {
    return "서버 응답을 해석할 수 없습니다. 잠시 후 다시 시도해주세요.";
  }
  if (error instanceof AdminReviewApiError) {
    if (error.status === 401 || error.status === 403) {
      return "이 작업에 대한 권한이 없습니다. 페이지를 새로고침해 다시 로그인해주세요.";
    }
    if (error.status === 404) {
      return context === "list"
        ? "검토 API를 사용할 수 없습니다(서버에 설정되지 않았을 수 있습니다)."
        : "이 후보를 찾을 수 없습니다(이미 처리됐을 수 있습니다).";
    }
    if (error.status === 409) {
      return "다른 곳에서 이미 처리됐습니다. 최신 상태를 다시 불러왔습니다.";
    }
    if (error.status >= 500) {
      return "서버에 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
    }
  }
  switch (context) {
    case "list":
      return "목록을 불러오지 못했습니다.";
    case "detail":
      return "상세 정보를 불러오지 못했습니다.";
    case "review":
      return "처리 중 문제가 발생했습니다.";
  }
}

function formatDateTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" });
}

function confidenceTone(confidence: number): string {
  if (confidence >= 0.8) return "text-mint";
  if (confidence >= 0.5) return "text-amber-700";
  return "text-rose";
}

const SOURCE_BADGE_COLORS: Record<string, string> = {
  oliveyoung: "border-oy-green/60 bg-oy-green-soft/70 text-oy-green",
  musinsa: "border-ms-black/30 bg-ms-soft text-ms-black",
  official: "border-official-gold/60 bg-official-soft text-official-gold",
};

function sourceKey(source: string): string | null {
  if (source === "oliveyoung" || source.startsWith("oliveyoung:")) return "oliveyoung";
  if (source === "musinsa" || source.startsWith("musinsa:")) return "musinsa";
  if (source === "official" || source.startsWith("official:")) return "official";
  return null;
}

function sourceLabel(offer: { source: string; source_label?: string | null }): string {
  return offer.source_label ?? offer.source;
}

function SourceBadge({ offer }: { offer: MatchOfferSummary }) {
  const key = sourceKey(offer.source);
  const colorClass = key ? SOURCE_BADGE_COLORS[key] : "border-blush/60 bg-blush-soft/70 text-rosewood";
  return (
    <span className={`inline-flex max-w-full items-center rounded-full border px-2 py-0.5 text-[11px] font-bold ${colorClass}`}>
      <span className="truncate">{sourceLabel(offer)}</span>
    </span>
  );
}

export default function AdminReviewPage() {
  const [items, setItems] = useState<PendingMatchSummary[]>([]);
  const [knownSources, setKnownSources] = useState<Set<string>>(new Set());
  const [nextAfterId, setNextAfterId] = useState<number | null>(null);
  const [sourceFilter, setSourceFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortMode, setSortMode] = useState<SortMode>("queue");
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null);
  const [detail, setDetail] = useState<MatchDetail | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [reviewer, setReviewer] = useState("");
  const [note, setNote] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [banner, setBanner] = useState<Banner | null>(null);

  // Belt-and-suspenders against a double-submit racing ahead of the
  // `isSubmitting` re-render that disables the buttons — a ref updates
  // synchronously, a state-driven `disabled` attribute doesn't kick in
  // until React commits the next render.
  const isSubmittingRef = useRef(false);

  useEffect(() => {
    const saved = window.sessionStorage.getItem(REVIEWER_STORAGE_KEY);
    if (saved) setReviewer(saved);
  }, []);

  const rememberSources = useCallback((newItems: PendingMatchSummary[]) => {
    if (newItems.length === 0) return;
    setKnownSources((current) => {
      const next = new Set(current);
      for (const item of newItems) next.add(item.offer.source);
      return next;
    });
  }, []);

  const loadList = useCallback(async () => {
    setIsLoadingList(true);
    setListError(null);
    try {
      const data = await fetchPendingMatches({ limit: PAGE_SIZE, source: sourceFilter.trim() || null });
      setItems(data.items);
      setNextAfterId(data.next_after_id ?? null);
      rememberSources(data.items);
    } catch (error) {
      setListError(describeError(error, "list"));
    } finally {
      setIsLoadingList(false);
    }
  }, [sourceFilter, rememberSources]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const loadMore = async () => {
    if (nextAfterId == null) return;
    setIsLoadingMore(true);
    try {
      const data = await fetchPendingMatches({
        limit: PAGE_SIZE,
        afterId: nextAfterId,
        source: sourceFilter.trim() || null,
      });
      setItems((current) => [...current, ...data.items]);
      setNextAfterId(data.next_after_id ?? null);
      rememberSources(data.items);
    } catch (error) {
      setListError(describeError(error, "list"));
    } finally {
      setIsLoadingMore(false);
    }
  };

  const loadDetail = useCallback(async (matchId: string) => {
    setSelectedMatchId(matchId);
    setDetail(null);
    setDetailError(null);
    setIsLoadingDetail(true);
    try {
      const data = await fetchMatchDetail(matchId);
      setDetail(data);
    } catch (error) {
      setDetailError(describeError(error, "detail"));
      if (error instanceof AdminReviewApiError && error.status === 404) {
        setItems((current) => current.filter((item) => item.match_id !== matchId));
      }
    } finally {
      setIsLoadingDetail(false);
    }
  }, []);

  const selectMatch = (matchId: string) => {
    setBanner(null);
    setNote("");
    void loadDetail(matchId);
  };

  const handleDecision = async (decision: MatchReviewDecision) => {
    if (!detail || !reviewer.trim() || isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setBanner(null);
    const reviewerName = reviewer.trim();
    window.sessionStorage.setItem(REVIEWER_STORAGE_KEY, reviewerName);
    try {
      await reviewMatch(detail.match_id, {
        decision,
        reviewer: reviewerName,
        note: note.trim() || null,
        expectedUpdatedAt: detail.updated_at,
      });
      setBanner({
        tone: "success",
        text: `${reviewerName}님이 ${decision === "verified" ? "검증" : "거부"} 처리했습니다.`,
      });
      setItems((current) => current.filter((item) => item.match_id !== detail.match_id));
      setSelectedMatchId(null);
      setDetail(null);
      setNote("");
      void loadList();
    } catch (error) {
      if (error instanceof AdminReviewApiError && error.status === 409) {
        setBanner({ tone: "conflict", text: describeError(error, "review") });
        void loadDetail(detail.match_id);
      } else if (error instanceof AdminReviewApiError && error.status === 404) {
        setBanner({ tone: "error", text: describeError(error, "review") });
        setItems((current) => current.filter((item) => item.match_id !== detail.match_id));
        setSelectedMatchId(null);
        setDetail(null);
      } else {
        setBanner({ tone: "error", text: describeError(error, "review") });
      }
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  };

  // "Skip" is deliberately NOT a decision sent to the API — there is no
  // "skipped" review_state in the backend (`MatchReviewState` is only
  // verified/pending_review/rejected/invalid), and inventing one client-side
  // would misrepresent this item as reviewed when it isn't (§8). This just
  // clears the selection so the reviewer can move on; the item stays exactly
  // as "pending_review" in the list and will be there next time.
  const skipCurrent = () => {
    setBanner(null);
    setSelectedMatchId(null);
    setDetail(null);
    setDetailError(null);
    setNote("");
  };

  const visibleItems = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    const filtered = query
      ? items.filter((item) => {
          const haystack = [
            item.canonical_product_id,
            item.offer.source,
            item.offer.source_label,
            item.target?.brand_ko,
            item.target?.brand_en,
            item.target?.product_name_ko,
            item.target?.product_name_display_ko,
          ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();
          return haystack.includes(query);
        })
      : items;

    if (sortMode === "queue") return filtered;
    const sorted = [...filtered].sort((a, b) =>
      sortMode === "confidence-asc" ? a.confidence - b.confidence : b.confidence - a.confidence,
    );
    return sorted;
  }, [items, searchQuery, sortMode]);

  const isAlreadyDecided = detail != null && detail.review_state !== "pending_review";

  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#fff7f6_0%,#fbfffb_46%,#ffffff_100%)] px-4 py-7 text-ink sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 pb-4">
        <h1 className="text-2xl font-extrabold text-rosewood">GlowSearch 관리자 검토</h1>
        <p className="text-sm text-neutral-500">
          아직 검증되지 않은 판매처 매치 후보를 확인하고 검증/거부를 결정합니다. 이 화면은 Basic Auth로
          보호됩니다. 이 목록에는 <strong className="font-bold text-neutral-700">검토 대기 중</strong>인 항목만
          표시됩니다 — 검증됨/거부됨 목록을 보는 기능은 아직 API가 지원하지 않습니다.
        </p>
      </div>

      <div className="mx-auto grid max-w-6xl gap-4 lg:grid-cols-[380px_1fr]">
        <section className="rounded-lg border border-line bg-white/90 p-4 shadow-soft">
          <div className="mb-2 flex items-center gap-2">
            <input
              type="text"
              value={sourceFilter}
              onChange={(event) => setSourceFilter(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void loadList();
              }}
              placeholder="판매처 필터 (정확히 일치, 예: musinsa)"
              className="min-w-0 flex-1 rounded-full border border-line px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose"
            />
            <button
              type="button"
              onClick={() => void loadList()}
              className="shrink-0 rounded-full border border-blush/70 bg-blush-soft px-3 py-1.5 text-xs font-bold text-rosewood transition hover:border-rose focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose"
            >
              새로고침
            </button>
          </div>

          {knownSources.size > 0 ? (
            <div className="mb-3 flex flex-wrap gap-1.5">
              {[...knownSources].sort().map((source) => (
                <button
                  key={source}
                  type="button"
                  onClick={() => setSourceFilter((current) => (current === source ? "" : source))}
                  className={[
                    "rounded-full border px-2 py-0.5 text-[11px] font-bold transition",
                    sourceFilter === source
                      ? "border-rosewood bg-blush-soft text-rosewood"
                      : "border-line text-neutral-500 hover:border-blush",
                  ].join(" ")}
                >
                  {source}
                </button>
              ))}
            </div>
          ) : null}

          <div className="mb-3 flex items-center gap-2">
            <div className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-neutral-400" aria-hidden="true" />
              <input
                type="text"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="불러온 목록에서 검색"
                aria-label="불러온 목록에서 검색"
                className="w-full rounded-full border border-line py-1.5 pl-8 pr-3 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose"
              />
            </div>
            <label className="sr-only" htmlFor="sort-mode">
              정렬
            </label>
            <select
              id="sort-mode"
              value={sortMode}
              onChange={(event) => setSortMode(event.target.value as SortMode)}
              className="shrink-0 rounded-full border border-line bg-white px-2 py-1.5 text-xs font-bold text-neutral-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose"
            >
              <option value="queue">대기열 순서</option>
              <option value="confidence-asc">신뢰도 낮은 순</option>
              <option value="confidence-desc">신뢰도 높은 순</option>
            </select>
          </div>

          {isLoadingList ? (
            <ListSkeleton />
          ) : listError ? (
            <div className="flex flex-col items-center gap-2 py-6 text-center text-sm text-rose">
              <AlertTriangle className="h-5 w-5" aria-hidden="true" />
              <p>{listError}</p>
              <button
                type="button"
                onClick={() => void loadList()}
                className="mt-1 inline-flex items-center gap-1 rounded-full border border-rose/60 px-3 py-1 text-xs font-bold text-rose transition hover:bg-red-50"
              >
                <RotateCcw className="h-3 w-3" aria-hidden="true" />
                다시 시도
              </button>
            </div>
          ) : items.length === 0 ? (
            <p className="py-6 text-center text-sm text-neutral-500">대기 중인 후보가 없습니다.</p>
          ) : visibleItems.length === 0 ? (
            <p className="py-6 text-center text-sm text-neutral-500">검색 결과가 없습니다.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {visibleItems.map((item) => (
                <li key={item.match_id}>
                  <button
                    type="button"
                    onClick={() => selectMatch(item.match_id)}
                    aria-current={selectedMatchId === item.match_id ? "true" : undefined}
                    className={[
                      "w-full rounded-lg border px-3 py-2 text-left text-sm transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose",
                      selectedMatchId === item.match_id
                        ? "border-rosewood bg-blush-soft"
                        : "border-line bg-white hover:border-blush",
                    ].join(" ")}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <SourceBadge offer={item.offer} />
                      <span className={`text-xs font-bold ${confidenceTone(item.confidence)}`}>
                        {(item.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="mt-1 truncate text-xs text-neutral-500">{item.canonical_product_id}</div>
                    {item.target?.product_name_display_ko || item.target?.product_name_ko ? (
                      <div className="mt-1 truncate text-xs text-neutral-700">
                        {item.target.product_name_display_ko ?? item.target.product_name_ko}
                      </div>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          )}

          {nextAfterId != null ? (
            <button
              type="button"
              onClick={() => void loadMore()}
              disabled={isLoadingMore}
              className="mt-3 w-full rounded-full border border-line py-2 text-xs font-bold text-neutral-600 transition hover:border-blush disabled:cursor-progress focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose"
            >
              {isLoadingMore ? "불러오는 중..." : "더 불러오기"}
            </button>
          ) : null}

          {items.length > 0 ? (
            <p className="mt-2 text-center text-[11px] text-neutral-400">
              {visibleItems.length === items.length ? `${items.length}개 불러옴` : `${visibleItems.length}/${items.length}개 표시 중`}
            </p>
          ) : null}
        </section>

        <section className="rounded-lg border border-line bg-white/90 p-4 shadow-soft">
          {banner ? (
            <div
              role="status"
              aria-live="polite"
              className={[
                "mb-4 flex items-start justify-between gap-3 rounded-lg px-4 py-3 text-sm",
                banner.tone === "success" && "bg-mint-soft text-mint",
                banner.tone === "conflict" && "bg-amber-50 text-amber-900",
                banner.tone === "error" && "bg-red-50 text-red-700",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              <span>{banner.text}</span>
              <button
                type="button"
                onClick={() => setBanner(null)}
                aria-label="알림 닫기"
                className="shrink-0 rounded-full p-0.5 opacity-70 transition hover:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          ) : null}

          {!selectedMatchId ? (
            <p className="py-10 text-center text-sm text-neutral-500">왼쪽에서 검토할 후보를 선택하세요.</p>
          ) : isLoadingDetail ? (
            <DetailSkeleton />
          ) : detailError ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center text-sm text-rose">
              <AlertTriangle className="h-5 w-5" aria-hidden="true" />
              <p>{detailError}</p>
              {selectedMatchId ? (
                <button
                  type="button"
                  onClick={() => void loadDetail(selectedMatchId)}
                  className="mt-1 inline-flex items-center gap-1 rounded-full border border-rose/60 px-3 py-1 text-xs font-bold text-rose transition hover:bg-red-50"
                >
                  <RotateCcw className="h-3 w-3" aria-hidden="true" />
                  다시 시도
                </button>
              ) : null}
            </div>
          ) : detail ? (
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line bg-white p-3">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                  <span className="font-bold text-neutral-700">
                    신뢰도 <span className={confidenceTone(detail.confidence)}>{(detail.confidence * 100).toFixed(0)}%</span>
                  </span>
                  <span className="text-neutral-500">매칭 방식: {detail.match_method}</span>
                  <span className="text-neutral-400">생성: {formatDateTime(detail.created_at)}</span>
                </div>
                {isAlreadyDecided ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-bold text-amber-900">
                    <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                    {REVIEW_STATE_LABELS[detail.review_state]}
                  </span>
                ) : null}
              </div>

              {isAlreadyDecided ? (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                  이 매치는 이미 <strong className="font-bold">{REVIEW_STATE_LABELS[detail.review_state]}</strong>{" "}
                  상태입니다{detail.reviewed_by ? ` (${detail.reviewed_by}` : ""}
                  {detail.reviewed_at ? `, ${formatDateTime(detail.reviewed_at)})` : detail.reviewed_by ? ")" : ""}.
                  더 이상 검증/거부할 필요가 없습니다.
                  <div className="mt-2">
                    <button
                      type="button"
                      onClick={skipCurrent}
                      className="rounded-full border border-amber-300 px-3 py-1 text-xs font-bold text-amber-900 transition hover:bg-amber-100"
                    >
                      목록으로 돌아가기
                    </button>
                  </div>
                </div>
              ) : null}

              <div className="grid gap-3 sm:grid-cols-2">
                <ComparisonCard title="후보 오퍼" offer={detail.offer} />
                <TargetComparisonCard target={detail.target} canonicalProductId={detail.canonical_product_id} />
              </div>

              {detail.evidence.length > 0 ? (
                <div className="rounded-lg border border-line bg-white p-3 text-sm">
                  <div className="mb-1 font-bold text-neutral-700">매칭 근거</div>
                  <ul className="flex flex-col gap-1">
                    {detail.evidence.map((item, index) => (
                      <li key={index} className="text-xs text-neutral-500">
                        {item.type}
                        {item.weight != null ? ` (weight ${item.weight})` : ""}
                        {item.value ? ` — ${item.value}` : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <div className="rounded-lg border border-line bg-white p-3 text-sm">
                <div className="mb-1 font-bold text-neutral-700">검토 이력</div>
                {detail.history.length === 0 ? (
                  <p className="text-xs text-neutral-500">아직 검토 이력이 없습니다.</p>
                ) : (
                  <ul className="flex flex-col gap-1">
                    {detail.history.map((event, index) => (
                      <li key={index} className="text-xs text-neutral-500">
                        {formatDateTime(event.created_at)} · {event.reviewer} · {event.previous_review_state} →{" "}
                        {event.new_review_state}
                        {event.note ? ` (${event.note})` : ""}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {!isAlreadyDecided ? (
                <div className="rounded-lg border border-line bg-white p-3">
                  <label className="mb-1 block text-xs font-bold text-neutral-700" htmlFor="reviewer-name">
                    검토자 이름 (필수)
                  </label>
                  <input
                    id="reviewer-name"
                    type="text"
                    value={reviewer}
                    onChange={(event) => setReviewer(event.target.value)}
                    disabled={isSubmitting}
                    className="mb-3 w-full rounded-lg border border-line px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose disabled:bg-neutral-50"
                    placeholder="이름을 입력하세요"
                  />
                  <label className="mb-1 block text-xs font-bold text-neutral-700" htmlFor="reviewer-note">
                    메모 (선택)
                  </label>
                  <textarea
                    id="reviewer-note"
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                    disabled={isSubmitting}
                    className="mb-3 w-full rounded-lg border border-line px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose disabled:bg-neutral-50"
                    rows={2}
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void handleDecision("verified")}
                      disabled={!reviewer.trim() || isSubmitting}
                      className="flex flex-1 items-center justify-center gap-1.5 rounded-full bg-mint px-4 py-2 text-sm font-bold text-white transition disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mint"
                    >
                      {isSubmitting ? (
                        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                      ) : (
                        <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                      )}
                      {isSubmitting ? "처리 중..." : "검증(verified)"}
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDecision("rejected")}
                      disabled={!reviewer.trim() || isSubmitting}
                      className="flex flex-1 items-center justify-center gap-1.5 rounded-full bg-rosewood px-4 py-2 text-sm font-bold text-white transition disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rosewood"
                    >
                      {isSubmitting ? (
                        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                      ) : (
                        <XCircle className="h-4 w-4" aria-hidden="true" />
                      )}
                      {isSubmitting ? "처리 중..." : "거부(rejected)"}
                    </button>
                    <button
                      type="button"
                      onClick={skipCurrent}
                      disabled={isSubmitting}
                      className="rounded-full border border-line px-4 py-2 text-sm font-bold text-neutral-600 transition hover:border-blush disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose"
                    >
                      나중에(건너뛰기)
                    </button>
                  </div>
                  {!reviewer.trim() ? (
                    <p className="mt-2 text-xs text-neutral-400">검토자 이름을 입력해야 처리할 수 있습니다.</p>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
}

function ListSkeleton() {
  return (
    <div className="flex flex-col gap-2" aria-hidden="true">
      {Array.from({ length: 5 }).map((_, index) => (
        <div key={index} className="animate-pulse rounded-lg border border-line bg-white px-3 py-2">
          <div className="mb-2 flex items-center justify-between">
            <div className="h-4 w-20 rounded-full bg-neutral-200" />
            <div className="h-3 w-10 rounded bg-neutral-200" />
          </div>
          <div className="mb-1.5 h-3 w-3/4 rounded bg-neutral-100" />
          <div className="h-3 w-1/2 rounded bg-neutral-100" />
        </div>
      ))}
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="flex flex-col gap-4" aria-hidden="true">
      <div className="animate-pulse h-12 rounded-lg border border-line bg-white" />
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="animate-pulse h-48 rounded-lg border border-line bg-white" />
        <div className="animate-pulse h-48 rounded-lg border border-line bg-white" />
      </div>
      <div className="animate-pulse h-20 rounded-lg border border-line bg-white" />
    </div>
  );
}

function ComparisonCard({ title, offer }: { title: string; offer: MatchOfferSummary }) {
  return (
    <article className="rounded-lg border border-line bg-white p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-xs font-bold uppercase tracking-wide text-neutral-500">{title}</span>
        <SourceBadge offer={offer} />
      </div>
      {offer.image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={offer.image_url} alt="" className="mb-2 h-32 w-full rounded-md object-cover" />
      ) : null}
      {offer.price != null ? <div className="text-sm text-neutral-700">{offer.price.toLocaleString("ko-KR")}원</div> : null}
      {offer.sold_out ? <div className="text-xs text-rose">품절</div> : null}
      <a
        href={offer.source_url}
        target="_blank"
        rel="noreferrer"
        className="mt-2 inline-flex items-center gap-1 text-xs font-bold text-rosewood hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose"
      >
        원본 링크 열기 <ExternalLink className="h-3 w-3" aria-hidden="true" />
      </a>
    </article>
  );
}

function TargetComparisonCard({
  target,
  canonicalProductId,
}: {
  target?: MatchTargetSummary | null;
  canonicalProductId: string;
}) {
  return (
    <article className="rounded-lg border border-line bg-white p-3">
      <div className="mb-2 text-xs font-bold uppercase tracking-wide text-neutral-500">대상 상품</div>
      {!target ? (
        <p className="text-xs text-neutral-500">인덱스에서 대응하는 상품 정보를 찾을 수 없습니다.</p>
      ) : (
        <>
          {target.image_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={target.image_url} alt="" className="mb-2 h-32 w-full rounded-md object-cover" />
          ) : null}
          <div className="text-sm font-bold text-ink">{target.brand_ko ?? target.brand_en}</div>
          <div className="text-sm text-neutral-700">
            {target.product_name_display_ko ?? target.product_name_ko}
          </div>
        </>
      )}
      <div className="mt-2 truncate text-xs text-neutral-400">{canonicalProductId}</div>
    </article>
  );
}
