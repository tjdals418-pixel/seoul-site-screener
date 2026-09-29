"use client";

/**
 * 북마크 — 브라우저 localStorage에만 저장 (서버·다른 기기와 공유되지 않음).
 * - "naver-crawler-bookmarks": articleNo[]
 * - "naver-crawler-bookmark-notes": Record<articleNo, {note, tag, updatedAt}>
 * 같은 탭의 여러 컴포넌트와 다른 탭 사이 동기화는 useStoredJSON이 처리.
 */
import { useCallback } from "react";
import { useStoredJSON } from "@/lib/local-store";

const KEY = "naver-crawler-bookmarks";
const NOTES_KEY = "naver-crawler-bookmark-notes";

export interface BookmarkNote {
  note: string;
  tag: string;             // "검토중" | "포기" | "실사예정" | (custom)
  updatedAt: number;
}

const EMPTY_IDS: string[] = [];
const EMPTY_NOTES: Record<string, BookmarkNote> = {};
const parseIds = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : EMPTY_IDS);
const parseNotes = (v: unknown): Record<string, BookmarkNote> =>
  typeof v === "object" && v != null && !Array.isArray(v)
    ? (v as Record<string, BookmarkNote>)
    : EMPTY_NOTES;

export function useBookmarks() {
  const [ids, setIds] = useStoredJSON(KEY, EMPTY_IDS, parseIds);
  const [notes, setNotes] = useStoredJSON(NOTES_KEY, EMPTY_NOTES, parseNotes);

  const toggle = useCallback(
    (aid: string) =>
      setIds((prev) => (prev.includes(aid) ? prev.filter((x) => x !== aid) : [...prev, aid])),
    [setIds],
  );

  const has = useCallback((aid: string) => ids.includes(aid), [ids]);

  const clear = useCallback(() => setIds([]), [setIds]);

  const getNote = useCallback(
    (aid: string): BookmarkNote | null => notes[aid] ?? null,
    [notes],
  );

  const saveNote = useCallback(
    (aid: string, note: string, tag: string) =>
      setNotes((prev) => {
        const next: Record<string, BookmarkNote> = { ...prev };
        if (!note && !tag) delete next[aid];
        else next[aid] = { note, tag, updatedAt: Date.now() };
        return next;
      }),
    [setNotes],
  );

  return { ids, toggle, has, clear, getNote, saveNote };
}

export const BOOKMARK_TAGS = ["검토중", "실사예정", "협상중", "포기"] as const;
