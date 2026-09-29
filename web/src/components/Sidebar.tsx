"use client";

import { useState } from "react";
import { ChevronDown, RotateCcw } from "lucide-react";
import type { FilterParams, MetaOptions } from "@/lib/api";
import { classesFor, type DevUse } from "@/lib/dev-class";

const ALL_CATEGORIES = ["단일", "통합그룹", "그룹멤버"];
const CATEGORY_LABELS: Record<string, string> = {
  단일: "단일 필지",
  통합그룹: "합필 (인접 필지 묶음)",
  그룹멤버: "합필 구성 필지",
};
export const DEFAULT_FILTERS: FilterParams = {
  categories: ["단일", "통합그룹"],
  grades: [],
  hotel_zone_only: true,   // 주거지역 등 신축 불가 지역은 기본 제외
};

const CAP_STEPS = [0, 0.03, 0.04, 0.05, 0.06, 0.07];

interface Props {
  filters: FilterParams;
  onChange: (next: FilterParams) => void;
  use: DevUse;
  meta: MetaOptions | null;
}

/** 조건 — 바꾸는 즉시 지도·순위에 반영 (필터링은 클라이언트에서 수행). */
export default function Sidebar({ filters, onChange, use, meta }: Props) {
  const [moreOpen, setMoreOpen] = useState(false);
  const set = (patch: Partial<FilterParams>) => onChange({ ...filters, ...patch });
  const toggle = (arr: string[] | undefined, val: string): string[] => {
    const cur = arr ?? [];
    return cur.includes(val) ? cur.filter((x) => x !== val) : [...cur, val];
  };
  // 값이 비어 있거나 기본값과 같은 항목은 무시하고 비교 (예: gu: [] 는 기본 상태)
  const meaningful = (f: FilterParams) =>
    JSON.stringify(
      Object.entries(f)
        .filter(([, v]) => v !== undefined && v !== false && !(Array.isArray(v) && v.length === 0))
        .sort(([x], [y]) => x.localeCompare(y)),
    );
  const isDefault = meaningful(filters) === meaningful(DEFAULT_FILTERS);
  const priceMax = meta?.price_max_M ?? 100000;
  const landMax = meta?.land_max_pyeong ?? 10000;

  return (
    <section aria-labelledby="filters-title">
      <div className="flex items-center justify-between mb-3">
        <h2 id="filters-title" className="text-[13px] font-semibold">조건</h2>
        {!isDefault && (
          <button
            onClick={() => onChange(DEFAULT_FILTERS)}
            className="inline-flex items-center gap-1 text-[12px] text-muted hover:text-accent"
          >
            <RotateCcw size={12} /> 초기화
          </button>
        )}
      </div>

      <Field label="최소 취득 Cap">
        <div className="grid grid-cols-6 gap-1">
          {CAP_STEPS.map((v) => {
            const active = (filters.cap_min ?? 0) === v;
            return (
              <button
                key={v}
                onClick={() => set({ cap_min: v === 0 ? undefined : v })}
                aria-pressed={active}
                className={`num h-8 rounded text-[12px] border transition-colors ${
                  active
                    ? "bg-accent text-surface border-accent"
                    : "bg-surface border-line text-ink-2 hover:border-line-strong"
                }`}
              >
                {v === 0 ? "전체" : `${Math.round(v * 100)}%+`}
              </button>
            );
          })}
        </div>
      </Field>

      <Field label="자치구" hint={(filters.gu ?? []).length ? `${filters.gu!.length}곳 선택` : "전체"}>
        <div className="flex flex-wrap gap-1">
          {meta?.gu.map((g) => (
            <Chip
              key={g}
              label={g.replace(/구$/, "")}
              active={(filters.gu ?? []).includes(g)}
              onClick={() => set({ gu: toggle(filters.gu, g) })}
            />
          ))}
        </div>
      </Field>

      <Field
        label={use === "hotel" ? "호텔 등급" : use === "office" ? "오피스 규모" : "등급 · 규모"}
        hint={(filters.grades ?? []).length ? undefined : "전체"}
      >
        <div className="flex flex-wrap gap-1">
          {classesFor(use).map((g) => (
            <Chip
              key={g}
              label={g}
              active={(filters.grades ?? []).includes(g)}
              onClick={() => set({ grades: toggle(filters.grades, g) })}
            />
          ))}
        </div>
      </Field>

      <button
        onClick={() => setMoreOpen(!moreOpen)}
        aria-expanded={moreOpen}
        className="w-full flex items-center justify-between py-2 text-[12.5px] text-ink-2 hover:text-accent border-t border-line"
      >
        상세 조건
        <ChevronDown size={15} className={`transition-transform ${moreOpen ? "rotate-180" : ""}`} />
      </button>

      {moreOpen && (
        <div className="pt-2">
          <Field label="매매가 (호가)">
            <RangeInput
              min={0}
              max={priceMax}
              step={Math.max(100, Math.floor(priceMax / 100))}
              minValue={filters.price_min_M ?? 0}
              maxValue={filters.price_max_M ?? priceMax}
              onChange={(lo, hi) =>
                set({ price_min_M: lo || undefined, price_max_M: hi >= priceMax ? undefined : hi })
              }
              format={(v) => `${Math.round(v / 100).toLocaleString()}억`}
            />
          </Field>

          <Field label="대지면적">
            <RangeInput
              min={0}
              max={landMax}
              step={50}
              minValue={filters.land_min ?? 0}
              maxValue={filters.land_max ?? landMax}
              onChange={(lo, hi) =>
                set({ land_min: lo || undefined, land_max: hi >= landMax ? undefined : hi })
              }
              format={(v) => `${v.toLocaleString()}평`}
            />
          </Field>

          <Field label="매물 구분">
            <div className="flex flex-wrap gap-1">
              {ALL_CATEGORIES.map((c) => (
                <Chip
                  key={c}
                  label={CATEGORY_LABELS[c]}
                  active={(filters.categories ?? []).includes(c)}
                  onClick={() => set({ categories: toggle(filters.categories, c) })}
                />
              ))}
            </div>
          </Field>

          <Field label="입지 · 규제">
            <div className="space-y-1.5">
              <Check
                id="f-rail"
                label="개통 예정 역 인근만"
                checked={filters.only_with_rail ?? false}
                onChange={(v) => set({ only_with_rail: v })}
              />
              <Check
                id="f-jigu"
                label="지구단위계획구역만"
                checked={filters.only_with_jigu ?? false}
                onChange={(v) => set({ only_with_jigu: v })}
              />
              <Check
                id="f-zone"
                label="상업·준주거·준공업 지역만"
                checked={filters.hotel_zone_only ?? false}
                onChange={(v) => set({ hotel_zone_only: v })}
              />
              <Check
                id="f-outlier"
                label="데이터 이상치로 표시된 매물만"
                checked={filters.outliers_only ?? false}
                onChange={(v) => set({ outliers_only: v })}
              />
            </div>
          </Field>
        </div>
      )}
    </section>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-4">
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="text-[12px] text-muted">{label}</span>
        {hint && <span className="text-[11px] text-faint">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

function Chip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`h-9 md:h-7 px-2.5 rounded text-[12px] border transition-colors ${
        active
          ? "bg-accent-soft border-accent/50 text-accent font-medium"
          : "bg-surface border-line text-ink-2 hover:border-line-strong"
      }`}
    >
      {label}
    </button>
  );
}

function Check({
  id,
  label,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label htmlFor={id} className="flex items-center gap-2 text-[12.5px] text-ink-2 cursor-pointer">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="w-3.5 h-3.5 accent-[var(--color-accent)]"
      />
      {label}
    </label>
  );
}

function RangeInput({
  min,
  max,
  step,
  minValue,
  maxValue,
  onChange,
  format,
}: {
  min: number;
  max: number;
  step: number;
  minValue: number;
  maxValue: number;
  onChange: (lo: number, hi: number) => void;
  format: (v: number) => string;
}) {
  return (
    <div className="w-full">
      <div className="num flex justify-between text-[11.5px] text-ink-2 mb-1">
        <span>{format(minValue)}</span>
        <span>{maxValue >= max ? `${format(max)}+` : format(maxValue)}</span>
      </div>
      <div className="flex gap-2">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={minValue}
          aria-label="최소"
          onChange={(e) => onChange(Math.min(Number(e.target.value), maxValue), maxValue)}
          className="w-full"
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={maxValue}
          aria-label="최대"
          onChange={(e) => onChange(minValue, Math.max(Number(e.target.value), minValue))}
          className="w-full"
        />
      </div>
    </div>
  );
}
