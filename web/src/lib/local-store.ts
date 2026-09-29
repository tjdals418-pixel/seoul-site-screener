"use client";

/**
 * localStorage JSON 값을 React state처럼 쓰는 hook (useSyncExternalStore 기반).
 *
 * - 서버 렌더/첫 hydration에서는 fallback을 쓰고, 이후 저장값으로 교체된다.
 * - 같은 탭의 다른 컴포넌트: CustomEvent로 즉시 동기화.
 *   다른 탭: 브라우저 storage 이벤트로 동기화.
 * - 저장소 접근이 막힌 환경(시크릿 창 등)에서도 fallback으로 정상 동작.
 */
import { useCallback, useSyncExternalStore } from "react";

const SAME_TAB_EVENT = "site-screener-storage";
const cache = new Map<string, { raw: string | null; value: unknown }>();

function readRaw(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function read<T>(key: string, fallback: T, parse: (v: unknown) => T): T {
  const raw = readRaw(key);
  const hit = cache.get(key);
  // 같은 raw 문자열이면 같은 객체를 돌려줘야 useSyncExternalStore가 무한 렌더하지 않음
  if (hit && hit.raw === raw) return hit.value as T;
  let value = fallback;
  if (raw) {
    try {
      value = parse(JSON.parse(raw));
    } catch {
      value = fallback;
    }
  }
  cache.set(key, { raw, value });
  return value;
}

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(SAME_TAB_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(SAME_TAB_EVENT, onChange);
  };
}

/** fallback과 parse는 module 상수로 넘길 것 (참조가 바뀌면 캐시가 무의미해짐). */
export function useStoredJSON<T>(
  key: string,
  fallback: T,
  parse: (v: unknown) => T,
): [T, (next: T | ((prev: T) => T)) => void] {
  const value = useSyncExternalStore(
    subscribe,
    () => read(key, fallback, parse),
    () => fallback,
  );

  const set = useCallback(
    (next: T | ((prev: T) => T)) => {
      const prev = read(key, fallback, parse);
      const v = typeof next === "function" ? (next as (p: T) => T)(prev) : next;
      try {
        window.localStorage.setItem(key, JSON.stringify(v));
      } catch {
        /* 용량 초과·차단 — 이번 세션 화면에서만 유지 */
        cache.set(key, { raw: readRaw(key), value: v });
      }
      window.dispatchEvent(new Event(SAME_TAB_EVENT));
    },
    [key, fallback, parse],
  );

  return [value, set];
}
