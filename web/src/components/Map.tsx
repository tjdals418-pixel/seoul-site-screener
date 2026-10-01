"use client";

import { useEffect, useRef, useState } from "react";
import mapboxgl, { LngLatLike } from "mapbox-gl";
import {
  fetchArticle,
  fetchGuBoundaries,
  fetchSubwayLines,
  fetchSubwayStations,
  type FilterParams,
} from "@/lib/api";
import { useArticles } from "@/lib/articles-context";
import { CAP_BANDS, capColor, siteTitle } from "@/lib/dev-class";

mapboxgl.accessToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || "";

const SEOUL_CENTER: LngLatLike = [126.99, 37.55];
const SEOUL_ZOOM = 11;

interface Props {
  filters: FilterParams;
  onSelect: (aid: string | null) => void;
  selectedAid: string | null;
}

export default function Map({ filters, onSelect, selectedAid }: Props) {
  // ArticlesContext에서 list 받음 — page.tsx Provider가 filters/sim/use 기준 1회 fetch
  const { list: articleList, loading: listLoading, error: listError, use } = useArticles();
  const containerRef = useRef<HTMLDivElement>(null);
  const tokenMissing = !mapboxgl.accessToken;
  // 초기화 effect가 onSelect 변경에 재실행되지 않도록 최신 콜백을 ref로 보관
  const onSelectRef = useRef(onSelect);
  useEffect(() => { onSelectRef.current = onSelect; }, [onSelect]);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<{ articles: number; groups: number } | null>(
    null
  );

  // 1) 지도 초기화 + 자치구 layer 한 번만
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    if (!mapboxgl.accessToken) return;  // tokenMissing으로 안내 표시

    const m = new mapboxgl.Map({
      container: containerRef.current,
      // light-v11 — 지적도 톤의 밝은 무채색 베이스 (custom layer 색이 잘 보임)
      style: "mapbox://styles/mapbox/light-v11",
      center: SEOUL_CENTER,
      zoom: SEOUL_ZOOM,
      attributionControl: false,
    });
    m.addControl(new mapboxgl.NavigationControl({ showCompass: false }), "top-right");
    m.addControl(new mapboxgl.ScaleControl({ unit: "metric" }), "bottom-left");
    m.addControl(new mapboxgl.AttributionControl({ compact: true }));

    const onLoad = async () => {
      try {
        // ── 자치구 + 지하철 노선/역 병렬 fetch ──
        const [guData, subwayLines, subwayStations] = await Promise.all([
          fetchGuBoundaries(),
          fetchSubwayLines(),
          fetchSubwayStations(),
        ]);

        // ── 자치구 ──
        m.addSource("gu", { type: "geojson", data: guData as unknown as GeoJSON.FeatureCollection });
        // choropleth fill — 매물 수 단계 색 (article_count는 data useEffect에서 join)
        m.addLayer({
          id: "gu-fill",
          type: "fill",
          source: "gu",
          maxzoom: 13.5,                 // 줌인 시 사라짐 (시각 방해 X)
          paint: {
            "fill-color": [
              "step",
              ["coalesce", ["get", "article_count"], 0],
              // 0 매물도 거의 투명하지만 0이면 mapbox mousemove 못 잡음 → 0.001
              "rgba(18,26,33,0.001)",
              1, "rgba(18,26,33,0.025)",
              3, "rgba(18,26,33,0.045)",
              6, "rgba(18,26,33,0.07)",
              10, "rgba(18,26,33,0.095)",
              20, "rgba(18,26,33,0.12)",
            ],
            "fill-opacity": [
              "interpolate", ["linear"], ["zoom"],
              10, 1, 13, 0.7, 13.5, 0,
            ],
          },
        });
        m.addLayer({
          id: "gu-line",
          type: "line",
          source: "gu",
          paint: {
            "line-color": "rgba(18,26,33,0.35)",
            "line-width": 1,
            "line-dasharray": [3, 3],
          },
        });
        // 자치구 hover popup — 매물수 / 평균 Cap / 평균 매매가
        const guPopup = new mapboxgl.Popup({
          closeButton: false,
          closeOnClick: false,
          offset: 8,
          className: "gu-hover-popup",
        });
        m.on("mousemove", "gu-fill", (e) => {
          const f = e.features?.[0];
          if (!f) { guPopup.remove(); return; }
          const p = f.properties as {
            name?: string;
            article_count?: number;
            avg_cap_pct?: number | null;
            avg_price_eok?: number | null;
          };
          if (!p.name) return;
          const cap = p.avg_cap_pct != null ? `${p.avg_cap_pct.toFixed(2)}%` : "—";
          const price = p.avg_price_eok != null ? `${p.avg_price_eok.toFixed(0)}억` : "—";
          guPopup
            .setLngLat(e.lngLat)
            .setHTML(
              `<div style="font-size:12px;line-height:1.5;color:#121a21">
                <div style="font-weight:600;margin-bottom:2px">${p.name}</div>
                <div style="color:#5d6a75;font-size:11px">
                  후보 <b style="color:#121a21">${p.article_count ?? 0}</b>건 ·
                  평균 Cap <b style="color:#2e7d4f">${cap}</b><br>
                  평균 매매가 <b style="color:#121a21">${price}</b>
                </div>
              </div>`
            )
            .addTo(m);
        });
        m.on("mouseleave", "gu-fill", () => guPopup.remove());

        // ── 지하철 노선 + 역 ──
        m.addSource("subway-lines", {
          type: "geojson",
          data: subwayLines as unknown as GeoJSON.FeatureCollection,
        });
        m.addLayer({
          id: "subway-line",
          type: "line",
          source: "subway-lines",
          minzoom: 10,
          paint: {
            "line-color": ["get", "color"],
            "line-width": [
              "interpolate", ["linear"], ["zoom"],
              10, 1.5, 14, 3, 17, 4.5,
            ],
            "line-opacity": 0.55,
          },
          layout: { "line-cap": "round", "line-join": "round" },
        });

        m.addSource("subway-stations", {
          type: "geojson",
          data: subwayStations as unknown as GeoJSON.FeatureCollection,
        });
        // 카카오맵 스타일: 흰색 동그라미 + 강한 cyan 외곽선 + "OO역" 라벨
        m.addLayer({
          id: "subway-station-dot",
          type: "circle",
          source: "subway-stations",
          minzoom: 11.5,
          paint: {
            "circle-radius": [
              "interpolate", ["linear"], ["zoom"],
              11.5, 3, 14, 5, 17, 8,
            ],
            "circle-color": "#ffffff",
            "circle-stroke-color": "#5d6a75",
            "circle-stroke-width": [
              "interpolate", ["linear"], ["zoom"],
              11.5, 1.5, 14, 2, 17, 2.5,
            ],
          },
        });
        m.addLayer({
          id: "subway-station-label",
          type: "symbol",
          source: "subway-stations",
          minzoom: 13,
          layout: {
            "text-field": ["concat", ["get", "name"], "역"],
            "text-size": [
              "interpolate", ["linear"], ["zoom"],
              13, 10, 15, 12.5, 17, 14,
            ],
            "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
            "text-offset": [0, 1.1],
            "text-anchor": "top",
            "text-allow-overlap": false,
            "text-padding": 2,
          },
          paint: {
            // 흰색 텍스트 + 두꺼운 검정 halo로 카카오맵 '흰 박스' 느낌
            "text-color": "#2d3943",
            "text-halo-color": "rgba(255,255,255,0.95)",
            "text-halo-width": 2,
            "text-halo-blur": 0.5,
          },
        });

        // 필지 polygon source (먼저 add — 아래쪽 layer가 z-order 낮음)
        m.addSource("parcels", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        // ── disco.re 스타일: 일반 필지는 살짝, 선택은 cyan dashed로 강조 ──
        m.addLayer({
          id: "parcels-fill",
          type: "fill",
          source: "parcels",
          minzoom: 12,
          paint: {
            "fill-color": ["get", "color"],
            "fill-opacity": [
              "case",
              ["==", ["get", "selected"], 1], 0.55,
              ["==", ["get", "isMember"], 1], 0.38,
              0.22,
            ],
          },
        });
        // 3D fill-extrusion — 개발 가능 연면적을 polygon 높이로 시각화.
        // 모든 매물 항상 띄우면 산만 + 무거우니 minzoom 15 + selected/멤버만.
        m.addLayer({
          id: "parcels-extrusion",
          type: "fill-extrusion",
          source: "parcels",
          minzoom: 15,
          filter: ["any",
            ["==", ["get", "selected"], 1],
            ["==", ["get", "isMember"], 1],
          ],
          paint: {
            "fill-extrusion-color": ["get", "color"],
            "fill-extrusion-height": [
              "interpolate", ["linear"], ["zoom"],
              15, ["*", ["coalesce", ["get", "devTotalPyeong"], 0], 0.04],
              18, ["*", ["coalesce", ["get", "devTotalPyeong"], 0], 0.1],
            ],
            "fill-extrusion-base": 0,
            "fill-extrusion-opacity": 0.55,
          },
        });
        // 베이스 라인 (모든 필지) — 등급별 색깔 + solid + 멤버는 두껍게
        m.addLayer({
          id: "parcels-line",
          type: "line",
          source: "parcels",
          minzoom: 12,
          filter: ["!=", ["get", "selected"], 1],
          paint: {
            "line-color": ["get", "color"],
            "line-width": [
              "case",
              ["==", ["get", "isMember"], 1], 2.6,   // 통합개발 멤버 강조
              1.8,
            ],
            "line-opacity": [
              "case",
              ["==", ["get", "isMember"], 1], 1.0,
              0.85,
            ],
          },
        });
        // 선택된 필지 — disco 시그니처 cyan dashed
        m.addLayer({
          id: "parcels-line-selected",
          type: "line",
          source: "parcels",
          minzoom: 11,
          filter: ["==", ["get", "selected"], 1],
          paint: {
            "line-color": "#1b5e8c",         // accent
            "line-width": 3,
            "line-dasharray": [2, 1.5],
            "line-opacity": 1,
          },
        });

        // 그룹 chain (그룹 중심 → 멤버 좌표 path)
        m.addSource("chains", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        m.addLayer({
          id: "chains-line",
          type: "line",
          source: "chains",
          paint: {
            "line-color": ["get", "color"],
            "line-width": 3.5,
            "line-dasharray": [2, 1.5],
            "line-opacity": 0.85,
          },
        });

        // 매물 마커 source (z-order 가장 위)
        // promoteId — selectedAid 변경 시 feature-state로 highlight (setData 없이).
        m.addSource("articles", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
          promoteId: "articleNo",
        });
        // 멤버 source — cluster 안 함 (숫자 묶음 너무 번잡). 줌 13.5+에서만 표시.
        m.addSource("articles-members", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
          promoteId: "articleNo",
        });
        // 단일 + 통합그룹 — 크게
        m.addLayer({
          id: "articles-circle",
          type: "circle",
          source: "articles",
          filter: ["!=", ["get", "isMember"], 1],
          paint: {
            "circle-radius": [
              "interpolate",
              ["linear"],
              ["zoom"],
              // 취득 Cap 4% 미만(low=1)은 작게 — 사업성 있는 부지가 먼저 눈에 띄도록
              10, ["case", ["==", ["get", "low"], 1], 2.5, ["==", ["get", "isGroup"], 1], 6, 4.5],
              14, ["case", ["==", ["get", "low"], 1], 4.5, ["==", ["get", "isGroup"], 1], 11, 7.5],
              17, ["case", ["==", ["get", "low"], 1], 6, ["==", ["get", "isGroup"], 1], 14, 9],
            ],
            "circle-color": ["get", "color"],
            "circle-stroke-width": [
              "case",
              ["boolean", ["feature-state", "selected"], false], 4,
              ["==", ["get", "low"], 1], 1,
              2,
            ],
            "circle-stroke-color": [
              "case",
              ["boolean", ["feature-state", "selected"], false], "#121a21",
              ["==", ["get", "isNew"], 1], "#2e7d4f",       // NEW = green ring
              "#ffffff",
            ],
            "circle-opacity": ["case", ["==", ["get", "low"], 1], 0.7, 0.95],
          },
        });

        // 그룹 멤버 — 작은 보조 마커. 줌 13.5+에서만 (산만함 방지).
        m.addLayer({
          id: "articles-member-circle",
          type: "circle",
          source: "articles-members",
          minzoom: 13.5,
          paint: {
            "circle-radius": [
              "interpolate", ["linear"], ["zoom"],
              13.5, 2.5, 16, 4, 18, 5.5,
            ],
            "circle-color": ["get", "color"],
            "circle-stroke-width": [
              "case",
              ["boolean", ["feature-state", "selected"], false], 2.5,
              1.2,
            ],
            "circle-stroke-color": [
              "case",
              ["boolean", ["feature-state", "selected"], false], "#121a21",
              "#ffffff",
            ],
            "circle-opacity": 0.9,
          },
        });

        const handleArticleClick = (e: mapboxgl.MapMouseEvent & { features?: mapboxgl.MapboxGeoJSONFeature[] }) => {
          const f = e.features?.[0];
          if (!f) return;
          const aid = (f.properties as { articleNo?: string })?.articleNo;
          if (aid) onSelectRef.current(aid);
        };

        // ── hover popup ──
        const hoverPopup = new mapboxgl.Popup({
          closeButton: false,
          closeOnClick: false,
          offset: 12,
          className: "article-hover-popup",
        });
        const showPopup = (e: mapboxgl.MapMouseEvent & { features?: mapboxgl.MapboxGeoJSONFeature[] }) => {
          const f = e.features?.[0];
          if (!f || f.geometry.type !== "Point") return;
          m.getCanvas().style.cursor = "pointer";
          const p = f.properties as {
            articleNo?: string;
            name?: string;
            devClass?: string;
            capRate?: number | null;
            color?: string;
            isGroup?: number;
            isMember?: number;
          };
          const coords = (f.geometry as GeoJSON.Point).coordinates as [number, number];
          const isGroup = p.isGroup === 1;
          const isMember = p.isMember === 1;
          const cap = p.capRate ?? null;
          const tag = isGroup ? "통합" : isMember ? "멤버" : "단일";
          const grade = p.devClass && p.devClass !== "—" ? p.devClass : "";
          hoverPopup
            .setLngLat(coords)
            .setHTML(
              `<div style="font-size:12px;line-height:1.45;color:#121a21">
                <div style="display:flex;align-items:center;gap:4px;margin-bottom:2px">
                  <span style="width:8px;height:8px;border-radius:50%;background:${p.color || "#52525b"};display:inline-block"></span>
                  <b>${(p.name || "(이름없음)").slice(0, 18)}</b>
                </div>
                <div style="color:#5d6a75;font-size:11px">
                  ${tag}${grade ? ` · ${grade}` : ""}${cap != null ? ` · Cap ${(cap * 100).toFixed(1)}%` : ""}
                </div>
              </div>`
            )
            .addTo(m);
        };
        const hidePopup = () => {
          m.getCanvas().style.cursor = "";
          hoverPopup.remove();
        };
        for (const layerId of ["articles-circle", "articles-member-circle"]) {
          m.on("click", layerId, handleArticleClick);
          m.on("mouseenter", layerId, showPopup);
          m.on("mousemove", layerId, showPopup);
          m.on("mouseleave", layerId, hidePopup);
        }

        setLoaded(true);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(`초기화 실패: ${msg}`);
      }
    };
    // mapbox-gl v3 Standard dark 스타일은 tile 종속이 다른지 `load` 이벤트가
    // 안 fire됨. `style.load`로 setup해도 sources/layers 등록은 충분.
    if (m.isStyleLoaded()) {
      onLoad();
    } else {
      m.once("style.load", onLoad);
    }

    mapRef.current = m;
    return () => {
      m.remove();
      mapRef.current = null;
      setLoaded(false);
    };
  }, []);

  // 2a) articleList / 카테고리 변경 → 무거운 source 갱신 (markers / members / chains / gu).
  //     selectedAid에 의존하지 않음 → 매물 클릭 시 이 effect는 재실행 안 됨.
  //     선택 highlight는 feature-state로 분리 (effect 2c). gu 통계 join 포함.
  const categoriesKey = (filters.categories ?? ["단일", "통합그룹"]).join(",");
  useEffect(() => {
    if (!loaded) return;
    const m = mapRef.current;
    if (!m) return;
    const src = m.getSource("articles") as mapboxgl.GeoJSONSource | undefined;
    if (!src) return;

    const list = articleList;
    const visibleCats = categoriesKey.split(",").filter(Boolean);

    // 그룹 색깔 매핑 (멤버 마커 색)
    const groupColorMap: Record<string, string> = {};
    for (const a of list.articles) {
      if (a.isCombinedDevelopment) {
        groupColorMap[a.articleNo] = capColor(a.capRate);
      }
    }

    // ── point markers (단일 + 통합그룹 + 그룹멤버) ──
    const pointFeatures: GeoJSON.Feature[] = list.articles
      .filter((a) => {
        if (!a.latitude || !a.longitude) return false;
        const cat = a.isCombinedDevelopment
          ? "통합그룹"
          : a.partOfGroup ? "그룹멤버" : "단일";
        if (cat === "그룹멤버") return true; // 항상 포함
        return visibleCats.includes(cat);
      })
      .map((a) => {
        const isMember = !!a.partOfGroup && !a.isCombinedDevelopment;
        let color = capColor(a.capRate);
        if (isMember && a.partOfGroup) {
          const parentColor = groupColorMap[a.partOfGroup];
          if (parentColor) color = parentColor;
        }
        return {
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: [a.longitude!, a.latitude!] },
          properties: {
            articleNo: a.articleNo,
            name: siteTitle(a),
            devClass: a.devClass || "—",
            capRate: a.capRate ?? null,
            isGroup: a.isCombinedDevelopment ? 1 : 0,
            isMember: isMember ? 1 : 0,
            color,
            isNew: a.isNew ? 1 : 0,
            low: (a.capRate ?? 0) < 0.04 ? 1 : 0,
            priceChangePct: a.priceChangePct ?? null,
          },
        };
      });

    // ── 그룹 chain — 방사형(spoke): 중심 → 각 멤버 좌표 line ──
    const chainFeatures: GeoJSON.Feature[] = [];
    for (const a of list.articles) {
      if (!a.isCombinedDevelopment) continue;
      if (!a.latitude || !a.longitude) continue;
      const center: [number, number] = [a.longitude, a.latitude];
      const groupColor = capColor(a.capRate);
      for (const md of (a.groupMembersDetail ?? []) as Array<{ latitude?: number; longitude?: number }>) {
        if (!md.latitude || !md.longitude) continue;
        chainFeatures.push({
          type: "Feature",
          geometry: { type: "LineString", coordinates: [center, [Number(md.longitude), Number(md.latitude)]] },
          properties: { articleNo: a.articleNo, color: groupColor },
        });
      }
    }

    const nonMembers = pointFeatures
      .filter((f) => f.properties?.isMember !== 1)
      .sort((x, y) => (x.properties?.capRate ?? 0) - (y.properties?.capRate ?? 0));
    const memberFeatures = pointFeatures.filter((f) => f.properties?.isMember === 1);
    src.setData({ type: "FeatureCollection", features: nonMembers });
    (m.getSource("articles-members") as mapboxgl.GeoJSONSource | undefined)
      ?.setData({ type: "FeatureCollection", features: memberFeatures });
    (m.getSource("chains") as mapboxgl.GeoJSONSource | undefined)
      ?.setData({ type: "FeatureCollection", features: chainFeatures });

    // 그룹멤버는 보조 마커라 후보 수에서 제외 (단일 + 통합그룹 = 실제 개발 후보)
    setStats({
      articles: nonMembers.length,
      groups: nonMembers.filter((f) => f.properties?.isGroup === 1).length,
    });

    // ── gu 통계 join ──
    const guStats: Record<string, { count: number; capSum: number; capN: number; priceSum: number; priceN: number }> = {};
    for (const a of list.articles) {
      if (a.partOfGroup && !a.isCombinedDevelopment) continue;
      const gu = a.divisionName;
      if (!gu) continue;
      const s = guStats[gu] ?? (guStats[gu] = { count: 0, capSum: 0, capN: 0, priceSum: 0, priceN: 0 });
      s.count++;
      if (a.capRate != null) { s.capSum += a.capRate; s.capN++; }
      if (a.dealPrice != null) { s.priceSum += a.dealPrice; s.priceN++; }
    }
    const guSrc = m.getSource("gu") as mapboxgl.GeoJSONSource | undefined;
    if (guSrc) {
      const cur = (guSrc as unknown as { _data?: GeoJSON.FeatureCollection })._data;
      if (cur?.features) {
        guSrc.setData({
          type: "FeatureCollection",
          features: cur.features.map((f) => {
            const name = (f.properties as { name?: string })?.name ?? "";
            const s = guStats[name];
            return {
              ...f,
              properties: {
                ...(f.properties ?? {}),
                article_count: s?.count ?? 0,
                avg_cap_pct: s && s.capN ? (s.capSum / s.capN) * 100 : null,
                avg_price_eok: s && s.priceN ? s.priceSum / s.priceN / 10000 : null,
              },
            };
          }),
        });
      }
    }
  }, [loaded, articleList, categoriesKey]);

  // 2b) parcels(필지) — articleList + selectedAid 의존. 선택 그룹 멤버 polygon만
  //     그려서 renderer 부담 최소화 + 선택 필지 cyan outline.
  useEffect(() => {
    if (!loaded) return;
    const m = mapRef.current;
    if (!m) return;
    const parcelsSrc = m.getSource("parcels") as mapboxgl.GeoJSONSource | undefined;
    if (!parcelsSrc) return;

    const list = articleList;
    const groupColorMap: Record<string, string> = {};
    for (const a of list.articles) {
      if (a.isCombinedDevelopment) {
        groupColorMap[a.articleNo] = capColor(a.capRate);
      }
    }

    const polygonFeatures: GeoJSON.Feature[] = [];
    for (const a of list.articles) {
      const geom = a.parcelPolygon;
      if (!geom) continue;
      if (a.isCombinedDevelopment) continue; // 그룹 자체엔 polygon 없음
      const isMember = !!a.partOfGroup;
      let color = capColor(a.capRate);
      if (isMember) {
        // 선택된 그룹의 멤버 polygon만 (3000+ 전부 그리면 무거움)
        if (a.partOfGroup !== selectedAid) continue;
        const groupColor = groupColorMap[a.partOfGroup!];
        if (groupColor) color = groupColor;
      }
      const isSelected =
        a.articleNo === selectedAid ||
        (isMember && a.partOfGroup === selectedAid);
      polygonFeatures.push({
        type: "Feature",
        geometry: geom as unknown as GeoJSON.Geometry,
        properties: {
          articleNo: a.articleNo,
          color,
          isMember: isMember ? 1 : 0,
          selected: isSelected ? 1 : 0,
          devTotalPyeong: a.devTotalPyeong ?? 0,
        },
      });
    }
    parcelsSrc.setData({ type: "FeatureCollection", features: polygonFeatures });
  }, [loaded, articleList, selectedAid]);

  // 2c) 마커 선택 highlight — feature-state로 setData 없이 갱신 (가장 가벼움).
  useEffect(() => {
    if (!loaded) return;
    const m = mapRef.current;
    if (!m) return;
    // 이전 선택 state 전부 클리어 후 새 선택만 set
    try { m.removeFeatureState({ source: "articles" }); } catch { /* source 미준비 */ }
    try { m.removeFeatureState({ source: "articles-members" }); } catch { /* */ }
    if (selectedAid) {
      // 단일/통합은 articles, 멤버는 articles-members — 양쪽 set (없는 id는 무해)
      try { m.setFeatureState({ source: "articles", id: selectedAid }, { selected: true }); } catch { /* */ }
      try { m.setFeatureState({ source: "articles-members", id: selectedAid }, { selected: true }); } catch { /* */ }
    }
  }, [loaded, selectedAid, articleList]);

  // 선택 해제 → 모바일 시트용으로 줬던 padding 원복
  useEffect(() => {
    if (!loaded || selectedAid) return;
    mapRef.current?.easeTo({ padding: { top: 0, bottom: 0, left: 0, right: 0 }, duration: 300 });
  }, [loaded, selectedAid]);

  // 3) selectedAid 변경 → fly-to. 우선 source features에서 찾고,
  //    줌아웃 상태(deep link 진입 등)면 API에서 직접 좌표 fetch.
  useEffect(() => {
    if (!loaded || !selectedAid) return;
    const m = mapRef.current;
    if (!m) return;

    const flyTo = (lon: number, lat: number) => {
      // 모바일은 하단 시트(최대 62vh)가 지도 아래쪽을 덮으므로 보이는 영역 가운데로 이동
      const mobile = window.innerWidth < 768;
      const sheet = mobile ? Math.round(window.innerHeight * 0.55) : 0;
      m.flyTo({
        center: [lon, lat],
        zoom: Math.max(m.getZoom(), mobile ? 16.5 : 17),  // polygon/멤버 마커가 또렷이
        padding: { top: 0, bottom: sheet, left: 0, right: 0 },
        duration: 700,
      });
      // 도착 직후 pulse marker — 어디로 갔는지 시각 헬프
      const el = document.createElement("div");
      el.style.cssText =
        "width:20px;height:20px;border-radius:50%;" +
        "background:rgba(27,94,140,0.25);border:2px solid #1b5e8c;" +
        "animation: mb-marker-pulse 1.4s ease-out 2;pointer-events:none";
      const pulse = new mapboxgl.Marker({ element: el, anchor: "center" })
        .setLngLat([lon, lat])
        .addTo(m);
      setTimeout(() => pulse.remove(), 3000);
    };

    // 1순위: 이미 렌더된 features에서 찾기 (빠름)
    const features = m.queryRenderedFeatures({
      layers: ["articles-circle", "articles-member-circle"],
    });
    const target = features.find(
      (f) => (f.properties as { articleNo?: string })?.articleNo === selectedAid
    );
    if (target && target.geometry.type === "Point") {
      const [lon, lat] = (target.geometry as GeoJSON.Point).coordinates;
      flyTo(lon, lat);
      return;
    }

    // 2순위: API에서 article fetch
    fetchArticle(selectedAid, use)
      .then((a) => {
        if (a.latitude && a.longitude) flyTo(a.longitude, a.latitude);
      })
      .catch(() => null);  // 목록에 없는 매물 — DetailPanel이 안내 표시
  }, [loaded, selectedAid, use]);

  return (
    <div className="relative w-full h-full">
      <div ref={containerRef} className="w-full h-full" />

      {!loaded && !error && !tokenMissing && (
        <div className="absolute inset-0 flex items-center justify-center bg-paper">
          <span className="text-muted text-sm">지도 불러오는 중…</span>
        </div>
      )}
      {(error || listError || tokenMissing) && (
        <div className="absolute inset-0 flex items-center justify-center bg-paper/80 p-4">
          <div className="bg-surface border border-bad/40 px-4 py-3 rounded text-bad text-sm max-w-md">
            {tokenMissing
              ? "Mapbox 토큰이 설정되지 않았습니다 (NEXT_PUBLIC_MAPBOX_TOKEN)."
              : error ?? "매물 데이터를 불러오지 못했습니다."}
            <div className="mt-2 text-xs text-muted">
              잠시 후 새로고침해 주세요. (API 서버 응답 없음)
            </div>
          </div>
        </div>
      )}
      {loaded && listLoading && !listError && (
        <div
          className="absolute top-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded text-xs text-ink-2 bg-surface border border-line-strong shadow-sm"
        >
          매물 계산 중…
        </div>
      )}

      {/* 우측 하단 범례 */}
      <div
        className="absolute bottom-8 right-2 md:right-3 px-3 py-2.5 rounded bg-surface/95 border border-line-strong shadow-sm"
      >
        <div className="text-[12px] text-muted font-semibold mb-1.5">
          취득 Cap <span className="font-normal text-faint">NOI ÷ 총사업비</span>
        </div>
        {CAP_BANDS.map((b) => (
          <div key={b.label} className="flex items-center gap-2 my-0.5">
            <span
              className="w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{
                background: b.color,
                border: "1.5px solid #fff",
                boxShadow: "0 0 0 1px rgba(18,26,33,0.25)",
              }}
            />
            <span className="num text-[13px] text-ink-2">{b.label}</span>
          </div>
        ))}
        {stats && (
          <div
            className="mt-2 pt-2 border-t border-line text-[12px] text-muted"
          >
            후보 <b className="num text-ink">{stats.articles}</b>건 · 합필{" "}
            <b className="num text-ink">{stats.groups}</b>
          </div>
        )}
      </div>
    </div>
  );
}
