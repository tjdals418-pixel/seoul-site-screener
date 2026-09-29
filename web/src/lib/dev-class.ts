/**
 * 개발 용도(호텔/오피스)와 등급·규모 구분 — 색상/라벨 단일 source.
 * Map / DetailPanel / Ranking / SearchBookmark / Sidebar가 공유.
 */

export type DevUse = "hotel" | "office" | "best";

export const USE_OPTIONS: { key: DevUse; label: string; short: string; desc: string }[] = [
  { key: "best", label: "최적 용도", short: "최적", desc: "호텔·오피스 중 취득 Cap이 높은 용도 (신축 가능 용도지역만)" },
  { key: "hotel", label: "호텔", short: "호텔", desc: "호텔 개발 시뮬 (연면적으로 3/4/5성급 분류)" },
  { key: "office", label: "오피스", short: "오피스", desc: "임대형 오피스 개발 시뮬 (권역별 NOC)" },
];

export const HOTEL_CLASSES = ["5성급", "4성급", "3성급"] as const;
export const OFFICE_CLASSES = ["대형 오피스", "중대형 오피스", "중형 오피스", "소형 오피스"] as const;

/**
 * 취득 Cap (NOI ÷ 총사업비) 구간 — 지도 마커·리스트의 색은 이것 하나만 뜻한다.
 * 높은 구간일수록 진한 녹색, 낮은 구간은 회색으로 물러나게.
 */
export const CAP_BANDS: { min: number; label: string; color: string }[] = [
  { min: 0.06, label: "6% 이상", color: "#17603a" },
  { min: 0.05, label: "5 – 6%", color: "#4c9a5b" },
  { min: 0.04, label: "4 – 5%", color: "#c99a2e" },
  { min: -Infinity, label: "4% 미만", color: "#a3adb6" },
];

export function capColor(cap: number | null | undefined): string {
  if (cap == null) return "#a3adb6";
  return (CAP_BANDS.find((b) => cap >= b.min) ?? CAP_BANDS[CAP_BANDS.length - 1]).color;
}

/** 용도별 필터 chip / 범례 목록. */
export function classesFor(use: DevUse): string[] {
  if (use === "hotel") return [...HOTEL_CLASSES];
  if (use === "office") return [...OFFICE_CLASSES];
  return [...HOTEL_CLASSES, ...OFFICE_CLASSES];
}

export function useLabel(devUse: string | null | undefined): string {
  if (devUse === "hotel") return "호텔";
  if (devUse === "office") return "오피스";
  return "—";
}

/** 매물 표시 이름 — 네이버 매물명이 "빌딩"·"기타"처럼 일반명사인 경우가 많아 동 이름을 붙인다. */
export function siteTitle(a: {
  name?: string | null;
  sectorName?: string | null;
  isCombinedDevelopment?: boolean;
  groupSize?: number | null;
}): string {
  const sector = a.sectorName ?? "";
  if (a.isCombinedDevelopment) return `${sector} 합필 ${a.groupSize ?? ""}필지`.trim();
  const name = (a.name ?? "").trim();
  if (!name) return sector || "(이름 없음)";
  return sector && !name.includes(sector) ? `${sector} ${name}` : name;
}
