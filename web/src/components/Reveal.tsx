import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

/** Restrained, one-time reveal-on-scroll: a section fades and lifts slightly
 * as it enters the viewport, once. Disabled entirely under
 * prefers-reduced-motion (see global.css). Purely editorial pacing -- never
 * gates or implies anything about real system/execution state. */
export function Reveal({ children, delay = 0 }: { children: ReactNode; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.15 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={ref} className={`reveal ${visible ? "reveal-visible" : ""}`} style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}
