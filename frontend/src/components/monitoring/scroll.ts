/** Scrolls the first *visible* element among `ids` to the middle of the viewport. */
export function scrollToFirstVisible(ids: string[]) {
  const target = ids
    .map((id) => document.getElementById(id))
    .find((element): element is HTMLElement => element !== null && element.offsetParent !== null);
  if (!target) return;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  target.scrollIntoView({ block: "center", behavior: reduceMotion ? "auto" : "smooth" });
}
