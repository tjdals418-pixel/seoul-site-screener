"use client";

import { useMemo, useState } from "react";
import type { Article } from "@/lib/api";
import { useArticles } from "@/lib/articles-context";
import { capColor, siteTitle } from "@/lib/dev-class";

type SortKey = "cap" | "priceAsc" | "landPpAsc";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "cap", label: "취득 Cap" },
  { key: "priceAsc", label: "매매가 낮은" },
  { key: "landPpAsc", label: "평당가 낮은" },
];

const PAGE = 12;

function sortValue(a: Article, key: SortKey): number {
  switch (key) {
    case "cap": return -(a.capRate ?? -1);
    case "priceAsc": return a.dealPrice ?? Infinity;
    case "landPpAsc": return a.landPerPyeongM ?? Infinity;
  }
}

interface Props {
  onNavigate: (aid: string) => void;
  selectedAid?: string | null;
}

/**
 * 첫 화면의 주인공 — 현재 조건에서 취득 Cap(NOI ÷ 총사업비) 높은 부지 순위.
 * 지도·필터·가정값과 같은 목록을 공유한다 (그룹멤버 제외 = 실제 개발 후보).
 */
export default function Ranking({ onNavigate, selectedAid }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("cap");
  const [shown, setShown] = useState(PAGE);
  const { candidates, loading } = useArticles();
  const sorted = useMemo(
    () => [...candidates].sort((a, b) => sortValue(a, sortKey) - sortValue(b, sortKey)),
    [candidates, sortKey],
  );
  const top = sorted.slice(0, shown);

  return (
    <section aria-labelledby="ranking-title">
      <div className="flex items-baseline justify-between mb-2">
        <h2 id="ranking-title" className="text-[13px] font-semibold">
          사업성 상위 부지
        </h2>
        <span className="text-[11px] text-muted">
          후보 <span className="num text-ink-2">{candidates.length}</span>곳
        </span>
      </div>

      <div className="flex gap-1 mb-2" role="group" aria-label="정렬 기준">
        {SORTS.map((s) => (
          <button
            key={s.key}
            aria-pressed={sortKey === s.key}
            onClick={() => { setSortKey(s.key); setShown(PAGE); }}
            className={`h-7 px-2 rounded text-[12px] transition-colors ${
              sortKey === s.key ? "bg-ink text-surface" : "text-muted hover:text-ink"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {loading && candidates.length === 0 ? (
        <div className="text-[12.5px] text-muted py-6 text-center">불러오는 중…</div>
      ) : top.length === 0 ? (
        <div className="text-[12.5px] text-muted py-6 text-center leading-relaxed">
          조건에 맞는 부지가 없어요.
          <br />
          최소 취득 Cap이나 자치구 조건을 풀어보세요.
        </div>
      ) : (
        <ol className="border-t border-line">
          {top.map((a, idx) => {
            const active = a.articleNo === selectedAid;
            return (
              <li key={a.articleNo}>
                <button
                  onClick={() => onNavigate(a.articleNo)}
                  className={`w-full grid grid-cols-[1.25rem_1fr_auto] items-center gap-2 py-2 px-1 border-b border-line text-left transition-colors ${
                    active ? "bg-accent-soft" : "hover:bg-sunken"
                  }`}
                >
                  <span className="num text-[11px] text-faint text-right">{idx + 1}</span>
                  <span className="min-w-0">
                    <span className="block text-[13px] text-ink truncate">
                      {siteTitle(a)}
                    </span>
                    <span className="block text-[11.5px] text-muted truncate">
                      {a.divisionName} · {a.devClass ?? "—"}
                      {a.landPyeong ? ` · 대지 ${Math.round(a.landPyeong)}평` : ""}
                      {a.dealPrice ? ` · ${Math.round(a.dealPrice / 10000).toLocaleString()}억` : ""}
                    </span>
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ background: capColor(a.capRate) }}
                      aria-hidden="true"
                    />
                    <span className="num text-[13px] text-ink font-medium">
                      {a.capRate != null ? `${(a.capRate * 100).toFixed(2)}%` : "—"}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      )}

      {sorted.length > shown && (
        <button
          onClick={() => setShown(shown + PAGE)}
          className="w-full mt-2 h-8 text-[12px] text-accent hover:bg-accent-soft rounded"
        >
          더 보기 ({sorted.length - shown}곳 남음)
        </button>
      )}
    </section>
  );
}
