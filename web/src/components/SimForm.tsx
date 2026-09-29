"use client";

import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import { fetchSimDefaults } from "@/lib/api";
import { useSimHistory } from "@/lib/sim-history";

/**
 * 시뮬 가정값 form. [적용] 시 onApply → ArticlesProvider가 POST /api/simulate.
 *
 * 초기값은 backend `/api/meta/sim-defaults` (= config/default.yaml). 응답 전/실패
 * 시에만 FALLBACK_SIM 사용.
 */

export interface GradeProfile {
  adr_10k: number;
  occupancy: number;
  fnb_ratio: number;
  gop_ratio: number;
  construction_cost_per_pyeong_M: number;
  room_area_sqm: number;
  exclusive_ratio: number;
}

export interface OfficeMarket {
  noc_10k: number;
  vacancy: number;
  exit_cap: number;
}

export interface OfficeProfile {
  min_total_pyeong: number;
  exclusive_ratio: number;
  opex_10k_per_pyeong: number;
  construction_cost_per_pyeong_M: number;
  markets: Record<string, OfficeMarket>;
}

export interface SimAssumptions {
  grade_3_min_pyeong: number;
  grade_4_min_pyeong: number;
  grade_5_min_pyeong: number;
  grade_3: GradeProfile;
  grade_4: GradeProfile;
  grade_5: GradeProfile;
  office: OfficeProfile;
}

const FALLBACK_SIM: SimAssumptions = {
  grade_3_min_pyeong: 1500,
  grade_4_min_pyeong: 3000,
  grade_5_min_pyeong: 7000,
  grade_3: {
    adr_10k: 15.0, occupancy: 0.87, fnb_ratio: 0.10, gop_ratio: 0.50,
    construction_cost_per_pyeong_M: 12.0, room_area_sqm: 20.0, exclusive_ratio: 0.80,
  },
  grade_4: {
    adr_10k: 20.0, occupancy: 0.85, fnb_ratio: 0.15, gop_ratio: 0.45,
    construction_cost_per_pyeong_M: 14.0, room_area_sqm: 25.0, exclusive_ratio: 0.70,
  },
  grade_5: {
    adr_10k: 40.0, occupancy: 0.80, fnb_ratio: 0.30, gop_ratio: 0.375,
    construction_cost_per_pyeong_M: 18.0, room_area_sqm: 33.0, exclusive_ratio: 0.50,
  },
  office: {
    min_total_pyeong: 1000,
    exclusive_ratio: 0.5,
    opex_10k_per_pyeong: 3.0,
    construction_cost_per_pyeong_M: 11.0,
    markets: {
      CBD: { noc_10k: 28.0, vacancy: 0, exit_cap: 0.045 },
      GBD: { noc_10k: 28.0, vacancy: 0, exit_cap: 0.045 },
      YBD: { noc_10k: 24.0, vacancy: 0, exit_cap: 0.048 },
      기타: { noc_10k: 17.0, vacancy: 0, exit_cap: 0.055 },
    },
  },
};

const MARKET_LABELS: Record<string, string> = {
  CBD: "CBD (중구·종로)",
  GBD: "GBD (강남·서초)",
  YBD: "YBD (영등포·마포)",
  기타: "기타 권역",
};

/** backend 응답(DevAssumptions 전체)에서 form이 다루는 키만 추출. */
function pickSim(raw: Record<string, unknown>, base: SimAssumptions): SimAssumptions {
  const r = raw as Partial<SimAssumptions>;
  const pickGrade = (g: GradeProfile | undefined, d: GradeProfile): GradeProfile => ({ ...d, ...(g ?? {}) });
  const o = (r.office ?? {}) as Partial<OfficeProfile>;
  return {
    grade_3_min_pyeong: r.grade_3_min_pyeong ?? base.grade_3_min_pyeong,
    grade_4_min_pyeong: r.grade_4_min_pyeong ?? base.grade_4_min_pyeong,
    grade_5_min_pyeong: r.grade_5_min_pyeong ?? base.grade_5_min_pyeong,
    grade_3: pickGrade(r.grade_3, base.grade_3),
    grade_4: pickGrade(r.grade_4, base.grade_4),
    grade_5: pickGrade(r.grade_5, base.grade_5),
    office: {
      min_total_pyeong: o.min_total_pyeong ?? base.office.min_total_pyeong,
      exclusive_ratio: o.exclusive_ratio ?? base.office.exclusive_ratio,
      opex_10k_per_pyeong: o.opex_10k_per_pyeong ?? base.office.opex_10k_per_pyeong,
      construction_cost_per_pyeong_M:
        o.construction_cost_per_pyeong_M ?? base.office.construction_cost_per_pyeong_M,
      markets: Object.fromEntries(
        Object.entries(base.office.markets).map(([k, m]) => [k, { ...m, ...(o.markets?.[k] ?? {}) }]),
      ),
    },
  };
}

