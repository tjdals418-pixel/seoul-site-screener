"use client";

/**
 * 비교 테이블 — 북마크된 매물 OR 필터 결과를 한 화면에서 횡 비교.
 *
 * 좌측 사이드바 expander. 호텔 개발 검토자가 가장 자주 묻는 질문
 * ("매물 A vs B, 평당가/Cap/객실수/연면적 어느 게 나은가") 를 한 표에서.
 *
 * Data source:
 *   - mode='bookmarks': useBookmarks의 ids로 개별 fetch
 *   - mode='filtered': 부모가 articles prop 전달 (현재 필터된 list)
 */
import { useEffect, useMemo, useState } from "react";
import {
  fetchArticle,
  type Article,
  type FilterParams,
} from "@/lib/api";
import { useArticles } from "@/lib/articles-context";
import { useBookmarks } from "@/lib/bookmarks";
import { capColor, siteTitle } from "@/lib/dev-class";
import { downloadArticlesCSV } from "@/lib/export";

type SortKey =
  | "name"
  | "divisionName"
  | "devClass"
  | "dealPrice"
  | "landPerPyeongM"
  | "landPyeong"
  | "devTotalPyeong"
  | "capRate";

type Mode = "bookmarks" | "filtered";

interface Props {
  /** 현재 적용된 필터 — 필터 결과 mode일 때 fetch에 사용. */
  filters: FilterParams;
  onNavigate?: (aid: string | null) => void;
}

