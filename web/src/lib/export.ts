/**
 * 매물 디테일 → CSV/JSON 다운로드.
 * 라이브러리 없이 native Blob + a.download.
 */
import type { Article } from "@/lib/api";
import { siteTitle } from "@/lib/dev-class";

const KOR_LABELS: Array<{ key: keyof Article; label: string; format?: (v: unknown) => string }> = [
  { key: "articleNo", label: "매물ID" },
  { key: "name", label: "매물명" },
  { key: "isCombinedDevelopment", label: "통합개발여부", format: (v) => (v ? "Y" : "N") },
  { key: "groupSize", label: "통합필지수" },
  { key: "groupMemberArticles", label: "통합멤버매물ID" },
  { key: "devUse", label: "개발용도", format: (v) => (v === "hotel" ? "호텔" : v === "office" ? "오피스" : "") },
  { key: "devClass", label: "등급·규모" },

  { key: "divisionName", label: "자치구" },
  { key: "sectorName", label: "동" },
  { key: "regRoadAddress", label: "도로명주소" },
  { key: "latitude", label: "위도" },
  { key: "longitude", label: "경도" },

  { key: "dealPrice", label: "매매가(만원)" },
  { key: "landSpace", label: "대지면적(㎡)" },
  { key: "landPyeong", label: "대지면적(평)" },
  { key: "landPerPyeongM", label: "토지평당가(백만원/평)" },

  { key: "regZoning", label: "용도지역" },
  { key: "maxFar", label: "용적률(%)" },

  { key: "capRate", label: "취득Cap(NOI/총사업비)", format: (v) => (v != null ? `${(Number(v) * 100).toFixed(2)}%` : "") },
  { key: "noiAnnualM", label: "NOI_연간(백만)" },
  { key: "hotelCapRate", label: "호텔_CapRate", format: (v) => (v != null ? `${(Number(v) * 100).toFixed(2)}%` : "") },
  { key: "officeCapRate", label: "오피스_CapRate", format: (v) => (v != null ? `${(Number(v) * 100).toFixed(2)}%` : "") },
  { key: "hotelGrade", label: "호텔등급" },
  { key: "officeClass", label: "오피스규모" },
  { key: "officeMarket", label: "오피스권역" },
  { key: "officeExclusivePyeong", label: "오피스전용면적(평)" },
  { key: "officeLeasablePyeong", label: "오피스임대면적(평)" },
  { key: "officeNoc10k", label: "NOC(만원/전용평/월)" },
  { key: "officeRevenueAnnualM", label: "오피스임대수입_연간(백만)" },
  { key: "officeOpexAnnualM", label: "오피스운용비용_연간(백만)" },
  { key: "devRoomCount", label: "객실수" },
  { key: "devTotalPyeong", label: "개발연면적(평)" },
  { key: "devExclusivePyeong", label: "전용면적(평)" },
  { key: "devRoomAreaSqm", label: "객실면적(㎡)" },

  { key: "adr10k", label: "ADR(만원/박)" },
  { key: "adrTier", label: "ADR_Tier" },
  { key: "adrMultiplier", label: "ADR_보정율" },
  { key: "occupancy", label: "Occupancy" },
  { key: "fnbRatio", label: "F&B_비율" },
  { key: "gopRatio", label: "GOP마진" },
  { key: "roomRevenueAnnualM", label: "객실매출_연간(백만)" },
  { key: "fnbRevenueAnnualM", label: "F&B매출_연간(백만)" },
  { key: "gopAnnualM", label: "GOP_연간(백만)" },

  { key: "costTotalM", label: "총사업비(백만)" },
  { key: "costPurchaseM", label: "토지비(백만)" },
  { key: "costConstructionM", label: "공사비(백만)" },
  { key: "costIncidentalM", label: "부대비(백만)" },
  { key: "costFinanceM", label: "금융비(백만)" },
  { key: "costPerRoomM", label: "객실당개발비(백만/실)" },
  { key: "costPerPyeongM", label: "평당개발비(백만/평)" },

  { key: "devJiguPrimaryName", label: "지구단위계획" },
  { key: "devNearestRailStation", label: "최근역" },
  { key: "devNearestRailDistanceM", label: "역까지거리(m)" },
  { key: "devNearestRailWalkMin", label: "역까지도보(분)" },
  { key: "devNearestRailOpenDate", label: "역_개통일" },
];

function escapeCSV(val: string): string {
  if (val.includes('"') || val.includes(",") || val.includes("\n")) {
    return `"${val.replace(/"/g, '""')}"`;
  }
  return val;
}

function formatValue(article: Article, def: typeof KOR_LABELS[0]): string {
  const v = article[def.key];
  if (v === null || v === undefined) return "";
  if (def.format) return def.format(v);
  return String(v);
}

export function articleToCSV(article: Article): string {
  // Excel 한글 호환 UTF-8 BOM
  const BOM = "﻿";
  const headers = KOR_LABELS.map((d) => escapeCSV(d.label)).join(",");
  const values = KOR_LABELS.map((d) => escapeCSV(formatValue(article, d))).join(",");
  return BOM + headers + "\n" + values + "\n";
}

export function downloadArticleCSV(article: Article): void {
  const csv = articleToCSV(article);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const safe = (siteTitle(article) || article.articleNo || "article")
    .replace(/[\\/:*?"<>|]/g, "_")
    .slice(0, 40);
  a.href = url;
  a.download = `${safe}_${article.articleNo}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/**
 * 여러 매물을 한 파일에 — 행=매물, 컬럼=지표. 비교 테이블용.
 * downloadArticleCSV를 N번 부르면 브라우저가 N개 다운로드 prompt를 띄움 →
 * 비교 컨텍스트엔 단일 통합 CSV가 적합.
 */
export function articlesToCSV(articles: Article[]): string {
  const BOM = "﻿";
  const headers = KOR_LABELS.map((d) => escapeCSV(d.label)).join(",");
  const rows = articles.map((a) =>
    KOR_LABELS.map((d) => escapeCSV(formatValue(a, d))).join(",")
  );
  return BOM + headers + "\n" + rows.join("\n") + "\n";
}

export function downloadArticlesCSV(articles: Article[], filename = "비교매물"): void {
  if (articles.length === 0) return;
  const csv = articlesToCSV(articles);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${filename}_${articles.length}건.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function downloadArticleJSON(article: Article): void {
  const blob = new Blob([JSON.stringify(article, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${article.articleNo}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
