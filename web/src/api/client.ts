// Thin fetch wrapper around the DELEVA backend API. No business logic lives
// here -- types mirror api/schemas.py exactly; this file only fetches and
// parses. The backend, not this file, owns the KeeperHub API key and every
// real/demo/historical-proof distinction.

const BASE = "/api";

export type ActivitySource = "live" | "demo" | "historical_proof";

export interface PositionData {
  wallet: string;
  chain: string;
  chain_display: string;
  protocol: string;
  protocol_display: string;
  collateral_usd: string | null;
  debt_usd: string | null;
  available_borrows_usd: string | null;
  health_factor: string | null;
  ltv: string | null;
  liquidation_threshold: string | null;
  usdc_balance: string | null;
  timestamp: string;
}

export interface PositionResponse {
  available: boolean;
  // "live" only when a real position was actually retrieved; null when
  // unavailable -- mirrors api/schemas.py::PositionResponse exactly, so this
  // type can never claim "live" for a response that carries no real data.
  source: "live" | null;
  reason: string | null;
  data: PositionData | null;
  note: string | null;
}

export interface StrategyResponse {
  name: string;
  protocol: string;
  protocol_display: string;
  chain: string;
  chain_display: string;
  trigger: string;
  trigger_health_factor: string;
  target_health_factor: string;
  action: string;
  decision_engine: string;
  execution_layer: string;
}

export interface LegResultSummary {
  tx_type: string;
  simulated: boolean;
  simulation_success: boolean | null;
  would_revert: boolean | null;
  executed: boolean;
  execution_status: string | null;
  transaction_hash: string | null;
  transaction_link: string | null;
}

export interface CycleResultSummary {
  engine_state: string;
  risk_state: string;
  execution_mode: string;
  triggered: boolean;
  action_taken: boolean;
  overall_success: boolean;
  skipped_reason: string | null;
  error: string | null;
  legs: LegResultSummary[];
  verification_success: boolean | null;
  verification_reason: string | null;
}

export interface EngineStatusResponse {
  configured: boolean;
  configuration_error: string | null;
  container_state: string | null;
  engine_state: string | null;
  execution_mode: string | null;
  pending_execution_id: string | null;
  monitoring_interval_seconds: number | null;
  last_cycle: CycleResultSummary | null;
  // Set only while the loop is RUNNING and its most recent cycle raised an
  // unexpected exception (e.g. a transient KeeperHub/network failure) -- the
  // loop is still alive and will retry on its next scheduled cycle. Clears
  // as soon as a cycle succeeds.
  runner_error: string | null;
}

export interface ActivityEventResponse {
  event_type: string;
  timestamp: string;
  description: string;
  health_factor: string | null;
  strategy: string | null;
  execution_id: string | null;
  transaction_hash: string | null;
  transaction_link: string | null;
  status: string | null;
  source: ActivitySource;
}

export interface ActivityResponse {
  events: ActivityEventResponse[];
  real_proof_transaction_hash: string;
  real_proof_transaction_link: string;
}

export interface DemoCycleResponse {
  cycle_number: number;
  summary: CycleResultSummary;
  events: ActivityEventResponse[];
}

export interface DemoRunResponse {
  mode: "demo";
  note: string;
  cycles: DemoCycleResponse[];
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`);
  if (!response.ok) {
    throw new Error(`${path} failed: HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

async function postJson<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { method: "POST" });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${path} failed: HTTP ${response.status} ${body}`);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => getJson<{ status: "ok" }>("/health"),
  position: () => getJson<PositionResponse>("/position"),
  strategy: () => getJson<StrategyResponse>("/strategy"),
  engineStatus: () => getJson<EngineStatusResponse>("/engine/status"),
  activity: () => getJson<ActivityResponse>("/activity"),
  runOnce: () => postJson<EngineStatusResponse>("/engine/run-once"),
  startEngine: () => postJson<EngineStatusResponse>("/engine/start"),
  stopEngine: () => postJson<EngineStatusResponse>("/engine/stop"),
  runDemo: () => postJson<DemoRunResponse>("/demo/run"),
};