export default function ComparisonTable({ filters, onNavigate }: Props) {
  void filters;       // 현재 ArticlesProvider가 filters에 따라 list 변경 (props는 호환용)
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Mode>("bookmarks");
  const [sortKey, setSortKey] = useState<SortKey>("capRate");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const { ids: bookmarkIds } = useBookmarks();
  const { candidates, lookup, use } = useArticles();

  // 북마크 매물 — 현재 목록에 있으면 그대로, 없는 것(필터 밖)만 fetch
  const { cached, missAids } = useMemo(() => {
    const cached: Article[] = [];
    const missAids: string[] = [];
    for (const aid of bookmarkIds) {
      const hit = lookup(aid);
      if (hit) cached.push(hit);
      else missAids.push(aid);
    }
    return { cached, missAids };
  }, [bookmarkIds, lookup]);
  const missKey = `${use}:${missAids.join(",")}`;
  const [fetchedMiss, setFetchedMiss] = useState<{ key: string; articles: Article[] } | null>(null);

  useEffect(() => {
    if (!open || mode !== "bookmarks" || missAids.length === 0) return;
    let cancelled = false;
    Promise.all(missAids.map((aid) => fetchArticle(aid, use).catch(() => null))).then((rs) => {
      if (!cancelled) {
        setFetchedMiss({ key: missKey, articles: rs.filter((a): a is Article => a !== null) });
      }
    });
    return () => { cancelled = true; };
  }, [open, mode, missAids, missKey, use]);

  const missReady = missAids.length === 0 || fetchedMiss?.key === missKey;
  const loading = open && mode === "bookmarks" && !missReady;
  const bookmarkArticles = useMemo(
    () => [...cached, ...(missReady && fetchedMiss?.key === missKey ? fetchedMiss.articles : [])],
    [cached, missReady, fetchedMiss, missKey],
  );

  // filtered mode — ArticlesProvider가 이미 filters 기준 list를 들고 있음
  const filteredArticles = candidates;

  const rows = useMemo<Article[]>(() => {
    const base = mode === "bookmarks" ? bookmarkArticles : filteredArticles;
    // 단일/통합만 — 그룹멤버는 보조 시각 (Cap 등 없음)
    const filtered = base.filter(
      (a) => !a.partOfGroup || a.isCombinedDevelopment
    );
    const sorted = [...filtered].sort((a, b) => {
      const va = a[sortKey];
      const vb = b[sortKey];
      // null은 항상 마지막
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === "string" && typeof vb === "string") {
        return sortDir === "asc"
          ? va.localeCompare(vb)
          : vb.localeCompare(va);
      }
      return sortDir === "asc"
        ? (va as number) - (vb as number)
        : (vb as number) - (va as number);
    });
    return sorted;
  }, [mode, bookmarkArticles, filteredArticles, sortKey, sortDir]);

  const setSort = (k: SortKey) => {
    if (k === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(k);
      setSortDir(k === "name" || k === "divisionName" ? "asc" : "desc");
    }
  };

  const exportCSV = () => {
    // 단일 통합 CSV (행=매물). N개 다운로드 prompt 회피.
    downloadArticlesCSV(rows, mode === "bookmarks" ? "북마크비교" : "필터비교");
  };

  return (
    <div className="mb-4">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-2 py-2 rounded text-[13px] font-semibold text-ink-2 hover:bg-ink/[0.04] transition"
        style={{
          background: "var(--dash-panel)",
          border: "1px solid var(--dash-border)",
        }}
      >
        <span>비교 테이블 ({rows.length})</span>
        <span className="text-muted">{open ? "▾" : "▸"}</span>
      </button>

      {open && (
        <div className="mt-2 space-y-2">
          {/* 모드 toggle */}
          <div className="flex gap-1">
            <button
              onClick={() => setMode("bookmarks")}
              className="flex-1 text-[12px] py-1 rounded transition"
              style={
                mode === "bookmarks"
                  ? {
                      background: "var(--dash-grad-primary)",
                      color: "var(--color-surface)",
                      fontWeight: 600,
                    }
                  : {
                      background: "var(--dash-panel)",
                      color: "var(--dash-muted)",
                      border: "1px solid var(--dash-border)",
                    }
              }
            >
              북마크 ({bookmarkIds.length})
            </button>
            <button
              onClick={() => setMode("filtered")}
              className="flex-1 text-[12px] py-1 rounded transition"
              style={
                mode === "filtered"
                  ? {
                      background: "var(--dash-grad-primary)",
                      color: "var(--color-surface)",
                      fontWeight: 600,
                    }
                  : {
                      background: "var(--dash-panel)",
                      color: "var(--dash-muted)",
                      border: "1px solid var(--dash-border)",
                    }
              }
            >
              필터 결과
            </button>
          </div>

          {loading && (
            <div className="text-[12px] text-muted px-1">로드 중...</div>
          )}

          {!loading && rows.length === 0 && (
            <div className="text-[12px] text-muted px-1 py-2 leading-relaxed">
              {mode === "bookmarks"
                ? "북마크한 부지가 없어요. 상세 화면의 북마크 버튼으로 추가하세요."
                : "필터 결과 없음."}
            </div>
          )}

          {!loading && rows.length > 0 && (
            <>
              {/* 표 — 가로 스크롤 가능 */}
              <div
                className="overflow-x-auto rounded"
                style={{
                  background: "var(--dash-panel)",
                  border: "1px solid var(--dash-border)",
                  maxHeight: "320px",
                  overflowY: "auto",
                }}
              >
                <table className="text-[11px] w-full">
                  <thead
                    className="text-muted sticky top-0"
                    style={{
                      background: "var(--dash-panel-strong)",
                      zIndex: 1,
                    }}
                  >
                    <tr>
                      <Th k="name" current={sortKey} dir={sortDir} setSort={setSort}>
                        매물
                      </Th>
                      <Th k="divisionName" current={sortKey} dir={sortDir} setSort={setSort}>
                        자치구
                      </Th>
                      <Th k="devClass" current={sortKey} dir={sortDir} setSort={setSort}>
                        등급·규모
                      </Th>
                      <Th k="dealPrice" current={sortKey} dir={sortDir} setSort={setSort} right>
                        매매가
                      </Th>
                      <Th k="landPerPyeongM" current={sortKey} dir={sortDir} setSort={setSort} right>
                        평당가
                      </Th>
                      <Th k="landPyeong" current={sortKey} dir={sortDir} setSort={setSort} right>
                        대지
                      </Th>
                      <Th k="devTotalPyeong" current={sortKey} dir={sortDir} setSort={setSort} right>
                        연면적(평)
                      </Th>
                      <Th k="capRate" current={sortKey} dir={sortDir} setSort={setSort} right>
                        Cap
                      </Th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((a) => (
                      <tr
                        key={a.articleNo}
                        className="border-t cursor-pointer hover:bg-ink/[0.04]"
                        style={{ borderColor: "var(--dash-border)" }}
                        onClick={() => onNavigate?.(a.articleNo)}
                      >
                        <td className="px-1.5 py-1 text-ink-2 truncate max-w-[100px]">
                          {siteTitle(a)}
                        </td>
                        <td className="px-1.5 py-1 text-muted whitespace-nowrap">
                          {a.divisionName ?? "—"}
                        </td>
                        <td className="px-1.5 py-1 text-muted whitespace-nowrap">
                          {a.devClass ?? "—"}
                        </td>
                        <td className="px-1.5 py-1 text-ink-2 text-right whitespace-nowrap">
                          {a.dealPrice
                            ? `${(a.dealPrice / 10000).toFixed(0)}억`
                            : "—"}
                        </td>
                        <td className="px-1.5 py-1 text-ink-2 text-right whitespace-nowrap">
                          {a.landPerPyeongM
                            ? `${a.landPerPyeongM.toFixed(1)}M`
                            : "—"}
                        </td>
                        <td className="px-1.5 py-1 text-ink-2 text-right whitespace-nowrap">
                          {a.landPyeong
                            ? `${Math.round(a.landPyeong).toLocaleString()}`
                            : "—"}
                        </td>
                        <td className="px-1.5 py-1 text-ink-2 text-right whitespace-nowrap">
                          {a.devTotalPyeong ? Math.round(a.devTotalPyeong).toLocaleString() : "—"}
                        </td>
                        <td
                          className="px-1.5 py-1 text-right font-semibold whitespace-nowrap"
                          style={{
                            color: a.capRate == null ? "var(--color-muted)" : capColor(a.capRate),
                          }}
                        >
                          {a.capRate != null
                            ? `${(a.capRate * 100).toFixed(2)}%`
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* CSV export */}
              <button
                onClick={exportCSV}
                className="w-full text-[12px] py-1 rounded text-muted hover:text-ink transition"
                style={{
                  background: "var(--dash-panel)",
                  border: "1px solid var(--dash-border)",
                }}
                title={`${rows.length}개 매물 한 파일에 다운로드`}
              >
                CSV 통합 다운로드 ({rows.length})
              </button>

              {/* 통계 한 줄 */}
              <div className="text-[10.5px] text-muted px-1 leading-relaxed">
                평균 Cap{" "}
                {(() => {
                  const caps = rows
                    .map((r) => r.capRate)
                    .filter((c): c is number => c != null);
                  return caps.length
                    ? `${((caps.reduce((s, c) => s + c, 0) / caps.length) * 100).toFixed(2)}%`
                    : "—";
                })()}{" "}
                · 평균 평당{" "}
                {(() => {
                  const lpp = rows
                    .map((r) => r.landPerPyeongM)
                    .filter((c): c is number => c != null);
                  return lpp.length
                    ? `${(lpp.reduce((s, c) => s + c, 0) / lpp.length).toFixed(1)}M`
                    : "—";
                })()}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Th({
  children,
  k,
  current,
  dir,
  setSort,
  right = false,
}: {
  children: React.ReactNode;
  k: SortKey;
  current: SortKey;
  dir: "asc" | "desc";
  setSort: (k: SortKey) => void;
  right?: boolean;
}) {
  const active = current === k;
  return (
    <th
      className={`px-1.5 py-1 cursor-pointer hover:text-ink whitespace-nowrap ${right ? "text-right" : "text-left"}`}
      onClick={() => setSort(k)}
      title="클릭하여 정렬"
    >
      <span className={active ? "text-ink" : ""}>
        {children}
        {active && (
          <span className="ml-0.5 text-[10px]">{dir === "asc" ? "▲" : "▼"}</span>
        )}
      </span>
    </th>
  );
}
