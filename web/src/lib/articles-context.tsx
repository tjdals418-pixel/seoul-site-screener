"use client";

/**
 * ArticlesContext — page.tsx scope에서 articles list를 fetch + provide.
 *
 * filters / sim / use 기준으로 1회 fetch → Map / DetailPanel / Ranking /
 * ComparisonTable이 공유. 시뮬 가정값이나 용도가 바뀌면 list가 교체되고,
 * lookup도 새 list 기준으로 바뀌어 DetailPanel이 최신 값을 다시 읽는다.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  applyFilterClient,
  fetchArticles,
  postSimulate,
  type Article,
  type ArticleList,
  type FilterParams,
} from "@/lib/api";
import type { DevUse } from "@/lib/dev-class";
import type { SimAssumptions } from "@/components/SimForm";

interface ArticlesContextValue {
  /** 필터 적용 목록 (그룹멤버 포함 — 지도 polygon용) */
  list: ArticleList;
  /** 필터·카테고리까지 적용한 개발 후보 (순위·요약·비교표 공용) */
  candidates: Article[];
  /** 필터 미적용 전체 (검색용, 현재 용도·가정값 반영) */
  all: Article[];
  loading: boolean;
  error: Error | null;
  use: DevUse;
  sim: SimAssumptions | null;
  /** in-list lookup. miss면 null. */
  lookup: (aid: string) => Article | null;
}

const EMPTY: ArticleList = { count: 0, articles: [] };

const ArticlesContext = createContext<ArticlesContextValue>({
  list: EMPTY,
  candidates: [],
  all: [],
  loading: false,
  error: null,
  use: "best",
  sim: null,
  lookup: () => null,
});

interface ProviderProps {
  filters: FilterParams;
  sim: SimAssumptions | null;
  use: DevUse;
  children: ReactNode;
}

/**
 * 항상 그룹멤버 카테고리도 포함해서 fetch (지도 polygon 그리기에 필요).
 * 사용자 카테고리 필터링은 consumer 측에서 수행 (Map의 visibleCats처럼).
 */
export function ArticlesProvider({ filters, sim, use, children }: ProviderProps) {
  // 용도·가정값 기준 전체 목록은 서버에서 한 번만 받고, 필터는 클라이언트에서
  // 즉시 적용 (필터 조작마다 네트워크 왕복 없음).
  const [full, setFull] = useState<{ key: string; data: ArticleList } | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const key = JSON.stringify({ sim, use });

  useEffect(() => {
    let cancelled = false;
    const req = sim === null
      ? fetchArticles({}, use)
      : postSimulate(sim as unknown as Record<string, unknown>, use);
    req
      .then((data) => {
        if (cancelled) return;
        setFull({ key, data });
        setError(null);
      })
      .catch((e) => { if (!cancelled) setError(e as Error); });
    return () => { cancelled = true; };
  }, [key, sim, use]);

  const loading = !error && full?.key !== key;

  // 그룹멤버 카테고리는 항상 포함 (지도 polygon용) — 카테고리는 consumer가 거름
  const list = useMemo(
    () => full
      ? applyFilterClient(full.data, { ...filters, categories: ["단일", "통합그룹", "그룹멤버"] })
      : EMPTY,
    [full, filters],
  );

  const candidates = useMemo(() => {
    const cats = filters.categories ?? [];
    return list.articles.filter((a) => {
      if (a.partOfGroup && !a.isCombinedDevelopment) return false;
      if (!cats.length) return true;
      return cats.includes(a.isCombinedDevelopment ? "통합그룹" : "단일");
    });
  }, [list, filters.categories]);

  const all = full?.data.articles ?? EMPTY.articles;

  const index = useMemo(() => {
    const m: Record<string, Article> = {};
    for (const a of list.articles) m[a.articleNo] = a;
    return m;
  }, [list]);

  const lookup = useCallback((aid: string) => index[aid] ?? null, [index]);

  const value = useMemo(
    () => ({ list, candidates, all, loading, error, use, sim, lookup }),
    [list, candidates, all, loading, error, use, sim, lookup]
  );

  return (
    <ArticlesContext.Provider value={value}>
      {children}
    </ArticlesContext.Provider>
  );
}

export function useArticles(): ArticlesContextValue {
  return useContext(ArticlesContext);
}
