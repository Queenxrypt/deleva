import { useEffect, useState, useCallback } from "react";

export type AsyncState<T> =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: T };

/** Shared fetch-state hook so every page handles loading/error/ready the
 * same honest way -- no page invents its own silent-failure or infinite
 * spinner behavior. */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []): AsyncState<T> & { reload: () => void } {
  const [state, setState] = useState<AsyncState<T>>({ status: "loading" });
  const [tick, setTick] = useState(0);

  const load = useCallback(() => {
    setState({ status: "loading" });
    fetcher()
      .then((data) => setState({ status: "ready", data }))
      .catch((err: unknown) =>
        setState({ status: "error", message: err instanceof Error ? err.message : "Request failed" })
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, tick]);

  return { ...state, reload: () => setTick((t) => t + 1) };
}
