import type { ActivityEventResponse } from "../api/client";
import { ModeIndicator } from "./ModeIndicator";

// Routine monitoring events that repeat every cycle -- real, never deleted,
// but visually secondary to a notable event (a decision, an execution, a
// verification). Consecutive runs of these are grouped into one collapsed
// row so the actual autonomous execution stays the primary story.
const ROUTINE_TYPES = new Set(["POSITION_EVALUATED", "RISK_THRESHOLD_BREACHED"]);

function eventOutcome(event: ActivityEventResponse): "ok" | "fail" | "neutral" {
  if (event.event_type === "EXECUTION_FAILED") return "fail";
  if (
    event.event_type === "TRANSACTION_CONFIRMED" ||
    event.event_type === "POSITION_VERIFIED" ||
    event.event_type === "KEEPERHUB_EXECUTION"
  ) {
    return "ok";
  }
  return "neutral";
}

type Row =
  | { kind: "event"; event: ActivityEventResponse }
  | { kind: "group"; events: ActivityEventResponse[] };

function groupRoutineRuns(events: ActivityEventResponse[]): Row[] {
  const rows: Row[] = [];
  let run: ActivityEventResponse[] = [];
  const flush = () => {
    if (run.length === 0) return;
    rows.push(run.length === 1 ? { kind: "event", event: run[0] } : { kind: "group", events: run });
    run = [];
  };
  for (const event of events) {
    if (ROUTINE_TYPES.has(event.event_type)) {
      run.push(event);
    } else {
      flush();
      rows.push({ kind: "event", event });
    }
  }
  flush();
  return rows;
}

function EventRow({ event }: { event: ActivityEventResponse }) {
  const outcome = eventOutcome(event);
  return (
    <div className="timeline-item">
      <div className={`timeline-dot ${outcome === "ok" ? "ok" : outcome === "fail" ? "fail" : ""}`} />
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span className="timeline-event-type">{event.event_type.split("_").join(" ")}</span>
          <ModeIndicator mode={event.source} />
        </div>
        <div className="timeline-description">{event.description}</div>
        <div className="timeline-meta">
          <span>{new Date(event.timestamp).toLocaleString()}</span>
          {event.health_factor && <span>HF {event.health_factor}</span>}
          {event.transaction_hash && event.transaction_link ? (
            <a href={event.transaction_link} target="_blank" rel="noopener noreferrer">
              {event.transaction_hash.slice(0, 10)}…{event.transaction_hash.slice(-6)}
            </a>
          ) : (
            event.transaction_hash && <span>{event.transaction_hash}</span>
          )}
        </div>
      </div>
    </div>
  );
}

function RoutineGroup({ events }: { events: ActivityEventResponse[] }) {
  const first = events[0];
  const last = events[events.length - 1];
  return (
    <div className="timeline-item timeline-item--minor">
      <div className="timeline-dot" />
      <details>
        <summary className="timeline-group-summary">
          {events.length} monitoring checks
          <span className="timeline-meta" style={{ marginLeft: 8 }}>
            {new Date(last.timestamp).toLocaleTimeString()} – {new Date(first.timestamp).toLocaleTimeString()}
          </span>
        </summary>
        <div className="timeline-group-body">
          {events.map((event, i) => (
            <div className="timeline-group-row" key={`${event.timestamp}-${i}`}>
              <span className="timeline-event-type">{event.event_type.split("_").join(" ")}</span>
              {event.health_factor && <span className="metadata">HF {event.health_factor}</span>}
              <span className="metadata">{new Date(event.timestamp).toLocaleTimeString()}</span>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}

export function ActivityTimeline({ events }: { events: ActivityEventResponse[] }) {
  if (events.length === 0) {
    return <p className="skeleton">No activity recorded yet.</p>;
  }
  const rows = groupRoutineRuns(events);
  return (
    <div className="timeline">
      {rows.map((row, i) =>
        row.kind === "event" ? (
          <EventRow event={row.event} key={`${row.event.timestamp}-${i}`} />
        ) : (
          <RoutineGroup events={row.events} key={`group-${i}`} />
        )
      )}
    </div>
  );
}