interface Props {
  onApply: (sim: SimAssumptions | null) => void;
  isDefault: boolean;
}

export default function SimForm({ onApply, isDefault }: Props) {
  const [open, setOpen] = useState(false);
  const [defaults, setDefaults] = useState<SimAssumptions>(FALLBACK_SIM);
  const [draft, setDraft] = useState<SimAssumptions>(FALLBACK_SIM);
  const [tab, setTab] = useState<"hotel" | "office">("hotel");
  const [openHistory, setOpenHistory] = useState(false);
  const { entries, save, remove, clear } = useSimHistory();

  useEffect(() => {
    let cancelled = false;
    fetchSimDefaults()
      .then((raw) => {
        if (cancelled) return;
        const d = pickSim(raw, FALLBACK_SIM);
        setDefaults(d);
        setDraft(d);
      })
      .catch(() => { /* FALLBACK_SIM 유지 */ });
    return () => { cancelled = true; };
  }, []);

  const apply = () => onApply(draft);
  const reset = () => {
    setDraft(defaults);
    onApply(null); // backend 기본값 사용 (GET)
  };
  const saveCurrent = () => {
    const label = prompt("이 가정값에 이름을 붙여주세요 (선택)", "") || undefined;
    save(draft, label);
  };
  const restore = (sim: SimAssumptions) => {
    // 옛 버전 히스토리(오피스 가정 없음)도 기본값과 병합해 복원
    const merged = pickSim(sim as unknown as Record<string, unknown>, defaults);
    setDraft(merged);
    onApply(merged);
  };
  const setMarket = (name: string, m: OfficeMarket) =>
    setDraft({
      ...draft,
      office: { ...draft.office, markets: { ...draft.office.markets, [name]: m } },
    });

  return (
    <div className="mb-4">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 h-9 rounded text-[13px] font-medium text-ink-2 hover:bg-sunken transition"
        style={{
          background: open ? "var(--dash-panel)" : "transparent",
          border: "1px solid var(--dash-border)",
        }}
      >
        <span>
          시뮬 가정값{" "}
          {!isDefault && (
            <span className="ml-1 text-[10.5px] px-1.5 py-0.5 rounded bg-accent-soft text-accent">
              변경됨
            </span>
          )}
        </span>
        <span className="text-muted">{open ? "▾" : "▸"}</span>
      </button>

      {open && (
        <div
          className="mt-2 p-3 rounded space-y-3"
          style={{
            background: "var(--dash-panel)",
            border: "1px solid var(--dash-border)",
          }}
        >
          <p className="text-[12.5px] text-muted leading-relaxed">
            호텔 등급별 ADR·공사비, 오피스 권역별 NOC 등을 조정합니다.
            [적용]을 누르면 모든 매물의 취득 Cap이 다시 계산됩니다.
          </p>

          <ActionRow onApply={apply} onSave={saveCurrent} onReset={reset} />

          {/* 히스토리 */}
          <div>
            <button
              onClick={() => setOpenHistory(!openHistory)}
              className="w-full flex items-center justify-between px-2 py-1 rounded text-[12.5px] text-muted hover:bg-ink/[0.04] transition"
            >
              <span>
                히스토리{" "}
                {entries.length > 0 && (
                  <span className="ml-1 text-[10.5px] text-muted">({entries.length})</span>
                )}
              </span>
              <span className="text-faint">{openHistory ? "▾" : "▸"}</span>
            </button>
            {openHistory && (
              <div className="mt-1 space-y-1 max-h-44 overflow-y-auto">
                {entries.length === 0 ? (
                  <div className="text-[12px] text-faint px-2 py-1.5">
                    저장된 가정값이 없어요. 저장 버튼으로 남겨두세요.
                  </div>
                ) : (
                  <>
                    {entries.map((e) => {
                      const d = new Date(e.timestamp);
                      const label = e.label || `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
                      return (
                        <div
                          key={e.id}
                          className="flex items-center justify-between gap-1 px-2 py-1 rounded text-[12.5px] hover:bg-ink/[0.04] group"
                          style={{ background: "var(--color-sunken)" }}
                        >
                          <button
                            onClick={() => restore(e.sim)}
                            className="flex-1 min-w-0 text-left text-ink-2 truncate hover:text-ink transition"
                          >
                            ⟲ {label}
                          </button>
                          <button
                            onClick={() => remove(e.id)}
                            className="text-faint hover:text-bad md:opacity-0 md:group-hover:opacity-100 transition text-xs"
                            title="삭제"
                          >
                            ✕
                          </button>
                        </div>
                      );
                    })}
                    <button
                      onClick={() => {
                        if (confirm(`히스토리 ${entries.length}개 전체 삭제?`)) clear();
                      }}
                      className="w-full py-1 text-[11px] text-faint hover:text-bad transition"
                    >
                      전체 비우기
                    </button>
                  </>
                )}
              </div>
            )}
          </div>

          {/* 호텔 / 오피스 탭 */}
          <div className="flex gap-1 p-0.5 rounded" style={{ background: "var(--color-sunken)" }}>
            {(["hotel", "office"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className="flex-1 py-1 rounded text-[12.5px] font-semibold transition"
                style={
                  tab === t
                    ? { background: "var(--dash-grad-primary)", color: "var(--color-surface)" }
                    : { color: "var(--dash-muted)" }
                }
              >
                {t === "hotel" ? "호텔" : "오피스"}
              </button>
            ))}
          </div>

          {tab === "hotel" ? (
            <>
              <div>
                <div className="text-[12px] font-semibold text-muted mb-1">
                  등급 분류 임계 (개발 연면적 평)
                </div>
                <NumberInput label="3성급 최소" value={draft.grade_3_min_pyeong} min={500} max={5000} step={100}
                  onChange={(v) => setDraft({ ...draft, grade_3_min_pyeong: v })} />
                <NumberInput label="4성급 최소" value={draft.grade_4_min_pyeong} min={1000} max={10000} step={100}
                  onChange={(v) => setDraft({ ...draft, grade_4_min_pyeong: v })} />
                <NumberInput label="5성급 최소" value={draft.grade_5_min_pyeong} min={3000} max={20000} step={500}
                  onChange={(v) => setDraft({ ...draft, grade_5_min_pyeong: v })} />
              </div>
              {(["grade_3", "grade_4", "grade_5"] as const).map((key) => (
                <GradeBox
                  key={key}
                  label={key === "grade_3" ? "3성급" : key === "grade_4" ? "4성급" : "5성급"}
                  profile={draft[key]}
                  onChange={(p) => setDraft({ ...draft, [key]: p })}
                />
              ))}
            </>
          ) : (
            <>
              <Box title="공통">
                <NumberInput label="최소 연면적 (평)" value={draft.office.min_total_pyeong} min={300} max={10000} step={100}
                  onChange={(v) => setDraft({ ...draft, office: { ...draft.office, min_total_pyeong: v } })} />
                <NumberInput label="평당공사비 (백만/평)" value={draft.office.construction_cost_per_pyeong_M} min={5} max={30} step={0.5} decimals={1}
                  onChange={(v) => setDraft({ ...draft, office: { ...draft.office, construction_cost_per_pyeong_M: v } })} />
                <NumberInput label="전용률" value={draft.office.exclusive_ratio} min={0.3} max={0.9} step={0.01} decimals={2}
                  onChange={(v) => setDraft({ ...draft, office: { ...draft.office, exclusive_ratio: v } })} />
                <NumberInput label="운용비용 (만원/임대평/월)" value={draft.office.opex_10k_per_pyeong} min={0} max={10} step={0.1} decimals={1}
                  onChange={(v) => setDraft({ ...draft, office: { ...draft.office, opex_10k_per_pyeong: v } })} />
              </Box>
              {Object.entries(draft.office.markets).map(([name, m]) => (
                <Box key={name} title={MARKET_LABELS[name] ?? name}>
                  <NumberInput label="NOC (만원/전용평/월)" value={m.noc_10k} min={5} max={60} step={0.5} decimals={1}
                    onChange={(v) => setMarket(name, { ...m, noc_10k: v })} />
                  <NumberInput label="공실률" value={m.vacancy} min={0} max={0.4} step={0.01} decimals={2}
                    onChange={(v) => setMarket(name, { ...m, vacancy: v })} />
                  <NumberInput label="매각 Cap (DCF용)" value={m.exit_cap} min={0.03} max={0.1} step={0.0025} decimals={4}
                    onChange={(v) => setMarket(name, { ...m, exit_cap: v })} />
                </Box>
              ))}
            </>
          )}

          <ActionRow onApply={apply} />
        </div>
      )}
    </div>
  );
}

function ActionRow({
  onApply,
  onSave,
  onReset,
}: {
  onApply: () => void;
  onSave?: () => void;
  onReset?: () => void;
}) {
  const sub = {
    background: "var(--dash-panel-strong)",
    border: "1px solid var(--dash-border)",
  };
  return (
    <div className="flex gap-2">
      <button
        onClick={onApply}
        className="flex-1 py-1.5 rounded text-ink text-xs font-semibold transition"
        style={{
          background: "var(--dash-grad-primary)",
          color: "var(--color-surface)",
          boxShadow: "none",
        }}
      >
        시뮬 적용
      </button>
      {onSave && (
        <button onClick={onSave} className="px-3 py-1.5 rounded text-xs text-ink-2 hover:text-ink transition"
          style={sub} title="현재 가정값을 히스토리에 저장" aria-label="가정값 저장">
          <Save size={13} />
                  </button>
      )}
      {onReset && (
        <button onClick={onReset} className="px-3 py-1.5 rounded text-xs text-muted hover:text-ink transition"
          style={sub} title="기본값으로 초기화">
          ↺
        </button>
      )}
    </div>
  );
}

function Box({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      className="p-2 rounded-md"
      style={{
        background: "var(--color-sunken)",
        border: "1px solid var(--dash-border)",
      }}
    >
      <div className="text-[12.5px] font-semibold text-ink-2 mb-1.5">{title}</div>
      {children}
    </div>
  );
}

function GradeBox({
  label,
  profile,
  onChange,
}: {
  label: string;
  profile: GradeProfile;
  onChange: (p: GradeProfile) => void;
}) {
  return (
    <Box title={`${label} 가정값`}>
      <NumberInput label="ADR (만원/박)" value={profile.adr_10k} min={1} max={200} step={1}
        onChange={(v) => onChange({ ...profile, adr_10k: v })} />
      <NumberInput label="Occupancy" value={profile.occupancy} min={0.1} max={1} step={0.01} decimals={2}
        onChange={(v) => onChange({ ...profile, occupancy: v })} />
      <NumberInput label="평당공사비 (백만/평)" value={profile.construction_cost_per_pyeong_M} min={1} max={50} step={0.5} decimals={1}
        onChange={(v) => onChange({ ...profile, construction_cost_per_pyeong_M: v })} />
      <NumberInput label="객실면적 (㎡)" value={profile.room_area_sqm} min={10} max={80} step={1}
        onChange={(v) => onChange({ ...profile, room_area_sqm: v })} />
      <NumberInput label="전용율" value={profile.exclusive_ratio} min={0.3} max={1} step={0.05} decimals={2}
        onChange={(v) => onChange({ ...profile, exclusive_ratio: v })} />
      <NumberInput label="GOP 마진" value={profile.gop_ratio} min={0.1} max={0.8} step={0.025} decimals={3}
        onChange={(v) => onChange({ ...profile, gop_ratio: v })} />
      <NumberInput label="F&B 비율 (객실매출 대비)" value={profile.fnb_ratio} min={0} max={1} step={0.05} decimals={2}
        onChange={(v) => onChange({ ...profile, fnb_ratio: v })} />
    </Box>
  );
}

function NumberInput({
  label,
  value,
  min,
  max,
  step,
  onChange,
  decimals = 0,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  decimals?: number;
}) {
  const round = (v: number) => Number(v.toFixed(Math.max(decimals, 4)));
  return (
    <div className="flex items-center justify-between py-0.5 text-[12.5px]">
      <label className="text-muted mr-2 truncate">{label}</label>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onChange(round(Math.max(min, value - step)))}
          className="w-6 h-6 rounded text-muted hover:bg-ink/[0.07] text-xs"
          aria-label={`${label} 감소`}
        >
          −
        </button>
        <input
          type="number"
          value={value.toFixed(decimals)}
          min={min}
          max={max}
          step={step}
          onChange={(e) => {
            const v = Number(e.target.value);
            if (!Number.isFinite(v)) return;
            onChange(Math.min(max, Math.max(min, v)));
          }}
          className="w-16 text-right bg-transparent border rounded px-1 py-0.5 text-ink-2 text-[12.5px]"
          style={{ borderColor: "var(--dash-border)" }}
          aria-label={label}
        />
        <button
          onClick={() => onChange(round(Math.min(max, value + step)))}
          className="w-6 h-6 rounded text-muted hover:bg-ink/[0.07] text-xs"
          aria-label={`${label} 증가`}
        >
          +
        </button>
      </div>
    </div>
  );
}
