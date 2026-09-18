// Presentation-only helper: given a health factor and the strategy's own
// trigger threshold (both already computed by the backend), decide how to
// label/color it. Does NOT reimplement DELEVA's risk evaluation -- it only
// mirrors the same HEALTHY / THRESHOLD_BREACHED boundary the backend's
// RiskEvaluator already applied, purely for display.

export type RiskTier = "healthy" | "danger" | "unknown";

export function riskTier(healthFactor: string | null, triggerThreshold: string | null): RiskTier {
  if (healthFactor === null || triggerThreshold === null) return "unknown";
  const hf = Number(healthFactor);
  const trigger = Number(triggerThreshold);
  if (Number.isNaN(hf) || Number.isNaN(trigger)) return "unknown";
  return hf >= trigger ? "healthy" : "danger";
}

export function riskLabel(tier: RiskTier): string {
  return tier === "healthy" ? "Healthy" : tier === "danger" ? "Threshold breached" : "Unavailable";
}
