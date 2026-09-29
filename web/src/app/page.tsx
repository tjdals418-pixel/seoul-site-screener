"use client";

import { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { Info, ListOrdered, X } from "lucide-react";
import Sidebar, { DEFAULT_FILTERS } from "@/components/Sidebar";
import DetailPanel from "@/components/DetailPanel";
import SimForm, { type SimAssumptions } from "@/components/SimForm";
import SearchBookmark from "@/components/SearchBookmark";
import Ranking from "@/components/Ranking";
import ComparisonTable from "@/components/ComparisonTable";
import AboutModal from "@/components/AboutModal";
import { ArticlesProvider } from "@/lib/articles-context";
import { fetchMeta, type FilterParams, type MetaOptions } from "@/lib/api";
import { USE_OPTIONS, classesFor, type DevUse } from "@/lib/dev-class";

const Map = dynamic(() => import("@/components/Map"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center bg-paper">
      <span className="text-muted text-sm">지도 불러오는 중…</span>
    </div>
  ),
});

const LINKEDIN_URL = "https://www.linkedin.com/in/sungmin-heo-824a6a1a5/";

export default function Home() {
  const [filters, setFilters] = useState<FilterParams>(DEFAULT_FILTERS);
  const [sim, setSim] = useState<SimAssumptions | null>(null);
  const [use, setUse] = useState<DevUse>("best");
  const [meta, setMeta] = useState<MetaOptions | null>(null);
  const [selectedAid, setSelectedAid] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);

  useEffect(() => {
    fetchMeta().then(setMeta).catch(() => setMeta(null));
    // URL `?aid=` deep link → 매물 바로 열기 (hydration 이후에만 URL 접근)
    const aid = new URLSearchParams(window.location.search).get("aid");
    if (aid) setSelectedAid(aid); // eslint-disable-line react-hooks/set-state-in-effect
  }, []);

  // 용도를 바꾸면 그 용도에 없는 등급·규모 필터는 정리
  const changeUse = (next: DevUse) => {
    setUse(next);
    const valid = new Set(classesFor(next));
    setFilters((f) => ({ ...f, grades: (f.grades ?? []).filter((g) => valid.has(g)) }));
  };

  // Map이 초기화 effect에서 참조하므로 reference를 고정 (바뀌면 지도가 재생성됨)
  const select = useCallback((aid: string | null) => {
    setSelectedAid(aid);
    if (aid) setFiltersOpen(false);
  }, []);

  return (
    <main className="flex flex-col h-full overflow-hidden bg-paper text-ink">
      <header className="flex-shrink-0 border-b border-line bg-surface">
        <div className="flex items-center gap-3 px-4 md:px-5 h-14">
          <div className="min-w-0">
            <div className="font-mono text-[10px] tracking-[0.18em] text-muted leading-none">
              SEOUL SITE SCREENER
            </div>
            <h1 className="text-[15px] md:text-base font-semibold leading-tight mt-1 truncate">
              서울 개발부지 스크리너
            </h1>
          </div>

          <div className="hidden md:block ml-4">
            <UseSwitch value={use} onChange={changeUse} />
          </div>

          <div className="ml-auto flex items-center gap-2 md:gap-4">
            {meta?.data_as_of && (
              <span className="hidden lg:inline text-xs text-muted">
                매물 기준일 <span className="num text-ink-2">{meta.data_as_of}</span>
              </span>
            )}
            <button
              onClick={() => setAboutOpen(true)}
              className="inline-flex items-center gap-1.5 text-xs text-ink-2 hover:text-accent px-2 py-1.5 rounded"
            >
              <Info size={15} strokeWidth={1.75} />
              <span className="hidden sm:inline">모델 설명</span>
            </button>
            <a
              href={LINKEDIN_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="hidden sm:inline-flex items-center gap-1.5 text-xs text-ink-2 hover:text-accent"
              title="만든 사람 — LinkedIn"
            >
              허성민
              <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true" fill="currentColor">
                <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.063 2.063 0 112.063 2.065zm1.782 13.019H3.554V9h3.565v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
              </svg>
            </a>
          </div>
        </div>
        {/* 모바일: 용도 전환을 두 번째 줄로 */}
        <div className="md:hidden px-4 pb-2.5">
          <UseSwitch value={use} onChange={changeUse} full />
        </div>
      </header>

      <ArticlesProvider filters={filters} sim={sim} use={use}>
        <div className="relative flex flex-1 min-h-0">
          {/* 좌: 필터 레일 (모바일은 드로어) */}
          <aside
            className={`bg-surface border-r border-line overflow-y-auto flex-shrink-0
              fixed inset-y-0 left-0 z-40 w-[88vw] max-w-sm transition-transform duration-200
              md:static md:z-auto md:w-80 md:max-w-none md:translate-x-0
              ${filtersOpen ? "translate-x-0" : "-translate-x-full"}`}
            aria-label="사업성 순위와 조건"
          >
            <div className="md:hidden flex items-center justify-between px-4 h-12 border-b border-line">
              <span className="text-sm font-semibold">상위 부지 · 조건</span>
              <button onClick={() => setFiltersOpen(false)} className="p-1.5 text-muted" aria-label="닫기">
                <X size={18} />
              </button>
            </div>
            <div className="p-4 space-y-6">
              <Ranking onNavigate={select} selectedAid={selectedAid} />
              <Sidebar filters={filters} onChange={setFilters} use={use} meta={meta} />
              <section aria-labelledby="tools-title" className="space-y-3 pt-4 border-t border-line">
                <h2 id="tools-title" className="text-[13px] font-semibold">도구</h2>
                <SearchBookmark onNavigate={select} />
                <ComparisonTable filters={filters} onNavigate={select} />
                <SimForm onApply={setSim} isDefault={sim === null} />
              </section>
              <p className="text-[11px] leading-relaxed text-faint pt-3 border-t border-line">
                공개된 매물 호가를 바탕으로 한 개인 포트폴리오용 추정치입니다. 네이버와
                무관하며 투자 권유가 아닙니다.
              </p>
            </div>
          </aside>
          {filtersOpen && (
            <button
              className="md:hidden fixed inset-0 z-30 bg-ink/30"
              onClick={() => setFiltersOpen(false)}
              aria-label="필터 닫기"
            />
          )}

          {/* 중앙: 지도 */}
          <section className="flex-1 relative min-w-0">
            <Map filters={filters} onSelect={select} selectedAid={selectedAid} />
            <button
              onClick={() => setFiltersOpen(true)}
              className="md:hidden absolute top-3 left-3 z-10 inline-flex items-center gap-1.5 px-3 h-9 rounded bg-surface border border-line-strong text-sm font-medium shadow-sm"
            >
              <ListOrdered size={15} /> 상위 부지 · 조건
            </button>
          </section>

          {/* 우: 매물 시트 (모바일은 하단 시트, 선택 시에만) */}
          <aside
            className={`bg-surface border-line overflow-y-auto
              fixed inset-x-0 bottom-0 z-20 max-h-[62vh] border-t rounded-t-lg shadow-[0_-8px_24px_rgba(18,26,33,0.12)]
              md:static md:max-h-none md:w-[380px] md:flex-shrink-0 md:border-t-0 md:border-l md:rounded-none md:shadow-none
              ${selectedAid ? "block" : "hidden md:block"}`}
            aria-label="선택한 매물"
          >
            <div className="md:hidden sticky top-0 z-10 flex justify-between items-center px-4 h-10 bg-surface border-b border-line">
              <span className="w-10 h-1 rounded-full bg-line-strong mx-auto absolute left-1/2 -translate-x-1/2 top-1.5" />
              <span className="text-xs text-muted">매물 상세</span>
              <button onClick={() => setSelectedAid(null)} className="p-1 text-muted" aria-label="닫기">
                <X size={18} />
              </button>
            </div>
            <div className="p-4 md:p-5">
              <DetailPanel selectedAid={selectedAid} onNavigate={select} />
            </div>
          </aside>
        </div>
      </ArticlesProvider>

      <AboutModal open={aboutOpen} onClose={() => setAboutOpen(false)} meta={meta} />
    </main>
  );
}

function UseSwitch({
  value,
  onChange,
  full = false,
}: {
  value: DevUse;
  onChange: (u: DevUse) => void;
  full?: boolean;
}) {
  return (
    <div
      role="radiogroup"
      aria-label="개발 용도"
      className={`inline-flex p-0.5 rounded-md bg-sunken border border-line ${full ? "w-full" : ""}`}
    >
      {USE_OPTIONS.map((o) => {
        const active = o.key === value;
        return (
          <button
            key={o.key}
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.key)}
            title={o.desc}
            className={`px-3.5 h-8 rounded text-[13px] transition-colors ${full ? "flex-1" : ""} ${
              active
                ? "bg-surface text-ink font-semibold shadow-[0_1px_2px_rgba(18,26,33,0.12)] border border-line"
                : "text-muted hover:text-ink border border-transparent"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
