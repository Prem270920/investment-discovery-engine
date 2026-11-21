import { useEffect, useRef, useState } from "react";

const observerSupported = () =>
  typeof window !== "undefined" && typeof window.IntersectionObserver === "function";

/**
 * Reports once when an element first scrolls into view, then stops watching.
 *
 *   const [stripRef, stripInView] = useInView({ threshold: 0.4 });
 *   <div ref={stripRef} className={stripInView ? styles.revealed : styles.waiting} />
 *
 * Fires once because reveals here play a single time; replaying them on every
 * scroll past would turn explanation into decoration.
 *
 * Without IntersectionObserver the element counts as visible from the start,
 * so content is never left stuck in its pre reveal state.
 *
 * Options are read when the element is first observed; changing them later
 * has no effect, which suits a one shot reveal.
 */
export function useInView({ threshold = 0.2, rootMargin = "0px" } = {}) {
  const elementRef = useRef(null);
  const [inView, setInView] = useState(() => !observerSupported());

  useEffect(() => {
    const element = elementRef.current;
    if (inView || !element || !observerSupported()) {
      return undefined;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setInView(true);
          observer.disconnect();
        }
      },
      { threshold, rootMargin },
    );
    observer.observe(element);
    return () => observer.disconnect();
    // threshold and rootMargin are deliberately left out: see the note above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView]);

  return [elementRef, inView];
}
