"use client";

import { ExternalLink, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AdminReviewApiError, fetchMatchDetail, fetchPendingMatches, reviewMatch } from "@/lib/adminReviewApi";
import type {
  MatchDetail,
  MatchOfferSummary,
  MatchReviewDecision,
  MatchTargetSummary,
  PendingMatchSummary,
} from "@/types/review";

const PAGE_SIZE = 20;
const REVIEWER_STORAGE_KEY = "glowsearch_admin_reviewer_name";

type Banner = { tone: "success" | "conflict" | "error"; text: string };

export default function AdminReviewPage() {
  const [items, setItems] = useState<PendingMatchSummary[]>([]);
  const [nextAfterId, setNextAfterId] = useState<number | null>(null);
  const [sourceFilter, setSourceFilter] = useState("");
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

  useEffect(() => {
    const saved = window.sessionStorage.getItem(REVIEWER_STORAGE_KEY);
    if (saved) setReviewer(saved);
  }, []);

  const loadList = useCallback(async () => {
    setIsLoadingList(true);
    setListError(null);
    try {
      const data = await fetchPendingMatches({ limit: PAGE_SIZE, source: sourceFilter.trim() || null });
      setItems(data.items);
      setNextAfterId(data.next_after_id ?? null);
    } catch {
      setListError("목록을 불러오지 못했습니다.");
    } finally {
      setIsLoadingList(false);
    }
  }, [sourceFilter]);

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
    } catch {
      setListError("추가 목록을 불러오지 못했습니다.");
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
      setDetailError(
        error instanceof AdminReviewApiError && error.status === 404
          ? "이 후보를 찾을 수 없습니다(이미 처리됐을 수 있습니다)."
          : "상세 정보를 불러오지 못했습니다.",
      );
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
    if (!detail || !reviewer.trim() || isSubmitting) return;
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
        setBanner({ tone: "conflict", text: "다른 곳에서 이미 처리됐습니다. 최신 상태를 다시 불러왔습니다." });
        void loadDetail(detail.match_id);
      } else if (error instanceof AdminReviewApiError && error.status === 404) {
        setBanner({ tone: "error", text: "이 후보를 찾을 수 없습니다(이미 처리됐을 수 있습니다)." });
        setItems((current) => current.filter((item) => item.match_id !== detail.match_id));
        setSelectedMatchId(null);
        setDetail(null);
      } else {
        setBanner({ tone: "error", text: "처리 중 문제가 발생했습니다." });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#fff7f6_0%,#fbfffb_46%,#ffffff_100%)] px-4 py-7 text-ink sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 pb-4">
        <h1 className="text-2xl font-extrabold text-rosewood">GlowSearch 관리자 검토</h1>
        <p className="text-sm text-neutral-500">
          아직 검증되지 않은 판매처 매치 후보를 확인하고 검증/거부를 결정합니다. 이 화면은 Basic Auth로
          보호됩니다.
        </p>
      </div>

      <div className="mx-auto grid max-w-6xl gap-4 lg:grid-cols-[380px_1fr]">
        <section className="rounded-lg border border-line bg-white/90 p-4 shadow-soft">
          <div className="mb-3 flex items-center gap-2">
            <input
              type="text"
              value={sourceFilter}
              onChange={(event) => setSourceFilter(event.target.value)}
              placeholder="판매처 필터 (예: musinsa)"
              className="min-w-0 flex-1 rounded-full border border-line px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose"
            />
            <button
              type="button"
              onClick={() => void loadList()}
              className="shrink-0 rounded-full border border-blush/70 bg-blush-soft px-3 py-1.5 text-xs font-bold text-rosewood transition hover:border-rose"
            >
              새로고침
            </button>
          </div>

          {isLoadingList ? (
            <div className="flex items-center gap-2 py-6 text-sm text-neutral-500">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              불러오는 중
            </div>
          ) : listError ? (
            <p className="py-6 text-sm text-rose">{listError}</p>
          ) : items.length === 0 ? (
            <p className="py-6 text-center text-sm text-neutral-500">대기 중인 후보가 없습니다.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {items.map((item) => (
                <li key={item.match_id}>
                  <button
                    type="button"
                    onClick={() => selectMatch(item.match_id)}
                    className={[
                      "w-full rounded-lg border px-3 py-2 text-left text-sm transition",
                      selectedMatchId === item.match_id
                        ? "border-rosewood bg-blush-soft"
                        : "border-line bg-white hover:border-blush",
                    ].join(" ")}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-bold">{item.offer.source}</span>
                      <span className="text-xs text-neutral-500">confidence {item.confidence.toFixed(2)}</span>
                    </div>
                    <div className="truncate text-xs text-neutral-500">{item.canonical_product_id}</div>
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
              className="mt-3 w-full rounded-full border border-line py-2 text-xs font-bold text-neutral-600 transition hover:border-blush disabled:cursor-progress"
            >
              {isLoadingMore ? "불러오는 중..." : "더 불러오기"}
            </button>
          ) : null}
        </section>

        <section className="rounded-lg border border-line bg-white/90 p-4 shadow-soft">
          {banner ? (
            <div
              className={[
                "mb-4 rounded-lg px-4 py-3 text-sm",
                banner.tone === "success" && "bg-mint-soft text-mint",
                banner.tone === "conflict" && "bg-amber-50 text-amber-900",
                banner.tone === "error" && "bg-red-50 text-red-700",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              {banner.text}
            </div>
          ) : null}

          {!selectedMatchId ? (
            <p className="py-10 text-center text-sm text-neutral-500">왼쪽에서 검토할 후보를 선택하세요.</p>
          ) : isLoadingDetail ? (
            <div className="flex items-center gap-2 py-10 text-sm text-neutral-500">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              상세 정보를 불러오는 중
            </div>
          ) : detailError ? (
            <p className="py-10 text-center text-sm text-rose">{detailError}</p>
          ) : detail ? (
            <div className="flex flex-col gap-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <ComparisonCard title="후보 오퍼" offer={detail.offer} />
                <TargetComparisonCard target={detail.target} canonicalProductId={detail.canonical_product_id} />
              </div>

              <div className="rounded-lg border border-line bg-white p-3 text-sm">
                <div className="mb-1 font-bold text-neutral-700">매칭 방법 / 근거</div>
                <div className="text-neutral-500">{detail.match_method}</div>
                {detail.evidence.length > 0 ? (
                  <ul className="mt-2 flex flex-col gap-1">
                    {detail.evidence.map((item, index) => (
                      <li key={index} className="text-xs text-neutral-500">
                        {item.type}
                        {item.weight != null ? ` (weight ${item.weight})` : ""}
                        {item.value ? ` — ${item.value}` : ""}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>

              <div className="rounded-lg border border-line bg-white p-3 text-sm">
                <div className="mb-1 font-bold text-neutral-700">검토 이력</div>
                {detail.history.length === 0 ? (
                  <p className="text-xs text-neutral-500">아직 검토 이력이 없습니다.</p>
                ) : (
                  <ul className="flex flex-col gap-1">
                    {detail.history.map((event, index) => (
                      <li key={index} className="text-xs text-neutral-500">
                        {event.created_at} · {event.reviewer} · {event.previous_review_state} →{" "}
                        {event.new_review_state}
                        {event.note ? ` (${event.note})` : ""}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="rounded-lg border border-line bg-white p-3">
                <label className="mb-1 block text-xs font-bold text-neutral-700" htmlFor="reviewer-name">
                  검토자 이름 (필수)
                </label>
                <input
                  id="reviewer-name"
                  type="text"
                  value={reviewer}
                  onChange={(event) => setReviewer(event.target.value)}
                  className="mb-3 w-full rounded-lg border border-line px-3 py-2 text-sm"
                  placeholder="이름을 입력하세요"
                />
                <label className="mb-1 block text-xs font-bold text-neutral-700" htmlFor="reviewer-note">
                  메모 (선택)
                </label>
                <textarea
                  id="reviewer-note"
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  className="mb-3 w-full rounded-lg border border-line px-3 py-2 text-sm"
                  rows={2}
                />
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => void handleDecision("verified")}
                    disabled={!reviewer.trim() || isSubmitting}
                    className="flex-1 rounded-full bg-mint px-4 py-2 text-sm font-bold text-white transition disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {isSubmitting ? "처리 중..." : "검증(verified)"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDecision("rejected")}
                    disabled={!reviewer.trim() || isSubmitting}
                    className="flex-1 rounded-full bg-rosewood px-4 py-2 text-sm font-bold text-white transition disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {isSubmitting ? "처리 중..." : "거부(rejected)"}
                  </button>
                </div>
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
}

function ComparisonCard({ title, offer }: { title: string; offer: MatchOfferSummary }) {
  return (
    <article className="rounded-lg border border-line bg-white p-3">
      <div className="mb-2 text-xs font-bold uppercase tracking-wide text-neutral-500">{title}</div>
      {offer.image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={offer.image_url} alt="" className="mb-2 h-32 w-full rounded-md object-cover" />
      ) : null}
      <div className="text-sm font-bold text-ink">{offer.source_label ?? offer.source}</div>
      {offer.price != null ? <div className="text-sm text-neutral-700">{offer.price.toLocaleString("ko-KR")}원</div> : null}
      {offer.sold_out ? <div className="text-xs text-rose">품절</div> : null}
      <a
        href={offer.source_url}
        target="_blank"
        rel="noreferrer"
        className="mt-2 inline-flex items-center gap-1 text-xs font-bold text-rosewood hover:underline"
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
