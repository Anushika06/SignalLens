import { describe, expect, it } from "vitest";

import { withQuery } from "./api";
import { activityHref, routes } from "./routes";

const WID = "00000000-0000-4000-8000-001000000001";

describe("withQuery", () => {
  it("skips empty values and encodes the rest", () => {
    expect(withQuery("/x", {})).toBe("/x");
    expect(withQuery("/x", { a: undefined, b: null, c: "" })).toBe("/x");
    expect(withQuery("/x", { a: "1 2", b: 3, c: true })).toBe("/x?a=1+2&b=3&c=true");
  });
});

describe("routes", () => {
  it("builds static and workspace routes", () => {
    expect(routes.home).toBe("/");
    expect(routes.newWorkspace).toBe("/new");
    expect(routes.dashboard(WID)).toBe(`/w/${WID}`);
    expect(routes.world(WID)).toBe(`/w/${WID}/world`);
    expect(routes.entity(WID, "e1")).toBe(`/w/${WID}/world/e1`);
    expect(routes.runs(WID)).toBe(`/w/${WID}/runs`);
    expect(routes.run(WID, "r1")).toBe(`/w/${WID}/runs/r1`);
    expect(routes.approvals(WID)).toBe(`/w/${WID}/approvals`);
    expect(routes.settings(WID)).toBe(`/w/${WID}/settings`);
    expect(routes.plan(WID, "p1")).toBe(`/w/${WID}/plan/p1`);
    expect(routes.report(WID, "rep")).toBe(`/w/${WID}/intel/rep`);
  });

  it("encodes path segments", () => {
    expect(routes.dashboard("a/b")).toBe("/w/a%2Fb");
    expect(routes.report("w", "x y")).toBe("/w/w/intel/x%20y");
  });

  it("adds only non-empty query parameters", () => {
    expect(routes.login()).toBe("/login");
    expect(routes.login("/w/1")).toBe("/login?next=%2Fw%2F1");
    expect(routes.lab()).toBe("/lab");
    expect(routes.lab(WID)).toBe(`/lab?from=${WID}`);
    expect(routes.intel(WID)).toBe(`/w/${WID}/intel`);
    expect(routes.intel(WID, { view: "all", severity: "high", area: "" })).toBe(
      `/w/${WID}/intel?view=all&severity=high`,
    );
  });

  it("builds the Ask page link with an optional pre-filled question", () => {
    expect(routes.ask(WID)).toBe(`/w/${WID}/ask`);
    expect(routes.ask(WID, "What changed in pricing?")).toBe(`/w/${WID}/ask?q=What+changed+in+pricing%3F`);
  });

  it("builds monitoring deep links", () => {
    expect(routes.monitoring(WID)).toBe(`/w/${WID}/monitoring`);
    expect(routes.monitoring(WID, "rules")).toBe(`/w/${WID}/monitoring?tab=rules`);
    expect(routes.source(WID, "s1")).toBe(`/w/${WID}/monitoring?tab=sources&source=s1`);
    expect(routes.filteredEvent(WID, "ev1")).toBe(`/w/${WID}/monitoring?tab=filtered&event=ev1`);
  });
});

describe("activityHref", () => {
  it("returns null without a link", () => {
    expect(activityHref(WID, null)).toBeNull();
  });

  it("maps each link type to its screen", () => {
    expect(activityHref(WID, { type: "report", id: "r" })).toBe(routes.report(WID, "r"));
    expect(activityHref(WID, { type: "run", id: "r" })).toBe(routes.run(WID, "r"));
    expect(activityHref(WID, { type: "source", id: "s" })).toBe(routes.source(WID, "s"));
    expect(activityHref(WID, { type: "plan", id: "p" })).toBe(routes.plan(WID, "p"));
    expect(activityHref(WID, { type: "event", id: "e" })).toBe(routes.filteredEvent(WID, "e"));
  });
});
