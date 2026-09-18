import type { MouseEvent } from "react";

/** Sets --spot-x/--spot-y CSS custom properties on the hovered element to
 * the pointer position, driving the restrained radial-highlight effect
 * defined in global.css (.how-card::after). Direct DOM property writes, not
 * React state -- avoids a re-render on every mousemove. Purely decorative;
 * never affects layout or data. */
export function handleSpotlight(e: MouseEvent<HTMLElement>): void {
  const rect = e.currentTarget.getBoundingClientRect();
  const x = ((e.clientX - rect.left) / rect.width) * 100;
  const y = ((e.clientY - rect.top) / rect.height) * 100;
  e.currentTarget.style.setProperty("--spot-x", `${x}%`);
  e.currentTarget.style.setProperty("--spot-y", `${y}%`);
}
