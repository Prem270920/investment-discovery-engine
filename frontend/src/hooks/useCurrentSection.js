import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Which section the reader is on, given each section's top edge measured
 * from the top of the scrolling panel.
 *
 * A section becomes current once its top has passed the reading line (just
 * under the sticky index). At the very bottom the last section wins, since a
 * short final section may never reach the line.
 */
export function pickCurrentSection(sectionTops, readingLine, atBottom) {
  if (sectionTops.length === 0) return -1;
  if (atBottom) return sectionTops.length - 1;
  let current = 0;
  sectionTops.forEach((top, position) => {
    if (top <= readingLine) current = position;
  });
  return current;
}

// After a jump from the index, how long to hold the clicked section as
// current while the smooth scroll passes over the ones in between.
const JUMP_HOLD_MS = 1000;

/**
 * Tracks the current section of a scrolling container and jumps between
 * sections. sectionIds name elements inside the container by data-section.
 * contentKey should change whenever the sections are replaced (a new asset),
 * so positions are measured again.
 *
 * Returns [currentId, jumpTo].
 */
export function useCurrentSection(containerRef, sectionIds, { readingLineOffset = 24, contentKey, reducedMotion = false } = {}) {
  const [currentId, setCurrentId] = useState(sectionIds[0]);
  const heldId = useRef(null);
  const holdTimer = useRef(null);
  const idsKey = sectionIds.join("|");

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;
    // Rebuilt from the joined key, so a fresh array each render doesn't re-run this.
    const ids = idsKey.split("|");
    let frame = null;

    const measure = () => {
      frame = null;
      if (heldId.current) return;
      const box = container.getBoundingClientRect();
      const sections = ids.map((id) => container.querySelector(`[data-section="${id}"]`));
      if (sections.some((section) => !section)) return;
      // The sticky index sits at the top of the container; read just below it.
      const index = container.querySelector("[data-section-index]");
      const readingLine = (index ? index.getBoundingClientRect().height : 0) + readingLineOffset;
      const tops = sections.map((section) => section.getBoundingClientRect().top - box.top);
      const atBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 2;
      const position = pickCurrentSection(tops, readingLine, atBottom);
      if (position >= 0) setCurrentId(ids[position]);
    };
    const scheduleMeasure = () => {
      if (frame === null) frame = requestAnimationFrame(measure);
    };
    // When a jump finishes, stop holding but don't re-measure: a jump to the
    // third section that bottoms out the panel would otherwise hand the
    // highlight to the last one. The reader's next scroll takes over.
    const releaseHold = () => {
      heldId.current = null;
    };

    container.addEventListener("scroll", scheduleMeasure, { passive: true });
    container.addEventListener("scrollend", releaseHold);
    window.addEventListener("resize", scheduleMeasure);
    scheduleMeasure();
    return () => {
      container.removeEventListener("scroll", scheduleMeasure);
      container.removeEventListener("scrollend", releaseHold);
      window.removeEventListener("resize", scheduleMeasure);
      if (frame !== null) cancelAnimationFrame(frame);
    };
    // contentKey isn't read here; it is listed so new sections get measured.
  }, [containerRef, idsKey, readingLineOffset, contentKey]);

  useEffect(() => () => clearTimeout(holdTimer.current), []);

  const jumpTo = useCallback((id) => {
    const container = containerRef.current;
    const section = container?.querySelector(`[data-section="${id}"]`);
    if (!section) return;
    setCurrentId(id);
    heldId.current = id;
    clearTimeout(holdTimer.current);
    holdTimer.current = setTimeout(() => { heldId.current = null; }, JUMP_HOLD_MS);
    section.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
  }, [containerRef, reducedMotion]);

  return [currentId, jumpTo];
}
