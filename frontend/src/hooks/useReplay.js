import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Drives a replay from 0 to 1 over durationMs with requestAnimationFrame.
 *
 * Progress starts at 1, so before anyone presses play the chart already shows
 * the finished result: nothing has to be watched to be seen. start() rewinds
 * to 0 and plays; pressing it again mid replay starts over. Under reduced
 * motion start() jumps straight to the end.
 *
 * finishedCount goes up each time a replay reaches the end, which lets the
 * caller re-reveal whatever should "appear" once the replay is done.
 */
export function useReplay(durationMs, reducedMotion) {
  const [progress, setProgress] = useState(1);
  const [playing, setPlaying] = useState(false);
  const [finishedCount, setFinishedCount] = useState(0);
  const frameRef = useRef(null);

  const stopFrames = () => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    frameRef.current = null;
  };

  const start = useCallback(() => {
    stopFrames();
    if (reducedMotion) {
      setProgress(1);
      setPlaying(false);
      setFinishedCount((count) => count + 1);
      return;
    }
    let startedAt = null;
    setProgress(0);
    setPlaying(true);
    const advance = (now) => {
      if (startedAt === null) startedAt = now;
      const fraction = Math.min(1, (now - startedAt) / durationMs);
      setProgress(fraction);
      if (fraction < 1) {
        frameRef.current = requestAnimationFrame(advance);
      } else {
        frameRef.current = null;
        setPlaying(false);
        setFinishedCount((count) => count + 1);
      }
    };
    frameRef.current = requestAnimationFrame(advance);
  }, [durationMs, reducedMotion]);

  // An unmounted chart must not keep scheduling frames.
  useEffect(() => stopFrames, []);

  return { progress, playing, finishedCount, start };
}
