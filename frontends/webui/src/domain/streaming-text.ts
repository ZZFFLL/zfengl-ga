export const STREAM_STEP_INTERVAL_MS = 40;
export const STREAM_DONE_CATCHUP_INTERVAL_MS = 8;

type GraphemeSegment = { segment: string };
type GraphemeSegmenter = { segment(input: string): Iterable<GraphemeSegment> };
type GraphemeSegmenterConstructor = new (
  locales?: string | string[],
  options?: { granularity: "grapheme" },
) => GraphemeSegmenter;

const graphemeSegmenter = (() => {
  const Segmenter = (Intl as typeof Intl & { Segmenter?: GraphemeSegmenterConstructor }).Segmenter;
  return Segmenter ? new Segmenter(undefined, { granularity: "grapheme" }) : null;
})();

export function splitGraphemes(text: string) {
  if (!text) return [];
  if (graphemeSegmenter) {
    return Array.from(graphemeSegmenter.segment(text), (item) => item.segment);
  }
  return Array.from(text);
}

export function streamStepInterval(remainingChars: number, done: boolean) {
  if (!done) return STREAM_STEP_INTERVAL_MS;
  if (remainingChars > 480) return 0;
  if (remainingChars > 160) return 2;
  return STREAM_DONE_CATCHUP_INTERVAL_MS;
}

export function nextSmoothContent(displayed: string, target: string, done = false) {
  const remaining = splitGraphemes(target.slice(displayed.length));
  if (remaining.length === 0) return target;
  const step = done ? Math.min(28, remaining.length) : Math.min(3, remaining.length);
  return displayed + remaining.slice(0, step).join("");
}

export function prefersReducedMotion() {
  return Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}
