"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchArticle, type Article } from "@/lib/api";
import { Search, Star } from "lucide-react";
import { useBookmarks } from "@/lib/bookmarks";
import { useArticles } from "@/lib/articles-context";
import { capColor, siteTitle } from "@/lib/dev-class";


interface Props {
  onNavigate: (aid: string) => void;
}

export default function SearchBookmark({ onNavigate }: Props) {
  const { ids: bookmarkIds, has, toggle, clear } = useBookmarks();
  const [query, setQuery] = useState("");
  const [fetchedBookmarks, setBookmarks] = useState<Article[]>([]);
  const [openBookmarks, setOpenBookmarks] = useState(false);
  // 검색 후보 — 필터와 무관한 전체 목록 (현재 용도·가정값 반영), 합필 구성 필지 제외
  const { use, all } = useArticles();
  const allArticles = useMemo(
    () => all.filter((a) => !a.partOfGroup || a.isCombinedDevelopment),
    [all],
  );

  // 북마크 — 현재 목록 값을 우선 쓰고, 목록에 없는 매물만 개별 조회 결과로 채움
  const bookmarks = useMemo(() => {
    const byId = new Map(all.map((a) => [a.articleNo, a]));
    const fetchedById = new Map(fetchedBookmarks.map((a) => [a.articleNo, a]));
    return bookmarkIds
      .map((id) => byId.get(id) ?? fetchedById.get(id))
      .filter((a): a is Article => !!a);
  }, [all, fetchedBookmarks, bookmarkIds]);

  // 북마크 article 데이터 (lazy fetch)
  useEffect(() => {
    if (bookmarkIds.length === 0) return;
    let cancelled = false;
    Promise.all(
      bookmarkIds.map((id) => fetchArticle(id, use).catch(() => null))
    ).then((rs) => {
      if (!cancelled) {
        setBookmarks(rs.filter((x): x is Article => !!x));
      }
    });
    return () => { cancelled = true; };
  }, [bookmarkIds, use]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || q.length < 2) return [];
    return allArticles
      .filter((a) => {
        const name = (a.name || "").toLowerCase();
        const addr = (a.regRoadAddress || "").toLowerCase();
        const div = (a.divisionName || "").toLowerCase();
        const sec = (a.sectorName || "").toLowerCase();
        return name.includes(q) || addr.includes(q) || div.includes(q) || sec.includes(q);
      })
      .slice(0, 12);
  }, [query, allArticles]);

  return (
    <div className="mb-4">
      {/* 검색 input */}
      <div className="mb-2 relative">
        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" aria-hidden="true" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="매물명·주소 검색"
          aria-label="매물명·주소 검색"
          className="w-full h-9 pl-8 pr-8 rounded text-[13px] text-ink bg-surface border border-line focus:border-accent outline-none placeholder:text-faint"
        />
        {query && (
          <button
            onClick={() => setQuery("")}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted hover:text-ink text-xs"
            aria-label="검색어 지우기"
          >
            ✕
          </button>
        )}
      </div>

      {/* 검색 결과 */}
      {results.length > 0 && (
        <div
          className="rounded overflow-hidden mb-3"
          style={{
            background: "var(--dash-panel-strong)",
            border: "1px solid var(--dash-border)",
          }}
        >
          {results.map((a) => (
            <ResultRow
              key={a.articleNo}
              article={a}
              isBookmarked={has(a.articleNo)}
              onSelect={() => { onNavigate(a.articleNo); setQuery(""); }}
              onToggleBookmark={() => toggle(a.articleNo)}
            />
          ))}
        </div>
      )}
      {query.trim().length >= 2 && results.length === 0 && (
        <div className="text-[12.5px] text-muted px-2 py-1.5 mb-3 leading-relaxed">
          &quot;{query}&quot;에 해당하는 매물 없음.
          <br />
          <span className="text-faint text-[12px]">
            자치구 이름 / 동 / 도로명 / 매물명으로 검색하거나
            인근 자치구를 시도해보세요.
          </span>
        </div>
      )}

      {/* 북마크 list */}
      <button
        onClick={() => setOpenBookmarks(!openBookmarks)}
        className="w-full flex items-center justify-between px-3 h-9 rounded text-[13px] font-medium text-ink-2 hover:bg-sunken transition"
        style={{
          background: openBookmarks ? "var(--dash-panel)" : "transparent",
          border: "1px solid var(--dash-border)",
        }}
      >
        <span>
          북마크{" "}
          {bookmarkIds.length > 0 && (
            <span className="ml-1 text-[12px] px-1.5 py-0.5 rounded bg-accent-soft text-accent">
              {bookmarkIds.length}
            </span>
          )}
        </span>
        <span className="text-muted">{openBookmarks ? "▾" : "▸"}</span>
      </button>

      {openBookmarks && (
        <div
          className="mt-1 rounded overflow-hidden"
          style={{
            background: "var(--dash-panel)",
            border: "1px solid var(--dash-border)",
          }}
        >
          {bookmarks.length === 0 ? (
            <div className="text-[12.5px] text-muted px-3 py-2">
              아직 북마크한 부지가 없어요. 상세 화면에서 추가하세요.
            </div>
          ) : (
            <>
              {bookmarks.map((a) => (
                <ResultRow
                  key={a.articleNo}
                  article={a}
                  isBookmarked
                  onSelect={() => onNavigate(a.articleNo)}
                  onToggleBookmark={() => toggle(a.articleNo)}
                />
              ))}
              <button
                onClick={() => {
                  if (confirm(`북마크 ${bookmarkIds.length}개 전체 삭제?`)) clear();
                }}
                className="w-full py-1.5 text-[12px] text-muted hover:text-bad transition border-t"
                style={{ borderColor: "var(--dash-border)" }}
              >
                전체 비우기
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function ResultRow({
  article,
  isBookmarked,
  onSelect,
  onToggleBookmark,
}: {
  article: Article;
  isBookmarked: boolean;
  onSelect: () => void;
  onToggleBookmark: () => void;
}) {
  const a = article;
  const color = capColor(a.capRate);
  const isGroup = !!a.isCombinedDevelopment;
  return (
    <div
      className="flex items-center gap-2 px-3 py-2 hover:bg-ink/[0.04] transition cursor-pointer"
      onClick={onSelect}
    >
      <span
        className="w-2 h-2 rounded-full flex-shrink-0"
        style={{ background: color }}
      />
      <div className="flex-1 min-w-0">
        <div className="text-[13px] text-ink-2 truncate">
          {siteTitle(a)}
          {isGroup && (
            <span className="ml-1.5 text-[10.5px] text-accent">통합</span>
          )}
        </div>
        <div className="text-[11px] text-muted truncate">
          {a.divisionName ?? ""} {a.sectorName ?? ""}
          {a.capRate != null && (
            <span className="ml-2 text-muted">Cap {(a.capRate * 100).toFixed(1)}%</span>
          )}
        </div>
      </div>
      <button
        onClick={(e) => { e.stopPropagation(); onToggleBookmark(); }}
        className="flex-shrink-0 p-1"
        title={isBookmarked ? "북마크 해제" : "북마크"}
        aria-pressed={isBookmarked}
      >
        <Star
          size={15}
          strokeWidth={1.75}
          className={isBookmarked ? "text-warn" : "text-faint hover:text-ink"}
          fill={isBookmarked ? "currentColor" : "none"}
        />
      </button>
    </div>
  );
}
