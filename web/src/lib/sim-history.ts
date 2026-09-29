"use client";

/**
 * 시뮬 가정값 history — 브라우저 localStorage에만 저장.
 * 사용자가 SimForm에서 변경한 값 저장/복원/삭제.
 */
import { useCallback } from "react";
import type { SimAssumptions } from "@/components/SimForm";
import { useStoredJSON } from "@/lib/local-store";

const KEY = "naver-crawler-sim-history";
const MAX_ENTRIES = 20;

export interface SimEntry {
  id: string;           // unix ms
  timestamp: number;
  label?: string;
  sim: SimAssumptions;
}

const EMPTY: SimEntry[] = [];
const parse = (v: unknown): SimEntry[] => (Array.isArray(v) ? (v as SimEntry[]) : EMPTY);

export function useSimHistory() {
  const [entries, setEntries] = useStoredJSON(KEY, EMPTY, parse);

  const save = useCallback(
    (sim: SimAssumptions, label?: string) => {
      const now = Date.now();
      const entry: SimEntry = { id: String(now), timestamp: now, label, sim };
      setEntries((prev) => [entry, ...prev].slice(0, MAX_ENTRIES));
    },
    [setEntries],
  );

  const remove = useCallback(
    (id: string) => setEntries((prev) => prev.filter((e) => e.id !== id)),
    [setEntries],
  );

  const clear = useCallback(() => setEntries([]), [setEntries]);

  return { entries, save, remove, clear };
}
