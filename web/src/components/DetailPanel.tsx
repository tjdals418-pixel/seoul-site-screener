"use client";

import { useEffect, useState } from "react";
import {
  fetchArticle,
  fetchFeasibility,
  type Article,
  type FeasibilityAssumptions,
  type FeasibilityResponse,
} from "@/lib/api";
import { useArticles } from "@/lib/articles-context";
import { useBookmarks, BOOKMARK_TAGS } from "@/lib/bookmarks";
import { ChevronDown, Download, ExternalLink, Star } from "lucide-react";
import { capColor, siteTitle, type DevUse } from "@/lib/dev-class";
import { downloadArticleCSV } from "@/lib/export";
import { nearestLandmarks } from "@/lib/landmarks";

interface Props {
  selectedAid: string | null;
  onNavigate?: (aid: string | null) => void;
}

export default function DetailPanel({ selectedAid, onNavigate }: Props) {
  const [fetched, setFetched] = useState<{ aid: string; article: Article | null } | null>(null);
  const { has, toggle, getNote, saveNote } = useBookmarks();
  const { lookup, use, sim } = useArticles();

  // 1) Context lookup 우선 — 현재 목록(시뮬·용도 반영)에 있으면 그 값을 그대로 사용
  const cached = selectedAid ? lookup(selectedAid) : null;

  // 2) 목록에 없으면(deep link / 필터 밖 매물) API fetch
  useEffect(() => {
    if (!selectedAid || cached) return;
    let cancelled = false;
    fetchArticle(selectedAid, use)
      .then((a) => { if (!cancelled) setFetched({ aid: selectedAid, article: a }); })
      .catch(() => { if (!cancelled) setFetched({ aid: selectedAid, article: null }); });
    return () => { cancelled = true; };
  }, [selectedAid, cached, use]);

  const fetchedHere = fetched && fetched.aid === selectedAid ? fetched : null;
  const article = cached ?? fetchedHere?.article ?? null;
  const loading = !!selectedAid && !cached && !fetchedHere;

  if (!selectedAid) {
    return <Overview />;
  }

  if (loading || !article) {
    return (
      <div>
        <h2 className="text-xs font-semibold mb-3 uppercase tracking-wider text-muted">
          선택된 매물
        </h2>
        <p className="text-xs text-muted leading-relaxed">
          {loading
            ? "로드 중..."
            : "현재 용도·가정값 기준으로는 시뮬 대상이 아닌 매물이에요. 용도를 바꾸거나 가정값을 조정해 보세요."}
        </p>
      </div>
    );
  }

  const a = article;
  const grade = a.devClass || "—";
  const gradeColor = capColor(a.capRate);
  const isOffice = a.devUse === "office";
  const isGroup = !!a.isCombinedDevelopment;
  const isMember = !!a.partOfGroup && !isGroup;
  const bookmarked = has(a.articleNo);

  // 멤버 매물 — 단독 시뮬값은 의미 없음. 그룹으로 이동 안내.
  if (isMember && a.partOfGroup) {
    return (
      <MemberStub
        article={a}
        parentGid={a.partOfGroup}
        onNavigate={onNavigate}
      />
    );
  }

  return (
    <div>
      {/* 헤더 — 용도·등급 라벨 + 이름 + 북마크 */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted mb-1">
            <span className="w-2 h-2 rounded-full" style={{ background: gradeColor }} />
            {isOffice ? "오피스" : "호텔"} · {grade}
            {isGroup && <span className="text-accent">· 합필 {a.groupSize ?? "?"}필지</span>}
          </div>
          <h2 className="text-[17px] font-semibold leading-snug text-ink break-keep">
            {siteTitle(a)}
          </h2>
          <div className="text-[12px] text-muted mt-0.5">
            {a.divisionName ?? "—"} {a.sectorName ?? ""}
            {a.regRoadAddress && <span className="text-faint"> · {a.regRoadAddress}</span>}
          </div>
        </div>
        <button
          onClick={() => toggle(a.articleNo)}
          className={`flex-shrink-0 inline-flex items-center gap-1 h-8 px-2.5 rounded border text-[12px] transition-colors ${
            bookmarked
              ? "border-warn/40 bg-warn-soft text-warn"
              : "border-line text-muted hover:text-ink hover:border-line-strong"
          }`}
          aria-pressed={bookmarked}
          title={bookmarked ? "북마크 해제" : "북마크 추가"}
        >
          <Star size={14} fill={bookmarked ? "currentColor" : "none"} strokeWidth={1.75} />
          북마크
        </button>
      </div>

      {/* 상태 배지 */}
      {(a.isNew || (a.priceChangePct != null && Math.abs(a.priceChangePct) >= 0.5) ||
        (a.outlierFlags && a.outlierFlags.length > 0)) && (
        <div className="flex flex-wrap gap-1 mb-3">
          {a.isNew && (
            <span className="px-1.5 py-0.5 rounded text-[11px] font-semibold bg-good-soft text-good" title="이전 스냅샷 이후 새로 나온 매물">
              신규
            </span>
          )}
          {a.priceChangePct != null && Math.abs(a.priceChangePct) >= 0.5 && (
            <span
              className={`px-1.5 py-0.5 rounded text-[11px] font-semibold num ${
                a.priceChangePct > 0 ? "bg-bad-soft text-bad" : "bg-good-soft text-good"
              }`}
              title={`이전 호가 ${((a.prevDealPrice ?? 0) / 10000).toFixed(1)}억`}
            >
              호가 {a.priceChangePct > 0 ? "▲" : "▼"} {Math.abs(a.priceChangePct).toFixed(1)}%
            </span>
          )}
          {a.outlierFlags && a.outlierFlags.length > 0 && <OutlierBadge flags={a.outlierFlags} />}
        </div>
      )}

      {/* 핵심 지표 — Cap Rate */}
      {a.capRate !== null && a.capRate !== undefined && (
        <div className="border-y border-line py-3 mb-3">
          <div className="flex items-end justify-between gap-3">
            <div>
              <div
                className="text-[11px] text-muted"
                title="안정화 NOI ÷ 총사업비. 호텔 NOI = GOP − 운영사 수수료 − FF&E − 재산세, 오피스 NOI = 전용면적 × NOC × 12 − 임대면적 × 운용비 × 12"
              >
                취득 Cap <span className="text-faint">(NOI ÷ 총사업비)</span>
              </div>
              <div className="num text-[34px] leading-none font-medium text-ink mt-1">
                {(a.capRate * 100).toFixed(2)}
                <span className="text-[18px] text-muted ml-0.5">%</span>
              </div>
            </div>
            <div className="text-right text-[12px] text-muted leading-relaxed">
              {isOffice ? (
                <>{a.officeMarket ?? "—"} 권역<br />임대 {Math.round(a.officeLeasablePyeong ?? 0).toLocaleString()}평</>
              ) : (
                <>객실 <span className="num text-ink-2">{Math.round(a.devRoomCount ?? 0).toLocaleString()}</span>실<br />
                  ADR <span className="num text-ink-2">{a.adr10k ?? "—"}</span>만원</>
              )}
            </div>
          </div>
          <UseComparison article={a} />
        </div>
      )}

      {/* KPI 2x2 */}
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 mb-3">
        <Kpi label="매매가 (호가)" val={a.dealPrice ? `${(a.dealPrice / 10000).toFixed(1)}억` : "—"} />
        <Kpi label="총사업비" val={a.costTotalM ? `${Math.round(a.costTotalM / 100).toLocaleString()}억` : "—"} />
        <Kpi label="대지면적" val={a.landPyeong ? `${Math.round(a.landPyeong).toLocaleString()}평` : "—"} />
        <Kpi label="개발 연면적" val={a.devTotalPyeong ? `${Math.round(a.devTotalPyeong).toLocaleString()}평` : "—"} />
      </dl>

      {a.regZoning && (
        <div className="flex items-center gap-2 text-[12px] text-ink-2 mb-4">
          <ZoningSwatch zoning={a.regZoning} />
          <span>{a.regZoning}</span>
          <span className="text-faint">·</span>
          <span className="text-muted" title={a.inHistoricCore ? "한양도성 안 — 서울시 역사도심 조례 용적률 적용" : undefined}>
            용적률 <span className="num">{a.maxFar ?? "—"}%</span>
            {a.inHistoricCore && <span className="text-faint"> (역사도심)</span>}
          </span>
          <span className="text-faint">·</span>
          <span className="text-muted">토지 <span className="num">{a.landPerPyeongM ? Math.round(a.landPerPyeongM).toLocaleString() : "—"}</span>백만/평</span>
        </div>
      )}

      {/* 북마크 메모/태그 (북마크 됐을 때만) — KPI 아래, 보조 정보 위치 */}
      {bookmarked && (
        <BookmarkNoteEditor
          key={a.articleNo}
          aid={a.articleNo}
          current={getNote(a.articleNo)}
          onSave={(note, tag) => saveNote(a.articleNo, note, tag)}
        />
      )}

      {/* 비용 분해 */}
      {a.costTotalM && (
        <Expander title="총사업비 구성" defaultOpen={false}>
          {[
            ["토지비", a.costPurchaseM],
            ["공사비", a.costConstructionM],
            ["부대비", a.costIncidentalM],
            ["금융비", a.costFinanceM],
          ].map(([label, val]) => {
            const v = (val as number) ?? 0;
            const pct = a.costTotalM ? (v / a.costTotalM) * 100 : 0;
            return (
              <div key={label as string} className="flex justify-between py-0.5 text-[13px]">
                <span className="text-muted">{label}</span>
                <span className="text-ink-2">
                  <b>{v.toLocaleString(undefined, { maximumFractionDigits: 0 })}</b>
                  <span className="text-faint ml-1">({pct.toFixed(0)}%)</span>
                </span>
              </div>
            );
          })}
          <div
            className="flex justify-between mt-2 pt-2 font-semibold"
            style={{ borderTop: "1px solid var(--dash-border)" }}
          >
            <span>총사업비</span>
            <span>
              {Math.round(a.costTotalM).toLocaleString()} 백만
            </span>
          </div>
          <div className="text-[12.5px] text-muted mt-1.5">
            연면적 평당 {(a.costPerPyeongM ?? 0).toFixed(1)} 백만/평
            {!isOffice && a.costPerRoomM != null && (
              <> · 객실당 {a.costPerRoomM.toFixed(1)} 백만/실</>
            )}
          </div>
        </Expander>
      )}

      {/* 운영/수익 — 오피스 */}
      {isOffice && a.officeRevenueAnnualM != null && (
        <Expander title="임대 / 수익 (연간, 안정화)" defaultOpen={false}>
          <div className="text-[12.5px] text-ink-2 space-y-1">
            <Row label="권역 · NOC" val={`${a.officeMarket} · ${a.officeNoc10k}만원/전용평/월`} />
            <Row label="전용면적" val={`${Math.round(a.officeExclusivePyeong ?? 0).toLocaleString()}평`} />
            <Row label="임대면적 (= 연면적)" val={`${Math.round(a.officeLeasablePyeong ?? 0).toLocaleString()}평`} />
            {(a.officeVacancy ?? 0) > 0 && (
              <Row label="공실률" val={`${Math.round((a.officeVacancy ?? 0) * 100)}%`} />
            )}
          </div>
          <div className="mt-2 pt-2 border-t border-line text-[12.5px] space-y-1">
            <Row label="임대수입 (전용 × NOC × 12)" val={`${((a.officeRevenueAnnualM ?? 0) / 100).toFixed(1)}억`} />
            <Row label="운용비용 (임대면적 × 단가 × 12)" val={`−${((a.officeOpexAnnualM ?? 0) / 100).toFixed(1)}억`} />
            <Row
              label="NOI"
              val={`${((a.noiAnnualM ?? 0) / 100).toFixed(1)}억`}
              valClass="num text-good font-semibold"
            />
          </div>
        </Expander>
      )}

      {/* 운영/수익 — 호텔 */}
      {!isOffice && a.gopAnnualM && (
        <Expander title="운영 / 수익 (연간)" defaultOpen={false}>
          <div className="text-[13px] text-ink-2 space-y-0.5">
            <div>
              ADR: <b>{a.adr10k} 만원/박</b>
              {a.adrTier && (
                <span className="text-muted text-[12px] ml-1">
                  (Tier {a.adrTier} · {Math.round((a.adrMultiplier ?? 1) * 100)}% of{" "}
                  {a.adrBase10k}만)
                </span>
              )}
            </div>
            <div>Occupancy: <b>{Math.round((a.occupancy ?? 0) * 100)}%</b></div>
            <div>
              F&B 비율: {Math.round((a.fnbRatio ?? 0) * 100)}% · GOP 마진:{" "}
              {((a.gopRatio ?? 0) * 100).toFixed(1)}%
            </div>
          </div>
          <div
            className="mt-2 pt-2 text-[13.5px] space-y-0.5"
            style={{ borderTop: "1px solid var(--dash-border)" }}
          >
            <Row label="객실 매출/년" val={`${((a.roomRevenueAnnualM ?? 0) / 100).toFixed(1)} 억`} />
            <Row label="F&B 매출/년" val={`${((a.fnbRevenueAnnualM ?? 0) / 100).toFixed(1)} 억`} />
            <Row label="GOP / 년" val={`${((a.gopAnnualM ?? 0) / 100).toFixed(1)} 억`} />
            <Row
              label="NOI / 년"
              val={`${((a.noiAnnualM ?? 0) / 100).toFixed(1)} 억`}
              valClass="text-good font-semibold"
            />
            <div className="text-[11px] text-muted pt-1">
              NOI = GOP − 운영사 fee(매출 2% + GOP 8%) − FF&E(매출 3%) − 재산세·보험
            </div>
          </div>
        </Expander>
      )}

      {/* DCF — IRR / NPV / Payback */}
      {a.costTotalM && a.noiAnnualM && (
        <FeasibilitySection
          aid={a.articleNo}
          use={use}
          sim={sim as unknown as Record<string, unknown> | null}
          isOffice={isOffice}
        />
      )}

      {/* 통합그룹 멤버 list (그룹일 때만) */}
      {isGroup && (
        <GroupMembers article={a} onNavigate={onNavigate} />
      )}

      {/* 현재 건물 현황 — Disco의 "건물" 탭 같은 정보 */}
      <BuildingStatus article={a} />

      {/* 주요 랜드마크 거리 — 호텔 입지 평가 */}
      <Landmarks article={a} />

      {/* 도시계획 */}
      {(a.devJiguPrimaryName || a.devNearestRailStation) && (
        <Expander title="도시계획 / 미래 호재" defaultOpen={false}>
          {a.devJiguPrimaryName && (
            <div className="text-[13px] text-ink-2 mb-1">
              <b>지구단위계획</b>: {a.devJiguPrimaryName}
            </div>
          )}
          {a.devNearestRailStation && (
            <div className="text-[13px] text-ink-2">
              <b>{a.devNearestRailStation}</b> ({a.devNearestRailLine ?? ""}) ·{" "}
              {a.devNearestRailDistanceM ? `${Math.round(a.devNearestRailDistanceM)}m` : "—"} · 도보{" "}
              {a.devNearestRailWalkMin ? `${Math.round(a.devNearestRailWalkMin)}분` : "—"}
              {a.devNearestRailOpenDate && (
                <span className="text-muted ml-1">· 개통 {a.devNearestRailOpenDate}</span>
              )}
            </div>
          )}
        </Expander>
      )}

      {/* 외부 링크 + 내보내기 */}
      <div className="mt-4 pt-4 border-t border-line grid grid-cols-2 gap-2">
        {!isGroup && !a.articleNo.startsWith("GROUP-") && (
          <a
            href={`https://fin.land.naver.com/articles/${a.articleNo}`}
            target="_blank"
            rel="noopener noreferrer"
            className="col-span-2 inline-flex items-center justify-center gap-1.5 h-9 rounded bg-accent text-surface text-[13px] font-medium hover:bg-accent/90"
          >
            원본 매물 보기 (네이버부동산) <ExternalLink size={13} />
          </a>
        )}
        {a.latitude && a.longitude && (
          <a
            href={`https://map.kakao.com/link/map/${encodeURIComponent(
              siteTitle(a) || a.regRoadAddress || `매물 ${a.articleNo}`
            )},${a.latitude},${a.longitude}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center gap-1.5 h-9 rounded border border-line text-[13px] text-ink-2 hover:border-line-strong"
          >
            카카오맵 <ExternalLink size={13} />
          </a>
        )}
        {a.regRoadAddress && <DiscoButton address={a.regRoadAddress} />}
        <button
          onClick={() => downloadArticleCSV(a)}
          className="inline-flex items-center justify-center gap-1.5 h-9 rounded border border-line text-[13px] text-ink-2 hover:border-line-strong"
          title="이 부지의 시뮬 결과를 Excel에서 열 수 있는 CSV로 저장"
        >
          <Download size={13} /> CSV
        </button>
      </div>
    </div>
  );
}

/**
 * Disco는 query string deep link를 지원 안 함 (URL 보내도 마지막 본 위치 그대로).
 * 대안: 주소를 clipboard에 자동 복사 + Disco 메인 새 탭. Disco 검색창에 paste만.
 */
function DiscoButton({ address }: { address: string }) {
  const [copied, setCopied] = useState(false);
  const handleClick = async () => {
    try {
      await navigator.clipboard.writeText(address);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard 권한 없으면 그냥 열기만 */
    }
    window.open("https://www.disco.re/", "_blank", "noopener,noreferrer");
  };
  return (
    <button
      onClick={handleClick}
      className="inline-flex items-center justify-center gap-1.5 h-9 rounded border border-line text-[13px] text-ink-2 hover:border-line-strong"
      title="주소를 복사하고 디스코를 엽니다 — 검색창에 붙여넣기"
    >
      {copied ? "주소 복사됨" : <>디스코 <ExternalLink size={13} /></>}
    </button>
  );
}

/** 북마크 메모 + 태그. 변경 즉시 localStorage 저장 (debounce 400ms). */
function BookmarkNoteEditor({
  aid,
  current,
  onSave,
}: {
  aid: string;
  current: { note: string; tag: string } | null;
  onSave: (note: string, tag: string) => void;
}) {
  // 매물이 바뀌면 부모가 key={aid}로 새로 마운트하므로 초기값만 받으면 됨
  const [note, setNote] = useState(current?.note ?? "");
  const [tag, setTag] = useState(current?.tag ?? "");

  useEffect(() => {
    if (note === (current?.note ?? "") && tag === (current?.tag ?? "")) return;
    const t = setTimeout(() => onSave(note, tag), 400);
    return () => clearTimeout(t);
  }, [note, tag, aid, current, onSave]);

  return (
    <div
      className="mb-4 p-2.5 rounded space-y-1.5 bg-warn-soft/60 border border-warn/20"
    >
      <div className="flex gap-1 flex-wrap">
        {BOOKMARK_TAGS.map((t) => {
          const active = tag === t;
          return (
            <button
              key={t}
              onClick={() => setTag(active ? "" : t)}
              className="text-[11px] px-1.5 py-0.5 rounded transition"
              style={{
                background: active ? "var(--dash-grad-primary)" : "var(--color-sunken)",
                color: active ? "var(--color-surface)" : "var(--color-muted)",
                border: active ? "none" : "1px solid var(--dash-border)",
              }}
            >
              {t}
            </button>
          );
        })}
      </div>
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="메모 (자동 저장)"
        className="w-full px-2 py-1 rounded text-[12.5px] text-ink-2 outline-none resize-none"
        style={{
          background: "var(--color-sunken)",
          border: "1px solid var(--dash-border)",
          minHeight: "36px",
        }}
        rows={2}
      />
    </div>
  );
}

/**
 * DCF 사업성 — 공사 기간 + 운영 ramp-up(호텔) / lease-up(오피스) + Exit 매각
 * cash flow로 IRR/NPV/Payback. 사이드바에서 적용한 시뮬 가정값(sim)과 용도(use)
 * 기준으로 재계산된 매물에 대해 계산한다.
 *
 * 가정값 (Exit cap, hold, LTV, 할인율)은 inline로 조정 가능.
 */
function FeasibilitySection({
  aid,
  use,
  sim,
  isOffice,
}: {
  aid: string;
  use: DevUse;
  sim: Record<string, unknown> | null;
  isOffice: boolean;
}) {
  const [assumptions, setAssumptions] = useState<FeasibilityAssumptions>({});
  const [result, setResult] = useState<FeasibilityResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  // 가정값 슬라이더/입력 변경 시 매 keystroke fetch 폭주 방지 — 300ms debounce.
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      setLoading(true);
      setErrorMsg(null);
      fetchFeasibility(aid, assumptions, use, sim)
        .then((r) => {
          setResult(r);
          setErrorMsg(null);
        })
        .catch((e: Error) => {
          setResult(null);
          setErrorMsg(e.message);
        })
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(t);
  }, [aid, assumptions, open, use, sim]);

  // 표시 헬퍼
  const fmtPct = (v: number | null) =>
    v == null ? "—" : `${(v * 100).toFixed(2)}%`;
  const fmtYear = (v: number | null) =>
    v == null ? "회수 불가" : `${v.toFixed(1)}년`;
  const fmtBn = (m: number | null) =>
    m == null ? "—" : `${(m / 100).toFixed(1)}억`;
  const fmtCap = (v: number | null) =>
    v == null ? "—" : `${(v * 100).toFixed(2)}%`;

  return (
    <div className="border-t border-line">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="w-full flex items-center justify-between h-10 text-[13px] font-medium text-ink hover:text-accent"
      >
        <span>사업성 DCF <span className="text-muted font-normal">IRR · NPV · 회수기간</span></span>
        <ChevronDown size={15} className={`text-muted transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="pb-3">
          <div className="text-[11px] text-muted mb-2 leading-relaxed">
            기본 {assumptions.hold_years ?? 5}년 보유 (공사{" "}
            {result?.construction_years_used ?? assumptions.construction_years ?? 2}년 +{" "}
            {isOffice ? "임대 안정화" : "운영 안정화"}{" "}
            {(assumptions.hold_years ?? 5) - (result?.construction_years_used ?? assumptions.construction_years ?? 2)}년)
            → Exit 매각.{" "}
            {isOffice
              ? "임대율 60% → 90% → 100% lease-up."
              : "운영 70% → 85% → 100% ramp-up."}
            {result?.noi_to_gop != null && (
              <span className="text-muted"> (NOI/GOP {(result.noi_to_gop * 100).toFixed(0)}%)</span>
            )}
          </div>

          {loading && (
            <div className="text-[12px] text-muted">계산 중...</div>
          )}

          {errorMsg && !loading && (
            <div
              className="text-[12px] text-warn px-2 py-2 rounded leading-relaxed"
              style={{ background: "var(--color-warn-soft)", border: "1px solid var(--color-warn-soft)" }}
            >
              {errorMsg}
            </div>
          )}

          {result && !loading && (
            <>
              {/* 핵심 4개 지표 */}
              <div className="grid grid-cols-2 gap-1.5 mb-2">
                <DCFKpi
                  label="IRR (Levered)"
                  val={fmtPct(result.irr_levered)}
                  good={(result.irr_levered ?? 0) >= 0.12}
                  bad={(result.irr_levered ?? 0) < 0.06}
                  tip="자기자본 기준 내부수익률. 12% 이상이면 녹색으로 표시해요"
                />
                <DCFKpi
                  label="IRR (Unlevered)"
                  val={fmtPct(result.irr_unlevered)}
                  good={(result.irr_unlevered ?? 0) >= 0.08}
                  bad={(result.irr_unlevered ?? 0) < 0.04}
                  tip="전체 사업 IRR. 부채구조 제외, project 자체 수익성"
                />
                <DCFKpi
                  label="NPV @8% / @12%"
                  val={`${fmtBn(result.npv_M)} / ${fmtBn(result.npv_dev_M)}`}
                  good={(result.npv_M ?? 0) >= 0}
                  bad={(result.npv_dev_M ?? 0) < 0}
                  tip="좌: 코어 할인율 8% · 우: 개발 risk 12%. 둘 다 양수여야 안전"
                />
                <DCFKpi
                  label="Payback"
                  val={fmtYear(result.payback_year)}
                  good={
                    result.payback_year != null && result.payback_year <= 8
                  }
                  bad={
                    result.payback_year == null || result.payback_year > 12
                  }
                  tip="누적 cash flow가 양으로 전환되는 시점"
                />
              </div>

              {/* YoC + Exit value */}
              <div className="flex justify-between gap-2 text-[12px] text-muted mb-1">
                <div>
                  <span className="text-muted">YoC(안정화):</span>{" "}
                  <b className="text-ink-2">{fmtPct(result.yoc_year3)}</b>
                </div>
                <div>
                  <span className="text-muted">Exit Value:</span>{" "}
                  <b className="text-ink-2">{fmtBn(result.exit_value_M)}</b>
                </div>
              </div>

              {/* Entry → Exit cap compression/expansion */}
              <div className="flex items-center gap-1.5 text-[12px] text-muted mb-2">
                <span className="text-muted">Cap:</span>
                <b className="text-ink-2">{fmtCap(result.entry_cap)}</b>
                <span className="text-faint">→</span>
                <b className="text-ink-2">{fmtCap(result.exit_cap_used)}</b>
                {result.entry_cap != null && result.exit_cap_used != null && (
                  <span
                    className="text-[10.5px] px-1 rounded"
                    style={{
                      background:
                        result.exit_cap_used > result.entry_cap
                          ? "var(--color-bad-soft)"
                          : "var(--color-good-soft)",
                      color:
                        result.exit_cap_used > result.entry_cap ? "var(--color-bad)" : "var(--color-good)",
                    }}
                    title="Exit cap > Entry cap이면 매각 시 가치 하락(expansion), 반대면 compression"
                  >
                    {result.exit_cap_used > result.entry_cap ? "expansion" : "compression"}
                  </span>
                )}
              </div>

              {/* 가정값 조정 */}
              <details className="mt-2">
                <summary className="cursor-pointer text-[12px] text-muted hover:text-ink">
                  DCF 가정값 조정
                </summary>
                <div className="mt-1.5 space-y-1 px-1">
                  <AssumeNum
                    label="공사 기간"
                    value={assumptions.construction_years ?? result?.construction_years_used ?? 2}
                    min={1}
                    max={5}
                    step={1}
                    decimals={0}
                    suffix="년"
                    onChange={(v) =>
                      setAssumptions((p) => ({ ...p, construction_years: v }))
                    }
                  />
                  <AssumeNum
                    label="보유 기간 (공사+운영)"
                    value={assumptions.hold_years ?? 5}
                    min={3}
                    max={20}
                    step={1}
                    decimals={0}
                    suffix="년"
                    onChange={(v) =>
                      setAssumptions((p) => ({ ...p, hold_years: v }))
                    }
                  />
                  <AssumeNum
                    label="LTV"
                    value={assumptions.ltv ?? 0.60}
                    min={0}
                    max={0.85}
                    step={0.05}
                    decimals={2}
                    suffix="%"
                    suffixMultiplier={100}
                    onChange={(v) => setAssumptions((p) => ({ ...p, ltv: v }))}
                  />
                  <AssumeNum
                    label="대출 금리"
                    value={assumptions.loan_rate ?? 0.055}
                    min={0.03}
                    max={0.10}
                    step={0.0025}
                    decimals={3}
                    suffix="%"
                    suffixMultiplier={100}
                    onChange={(v) =>
                      setAssumptions((p) => ({ ...p, loan_rate: v }))
                    }
                  />
                  <AssumeNum
                    label={isOffice ? "Exit Cap (권역별 자동)" : "Exit Cap (자치구 Tier 자동)"}
                    value={assumptions.exit_cap ?? result?.exit_cap_used ?? 0.06}
                    min={0.03}
                    max={0.10}
                    step={0.0025}
                    decimals={3}
                    suffix="%"
                    suffixMultiplier={100}
                    onChange={(v) =>
                      setAssumptions((p) => ({ ...p, exit_cap: v }))
                    }
                  />
                  <AssumeNum
                    label="할인율 (Equity 요구)"
                    value={assumptions.discount_rate ?? 0.08}
                    min={0.05}
                    max={0.15}
                    step={0.005}
                    decimals={3}
                    suffix="%"
                    suffixMultiplier={100}
                    onChange={(v) =>
                      setAssumptions((p) => ({ ...p, discount_rate: v }))
                    }
                  />
                  <AssumeNum
                    label="Vehicle 운용비 (영업외)"
                    value={assumptions.vehicle_cost_rate ?? 0.006}
                    min={0}
                    max={0.02}
                    step={0.0005}
                    decimals={0}
                    suffix="bp"
                    suffixMultiplier={10000}
                    onChange={(v) =>
                      setAssumptions((p) => ({ ...p, vehicle_cost_rate: v }))
                    }
                  />
                </div>
              </details>

              {/* 노트 */}
              {result.notes.length > 0 && (
                <div className="mt-2 text-[11px] text-muted space-y-0.5">
                  {result.notes.map((n, i) => (
                    <div key={i}>{n}</div>
                  ))}
                </div>
              )}

              {/* cash flow chart (간단 bar) */}
              <div className="mt-2 pt-2" style={{ borderTop: "1px solid var(--dash-border)" }}>
                <div className="text-[11px] text-muted mb-1">
                  연도별 unlevered cash flow (백만원)
                </div>
                <CashFlowBars flows={result.cash_flows_M} />
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function DCFKpi({
  label,
  val,
  good,
  bad,
  tip,
}: {
  label: string;
  val: string;
  good?: boolean;
  bad?: boolean;
  tip?: string;
}) {
  const tone = bad ? "text-bad" : good ? "text-good" : "text-ink";
  return (
    <div className="min-w-0" title={tip}>
      <div className="text-[11px] text-muted">{label}</div>
      <div className={`num text-[15px] mt-0.5 ${tone}`}>{val}</div>
    </div>
  );
}

function AssumeNum({
  label,
  value,
  min,
  max,
  step,
  decimals,
  suffix = "",
  suffixMultiplier = 1,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  decimals: number;
  suffix?: string;
  suffixMultiplier?: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center justify-between text-[12px]">
      <span className="text-muted truncate mr-2">{label}</span>
      <div className="flex items-center gap-1">
        <input
          type="number"
          value={(value * suffixMultiplier).toFixed(decimals)}
          min={min * suffixMultiplier}
          max={max * suffixMultiplier}
          step={step * suffixMultiplier}
          onChange={(e) => {
            const raw = Number(e.target.value);
            if (!Number.isFinite(raw)) return;
            const v = raw / suffixMultiplier;
            onChange(Math.min(max, Math.max(min, v)));
          }}
          className="w-16 text-right bg-transparent border rounded px-1 py-0.5 text-ink-2 text-[12px]"
          style={{ borderColor: "var(--dash-border)" }}
        />
        {suffix && <span className="text-muted w-2 text-[11px]">{suffix}</span>}
      </div>
    </div>
  );
}

function CashFlowBars({ flows }: { flows: number[] }) {
  const max = Math.max(...flows.map(Math.abs), 1);
  return (
    <div className="flex items-end gap-0.5 h-10">
      {flows.map((cf, i) => {
        const h = (Math.abs(cf) / max) * 100;
        const isNeg = cf < 0;
        return (
          <div
            key={i}
            className="flex-1 flex flex-col items-center justify-end relative group"
            title={`Year ${i}: ${cf >= 0 ? "+" : ""}${cf.toFixed(0)} 백만`}
          >
            <div
              className="w-full rounded-sm"
              style={{
                height: `${h}%`,
                background: isNeg ? "#ef4444" : "var(--color-good)",
                opacity: 0.85,
              }}
            />
            <div className="text-[10px] text-faint mt-0.5">{i}</div>
          </div>
        );
      })}
    </div>
  );
}

/** 매물 좌표 → 가까운 랜드마크 5개. */
function Landmarks({ article }: { article: Article }) {
  if (!article.latitude || !article.longitude) return null;
  const list = nearestLandmarks(article.latitude, article.longitude, 5);
  return (
    <Expander title="주요 랜드마크 거리" defaultOpen={false}>
      <div className="text-[13px] space-y-0.5">
        {list.map((lm) => {
          const km = lm.distanceM / 1000;
          const distLabel = km >= 1 ? `${km.toFixed(1)}km` : `${Math.round(lm.distanceM)}m`;
          // 도보 30분 이상은 도보 시간 의미 X
          const walkable = lm.walkMin <= 30;
          return (
            <div key={lm.name} className="flex justify-between py-0.5 gap-2">
              <span className="text-muted">
                {lm.name}
              </span>
              <span className="text-ink-2 text-right">
                <b>{distLabel}</b>
                {walkable && (
                  <span className="text-muted text-[11px] ml-1">
                    · 도보 {lm.walkMin}분
                  </span>
                )}
              </span>
            </div>
          );
        })}
      </div>
    </Expander>
  );
}

const OUTLIER_LABELS: Record<string, { text: string; tip: string }> = {
  price_low: { text: "평당가 하위 5% · 면적·호가 확인", tip: "토지 평당가가 하위 5% — 대지면적이나 호가 입력 오류일 수 있어요" },
  cap_high: { text: "취득 Cap 10% 초과 · 데이터 확인", tip: "서울 신축 기준으로 드문 수준이에요. 호가·대지면적·용도지역을 원본에서 확인해 보세요" },
  zone_unfit: { text: "신축 불가 용도지역", tip: "일반주거·전용주거 등 호텔·대형 오피스 신축이 어려운 용도지역이라 참고용이에요" },
};

/** 선택 전 — 현재 조건의 후보 요약과 읽는 법. */
function Overview() {
  const { candidates: cands, use } = useArticles();
  const caps = cands.map((a) => a.capRate).filter((c): c is number => c != null).sort((x, y) => x - y);
  const median = caps.length ? caps[Math.floor((caps.length - 1) / 2)] : null;
  const byUse = {
    hotel: cands.filter((a) => a.devUse === "hotel").length,
    office: cands.filter((a) => a.devUse === "office").length,
  };
  const gu = new Map<string, number>();
  for (const a of cands) {
    if ((a.capRate ?? 0) >= 0.05 && a.divisionName) gu.set(a.divisionName, (gu.get(a.divisionName) ?? 0) + 1);
  }
  const topGu = [...gu.entries()].sort((x, y) => y[1] - x[1]).slice(0, 3);

  return (
    <div className="space-y-5">
      <div>
        <div className="text-[11px] text-muted mb-1">현재 조건</div>
        <h2 className="text-[17px] font-semibold leading-snug">
          개발 후보 <span className="num">{cands.length}</span>곳
        </h2>
        {use === "best" && (
          <p className="text-[12px] text-muted mt-0.5">
            호텔이 유리한 곳 <span className="num text-ink-2">{byUse.hotel}</span> · 오피스가 유리한 곳{" "}
            <span className="num text-ink-2">{byUse.office}</span>
          </p>
        )}
      </div>

      <dl className="grid grid-cols-3 border-y border-line divide-x divide-line">
        {[
          ["6% 이상", caps.filter((c) => c >= 0.06).length, "곳"],
          ["5% 이상", caps.filter((c) => c >= 0.05).length, "곳"],
          ["중앙값", median != null ? (median * 100).toFixed(2) : "—", "%"],
        ].map(([label, v, unit]) => (
          <div key={String(label)} className="py-3 px-2 first:pl-0">
            <dt className="text-[11px] text-muted">취득 Cap {label}</dt>
            <dd className="num text-[20px] text-ink mt-0.5">
              {v}
              <span className="text-[12px] text-muted ml-0.5">{unit}</span>
            </dd>
          </div>
        ))}
      </dl>

      {topGu.length > 0 && (
        <div>
          <div className="text-[11px] text-muted mb-1.5">5% 이상 부지가 많은 구</div>
          <ol className="space-y-1">
            {topGu.map(([name, n]) => (
              <li key={name} className="flex justify-between text-[13px]">
                <span>{name}</span>
                <span className="num text-muted">{n}곳</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      <div className="text-[12.5px] leading-relaxed text-ink-2 bg-sunken border border-line rounded p-3 space-y-1.5">
        <p className="font-medium text-ink">이렇게 보세요</p>
        <p>왼쪽 순위나 지도에서 부지를 누르면 개발 규모, 총사업비, NOI, IRR이 여기에 나와요.</p>
        <p>
          <b>취득 Cap</b>은 지금 호가로 사서 새로 지었을 때의 NOI ÷ 총사업비예요. 지도 점 색이 진할수록
          높아요.
        </p>
      </div>
    </div>
  );
}

/** 같은 부지의 호텔 vs 오피스 Cap Rate 비교 (둘 다 계산된 경우만). */
function UseComparison({ article }: { article: Article }) {
  const h = article.hotelCapRate;
  const o = article.officeCapRate;
  if (h == null || o == null) return null;
  const hotelWins = h >= o;
  const cell = (label: string, v: number, win: boolean) => (
    <span className={win ? "text-good font-semibold" : "text-muted"}>
      {label} {(v * 100).toFixed(2)}%
    </span>
  );
  return (
    <div
      className="mt-1.5 pt-1.5 text-[12px] flex items-center gap-2"
      style={{ borderTop: "1px dashed var(--dash-border)" }}
      title="같은 부지를 호텔/오피스로 개발했을 때의 취득 Cap"
    >
      <span className="text-muted">용도 비교</span>
      {cell("", h, hotelWins)}
      <span className="text-faint">vs</span>
      {cell("", o, !hotelWins)}
      {article.devZoneOk === false && (
        <span className="text-[10.5px] text-bad">· 신축 불가 지역</span>
      )}
    </div>
  );
}

function OutlierBadge({ flags }: { flags: string[] }) {
  return (
    <>
      {flags.map((f) => {
        const def = OUTLIER_LABELS[f];
        if (!def) return null;
        // 카테고리별 색
        let bg = "var(--color-warn-soft)";    // amber default (warning)
        let color = "var(--color-warn)";
        if (f === "zone_unfit") {            // 빨강 (강한 경고)
          bg = "var(--color-bad-soft)";
          color = "var(--color-bad)";
        }
        return (
          <span
            key={f}
            className="px-2 py-0.5 rounded text-[11px] font-semibold whitespace-nowrap"
            style={{ background: bg, color }}
            title={def.tip}
          >
            {def.text}
          </span>
        );
      })}
    </>
  );
}

/**
 * 통합그룹의 멤버 list — 각 row 클릭 시 멤버 매물로 jump.
 * 또 네이버부동산 직접 link.
 */
function GroupMembers({
  article,
  onNavigate,
}: {
  article: Article;
  onNavigate?: (aid: string | null) => void;
}) {
  const members = (article.groupMembersDetail ?? []) as Array<{
    articleNo?: string;
    landSpace?: number;
    landPyeong?: number;
    dealPrice?: number;
    regRoadAddress?: string;
  }>;
  if (members.length === 0) return null;

  return (
    <Expander title={`통합 멤버 ${members.length}필지`} defaultOpen={true}>
      <div className="text-[12px] text-muted mb-2 leading-relaxed">
        합필은 가상 부지라 원본 매물 링크가 없어요. 필지별 링크로 확인하세요.
        멤버 ↗/로 개별 매물 확인.
      </div>
      <div className="space-y-1">
        {members.map((m, idx) => {
          const aid = String(m.articleNo ?? "");
          const land = m.landPyeong
            ? `${Math.round(m.landPyeong)}평`
            : m.landSpace ? `${Math.round(m.landSpace)}㎡` : "—";
          const price = m.dealPrice ? `${(m.dealPrice / 10000).toFixed(0)}억` : "—";
          return (
            <div
              key={aid || idx}
              className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-ink/[0.04] transition text-[12.5px]"
              style={{ background: "var(--color-sunken)" }}
            >
              <span className="text-faint w-4 text-center flex-shrink-0">
                {idx + 1}
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-ink-2 truncate">
                  {m.regRoadAddress || `매물 ${aid}`}
                </div>
                <div className="text-[11px] text-muted">
                  {land} · {price}
                </div>
              </div>
              {aid && (
                <>
                  <button
                    onClick={() => onNavigate?.(aid)}
                    className="text-[12px] text-accent hover:text-accent transition flex-shrink-0"
                    title="이 멤버 매물로 이동"
                  >
                    ↗
                  </button>
                  <a
                    href={`https://fin.land.naver.com/articles/${aid}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[12px] text-muted hover:text-ink transition flex-shrink-0"
                    title="원본 매물 (네이버부동산)"
                    aria-label="원본 매물 (네이버부동산)"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <ExternalLink size={13} />
                                      </a>
                </>
              )}
            </div>
          );
        })}
      </div>
    </Expander>
  );
}

/** YYYYMMDD → "1969년 8월 13일" */
function formatApprovalDate(raw: number | string | null | undefined): string | null {
  if (!raw) return null;
  const s = String(raw);
  if (s.length !== 8) return null;
  const y = s.slice(0, 4);
  const m = parseInt(s.slice(4, 6), 10);
  const d = parseInt(s.slice(6, 8), 10);
  if (!y || !m || !d) return null;
  return `${y}년 ${m}월 ${d}일`;
}

/**
 * 현재 건물 현황 — 시뮬값(개발 후)이 아니라 raw 건축물대장 기반.
 * Disco의 "건물" 탭과 유사.
 */
function BuildingStatus({ article }: { article: Article }) {
  const a = article;

  // 표시할 값 모음 (값 있을 때만)
  const rows: Array<[string, string | null]> = [];
  const approval = formatApprovalDate(a.regUseApprovalDate ?? a.approvalDateRaw);
  if (approval) {
    rows.push([
      "준공일",
      a.approvalElapsedYear
        ? `${approval} (${a.approvalElapsedYear}년 경과)`
        : approval,
    ]);
  }
  if (a.regBuildingUse) rows.push(["주용도", a.regBuildingUse]);
  if (a.regStructure) rows.push(["구조", a.regStructure]);

  // 층
  if (a.floorInfo || a.groundTotalFloor) {
    const above = a.groundTotalFloor;
    const below = a.undergroundTotalFloor ? Math.abs(a.undergroundTotalFloor) : 0;
    const fmt = below
      ? `지하 ${below}층 / 지상 ${above ?? "?"}층`
      : `지상 ${above ?? "?"}층`;
    rows.push(["층수", fmt]);
  }

  // 토지 / 연면적
  if (a.landPyeong) {
    rows.push([
      "토지면적",
      `${Math.round(a.landPyeong).toLocaleString()} 평 (${Math.round(a.landSpace ?? 0).toLocaleString()}㎡)`,
    ]);
  }
  if (a.totalPyeong) {
    rows.push([
      "연면적 (현재)",
      `${Math.round(a.totalPyeong).toLocaleString()} 평 (${Math.round(a.floorSpace ?? 0).toLocaleString()}㎡)`,
    ]);
  }

  // 용도지역 / 용적률
  if (a.regZoning) {
    const max = a.maxFar ? ` (최대 ${a.maxFar}%)` : "";
    rows.push(["용도지역", `${a.regZoning}${max}`]);
  }
  if (a.regFloorAreaRatio) {
    rows.push(["현재 용적률", `${a.regFloorAreaRatio}%`]);
  }
  if (a.regBuildingCoverageRatio) {
    rows.push(["건폐율", `${a.regBuildingCoverageRatio}%`]);
  }

  // 설비
  if (a.regTotalParkingCount != null && a.regTotalParkingCount > 0) {
    rows.push(["주차", `${a.regTotalParkingCount}대`]);
  }
  if (a.regElevatorCount != null && a.regElevatorCount > 0) {
    rows.push(["엘리베이터", `${a.regElevatorCount}대`]);
  }
  if (a.regHouseholdNumber != null && a.regHouseholdNumber > 0) {
    rows.push(["세대수", `${a.regHouseholdNumber}세대`]);
  }

  if (rows.length === 0) return null;

  return (
    <Expander title="현재 건물 현황" defaultOpen={false}>
      <div className="text-[13px] space-y-0.5">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between py-0.5 gap-2">
            <span className="text-muted flex-shrink-0">{k}</span>
            <span className="text-ink-2 text-right">{v}</span>
          </div>
        ))}
      </div>
    </Expander>
  );
}

/**
 * 그룹멤버 매물 stub — 단독 호텔 시뮬은 의미 없으니
 * 부모 그룹 안내 + jump 버튼만.
 */
function MemberStub({
  article,
  parentGid,
  onNavigate,
}: {
  article: Article;
  parentGid: string;
  onNavigate?: (aid: string | null) => void;
}) {
  const { lookup, use } = useArticles();
  const [fetchedParent, setFetchedParent] = useState<Article | null>(null);
  const cachedParent = lookup(parentGid);
  useEffect(() => {
    if (cachedParent) return;
    let cancelled = false;
    fetchArticle(parentGid, use)
      .then((p) => { if (!cancelled) setFetchedParent(p); })
      .catch(() => { if (!cancelled) setFetchedParent(null); });
    return () => { cancelled = true; };
  }, [parentGid, cachedParent, use]);
  const parent = cachedParent ?? fetchedParent;

  const grade = parent?.devClass || "—";
  const gradeColor = parent ? capColor(parent.capRate) : "var(--color-accent)";
  const a = article;

  return (
    <div>
      <h2 className="text-xs font-semibold mb-3 uppercase tracking-wider text-muted">
        통합개발 멤버
      </h2>

      <div
        className="p-3 rounded-xl mb-3"
        style={{
          background: "var(--color-accent-soft)",
          border: "1px solid var(--color-accent-soft)",
        }}
      >
        <div className="text-[12.5px] text-accent mb-1">
          이 매물은 인접 필지와 묶였을 때 개발 규모가 나오는 부지예요
        </div>
        <div className="text-[13px] text-ink-2">
          인근 다른 매물과 묶어{" "}
          <b style={{ color: gradeColor }}>
            {parent?.groupSize ?? "?"}필지 {grade}
          </b>{" "}
          통합개발 후보로 분석됐어요.
        </div>
      </div>

      {/* 멤버 단독 정보 (작게) */}
      <div className="text-[13px] text-muted mb-3 space-y-0.5">
        <div>
          <b className="text-ink-2">{a.name || "(이름없음)"}</b>
        </div>
        {a.regRoadAddress && (
          <div className="text-[12px] text-muted">{a.regRoadAddress}</div>
        )}
        <div className="pt-2 grid grid-cols-2 gap-1 text-[12.5px]">
          <div>
            <span className="text-muted">매매가</span>{" "}
            <b className="text-ink-2">
              {a.dealPrice ? `${(a.dealPrice / 10000).toFixed(1)}억` : "—"}
            </b>
          </div>
          <div>
            <span className="text-muted">대지</span>{" "}
            <b className="text-ink-2">
              {a.landPyeong ? `${Math.round(a.landPyeong)}평` : "—"}
            </b>
          </div>
        </div>
      </div>

      {/* 그룹으로 이동 CTA */}
      <button
        onClick={() => onNavigate?.(parentGid)}
        className="w-full py-2.5 rounded text-ink font-semibold text-xs transition"
        style={{
          background: "var(--dash-grad-primary)",
          color: "var(--color-surface)",
          boxShadow: "none",
        }}
      >
        합필 부지 보기 ({parent?.groupSize ?? "?"}필지)
      </button>

      {/* 네이버 / Disco / 카카오 (멤버 단독) */}
      <div className="mt-3 grid grid-cols-2 gap-2">
        {!a.articleNo.startsWith("GROUP-") && (
          <a
            href={`https://fin.land.naver.com/articles/${a.articleNo}`}
            target="_blank"
            rel="noopener noreferrer"
            className="col-span-2 text-center py-1.5 rounded text-ink-2 text-[13px] transition"
            style={{
              border: "1px solid var(--dash-border)",
            }}
          >
            네이버부동산
          </a>
        )}
      </div>
    </div>
  );
}

function Kpi({ label, val }: { label: string; val: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] text-muted">{label}</dt>
      <dd className="num text-[15px] text-ink mt-0.5">{val}</dd>
    </div>
  );
}

/** 도시계획도 관례 색 (주거 = 노랑, 상업 = 분홍, 공업 = 보라, 녹지 = 초록). */
function zoningColor(z: string): string {
  if (z.includes("전용주거")) return "#fbeea8";
  if (z.includes("준주거")) return "#f1bd6a";
  if (z.includes("주거")) return "#f3dc6b";
  if (z.includes("상업")) return "#e58ba0";
  if (z.includes("공업")) return "#a898d6";
  if (z.includes("녹지")) return "#97c889";
  return "#cfd6dc";
}

function ZoningSwatch({ zoning }: { zoning: string }) {
  return (
    <span
      className="w-3 h-3 rounded-[2px] flex-shrink-0 border border-ink/15"
      style={{ background: zoningColor(zoning) }}
      aria-hidden="true"
    />
  );
}

function Row({
  label,
  val,
  valClass = "num text-ink-2",
}: {
  label: string;
  val: string;
  valClass?: string;
}) {
  return (
    <div className="flex justify-between gap-3 py-0.5">
      <span className="text-muted">{label}</span>
      <span className={`text-right ${valClass}`}>{val}</span>
    </div>
  );
}

function Expander({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-t border-line">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="w-full flex items-center justify-between h-10 text-[13px] font-medium text-ink hover:text-accent"
      >
        <span>{title}</span>
        <ChevronDown size={15} className={`text-muted transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <div className="pb-3 text-[12.5px]">{children}</div>}
    </div>
  );
}
