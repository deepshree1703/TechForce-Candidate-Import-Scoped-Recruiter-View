// Two small hooks: a debounced value, and a loader that tracks loading / error / ready.
import { useEffect, useState } from "react";

import { describeError } from "./api";

/** What a request is doing right now. */
export type Load<T> = { state: "loading" } | { state: "error"; message: string } | { state: "ready"; data: T };

/** Return the value only after it has stopped changing for delayMs. */
export function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

/**
 * Run a request whenever key changes, and report its state.
 *
 * key must change whenever the request should change. A result for an older key is never
 * shown (the request is cancelled, and a result is used only if its key is the current one).
 */
export function useLoad<T>(fetcher: (signal: AbortSignal) => Promise<T>, key: string): Load<T> {
  const [result, setResult] = useState<{ key: string; load: Load<T> } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetcher(controller.signal)
      .then((data) => setResult({ key, load: { state: "ready", data } }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setResult({ key, load: { state: "error", message: describeError(error) } });
        }
      });
    return () => controller.abort();
    // Only key decides when to reload; fetcher is a new function on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return result !== null && result.key === key ? result.load : { state: "loading" };
}