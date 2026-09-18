import type { ActivitySource } from "../api/client";

/** The one, consistent way any record on screen declares its provenance:
 * live, demo, or manual execution. Never silently mixed -- every event that
 * shows chain-derived data carries one of these. The backend's own
 * "historical_proof" source is presented here as "Manual execution" --
 * it is a real, completed transaction, just not autonomously triggered. */
export function ModeIndicator({ mode }: { mode: ActivitySource | "unavailable" }) {
  const label =
    mode === "live"
      ? "Live"
      : mode === "demo"
        ? "Demo"
        : mode === "historical_proof"
          ? "Manual execution"
          : "Unavailable";
  const cls = mode === "historical_proof" ? "manual" : mode === "unavailable" ? "unavailable" : mode;
  return <span className={`mode-indicator ${cls}`}>{label}</span>;
}
