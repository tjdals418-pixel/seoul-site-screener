/**
 * 서울 주요 랜드마크 — 입지 평가 기준점.
 * 매물 좌표 → Haversine 거리 + 도보 시간 (4km/h ≈ 67m/min).
 */

export interface Landmark {
  name: string;
  lat: number;
  lon: number;
  category: "관광" | "업무" | "쇼핑" | "교통";
}

export const LANDMARKS: Landmark[] = [
  { name: "명동", lat: 37.5636, lon: 126.9826, category: "쇼핑" },
  { name: "광화문", lat: 37.5759, lon: 126.9769, category: "관광" },
  { name: "강남역", lat: 37.4979, lon: 127.0276, category: "교통" },
  { name: "홍대입구역", lat: 37.5572, lon: 126.9244, category: "쇼핑" },
  { name: "여의도", lat: 37.5219, lon: 126.9241, category: "업무" },
  { name: "잠실 (롯데월드타워)", lat: 37.5125, lon: 127.1025, category: "관광" },
  { name: "동대문 DDP", lat: 37.5663, lon: 127.0093, category: "쇼핑" },
  { name: "이태원", lat: 37.5345, lon: 126.9947, category: "관광" },
  { name: "서울역", lat: 37.5547, lon: 126.9706, category: "교통" },
  { name: "인천공항", lat: 37.4602, lon: 126.4407, category: "교통" },
];

/** Haversine distance — meters. */
export function distanceM(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

/** 4km/h ≈ 67m/min */
export function walkMin(distM: number): number {
  return Math.round(distM / 67);
}

export interface LandmarkDistance extends Landmark {
  distanceM: number;
  walkMin: number;
}

/**
 * 매물 좌표에서 가까운 랜드마크 N개 + 거리/도보시간.
 * 도보 30분 이내 + 차로 5km 이내 (인천공항 등은 차로) 추리고 최단순 정렬.
 */
export function nearestLandmarks(
  lat: number,
  lon: number,
  limit = 5
): LandmarkDistance[] {
  return LANDMARKS
    .map((lm) => {
      const d = distanceM(lat, lon, lm.lat, lm.lon);
      return { ...lm, distanceM: d, walkMin: walkMin(d) };
    })
    .sort((a, b) => a.distanceM - b.distanceM)
    .slice(0, limit);
}
