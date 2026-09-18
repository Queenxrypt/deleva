import type { ReactNode } from "react";
import type { AsyncState } from "../api/useApi";

/** The one place loading/error rendering happens, so no page invents its own
 * blank screen, infinite spinner, or silent failure (see Phase 3 spec, Part
 * 4: "No blank screens. No fake success states. No fake loading forever."). */
export function AsyncBoundary<T>({
  state,
  render,
}: {
  state: AsyncState<T>;
  render: (data: T) => ReactNode;
}) {
  if (state.status === "loading") {
    return <p className="skeleton">Loading…</p>;
  }
  if (state.status === "error") {
    return (
      <div className="error-banner">
        Could not reach the DELEVA backend: {state.message}
        <div style={{ marginTop: 6, color: "var(--text-faint)" }}>
          Is the API running? See README for <code>uvicorn api.main:app</code>.
        </div>
      </div>
    );
  }
  return <>{render(state.data)}</>;
}
