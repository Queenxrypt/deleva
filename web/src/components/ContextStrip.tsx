/** A single, quiet line of context near a page header -- replaces repeating
 * a "LIVE DATA" badge on every card. The actual values already demonstrate
 * the data is live; this just orients the reader to chain/protocol/status. */
export function ContextStrip({
  chain,
  protocol,
  available,
}: {
  chain: string;
  protocol: string;
  available: boolean;
}) {
  return (
    <span className={`context-strip ${available ? "live" : ""}`}>
      {chain}
      <span className="dot-sep">·</span>
      {protocol}
      <span className="dot-sep">·</span>
      {available ? "Live" : "Unavailable"}
    </span>
  );
}
