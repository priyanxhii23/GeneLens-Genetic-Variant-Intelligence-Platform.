/**
 * Renders floating content (dropdowns) in a portal on <body>, positioned against
 * an anchor element with `position: fixed`.
 *
 * Why: cards use transforms (Framer Motion) and backdrop-filter, which each
 * create a new stacking context – a dropdown rendered inside a card can never
 * rise above the *next* card, whatever its z-index. Rendering in a portal
 * escapes every ancestor stacking context, overflow clip and transform.
 *
 * Behaviour: placed directly below the anchor; flips above when there is not
 * enough room below; clamped to the viewport horizontally; height limited to
 * the available space (content scrolls); follows scrolling/resizing via rAF.
 */
import { useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";

export default function AnchoredPortal({ anchor, open, children, minWidth = 0, maxHeight = 460, gap = 6, onPanel }: {
  anchor: RefObject<HTMLElement>; open: boolean; children: ReactNode; minWidth?: number; maxHeight?: number; gap?: number;
  onPanel?: (el: HTMLDivElement | null) => void;
}) {
  const [style, setStyle] = useState<React.CSSProperties>({ visibility: "hidden" });
  const frame = useRef(0);

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const el = anchor.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const vw = window.innerWidth, vh = window.innerHeight, margin = 8;
      const width = Math.min(Math.max(r.width, minWidth), vw - 2 * margin);
      const left = Math.min(Math.max(margin, r.left), vw - width - margin);
      const below = vh - r.bottom - gap - margin;
      const above = r.top - gap - margin;
      const flip = below < Math.min(maxHeight, 240) && above > below;
      const avail = Math.max(160, Math.min(maxHeight, flip ? above : below));
      setStyle(flip
        ? { position: "fixed", left, width, bottom: vh - r.top + gap, maxHeight: avail, zIndex: 1000 }
        : { position: "fixed", left, width, top: r.bottom + gap, maxHeight: avail, zIndex: 1000 });
    };
    const schedule = () => { cancelAnimationFrame(frame.current); frame.current = requestAnimationFrame(place); };
    place();
    window.addEventListener("scroll", schedule, true);  // capture: also inner scroll containers
    window.addEventListener("resize", schedule);
    return () => { cancelAnimationFrame(frame.current); window.removeEventListener("scroll", schedule, true); window.removeEventListener("resize", schedule); };
  }, [open, anchor, minWidth, maxHeight, gap]);

  if (!open) return null;
  return createPortal(
    <div ref={onPanel} style={style} className="flex flex-col" data-portal="dropdown">{children}</div>,
    document.body,
  );
}
