const AUTO_SCROLL_BOTTOM_THRESHOLD_PX = 48;

export function isNearScrollBottom(
  scrollTop: number,
  clientHeight: number,
  scrollHeight: number,
  threshold = AUTO_SCROLL_BOTTOM_THRESHOLD_PX,
) {
  return scrollHeight - (scrollTop + clientHeight) <= threshold;
}
