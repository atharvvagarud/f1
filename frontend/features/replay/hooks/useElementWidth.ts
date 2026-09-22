"use client";

// Measured container width for the replay probability chart (UI3).
//
// The chart is SVG with a viewBox; a fixed viewBox scaled into a narrow rail
// would shrink its 10px labels below legibility. Measuring the wrapper and
// building geometry at the real pixel width keeps type at its intended size at
// every breakpoint. Re-renders only when the container actually resizes.

import { useCallback, useEffect, useRef, useState } from "react";

export function useElementWidth<T extends HTMLElement>(
  fallback = 560,
): readonly [React.RefObject<T | null>, number] {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState(fallback);

  const measure = useCallback(() => {
    const element = ref.current;
    if (!element) return;
    const next = Math.round(element.clientWidth);
    if (next > 0) setWidth((current) => (current === next ? current : next));
  }, []);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [measure]);

  return [ref, width] as const;
}
