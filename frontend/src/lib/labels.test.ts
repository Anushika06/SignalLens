import { describe, expect, it } from "vitest";

import {
  APPROVAL_STATUS,
  EVIDENCE,
  EVIDENCE_ORDER,
  FEEDBACK_REASON,
  FEEDBACK_REASONS_BY_VERDICT,
  IMPORTANCE,
  IMPORTANCE_ORDER,
  PRIORITY,
  PRIORITY_ORDER,
  SEVERITY,
  SEVERITY_ORDER,
  TONE_BADGE,
  TONE_DOT,
  TONE_TEXT,
  type Tone,
} from "./labels";

const TONES: Tone[] = ["red", "orange", "amber", "green", "teal", "blue", "violet", "brand", "gray"];

describe("tone palettes", () => {
  it("define a class for every tone", () => {
    for (const palette of [TONE_BADGE, TONE_DOT, TONE_TEXT]) {
      expect(Object.keys(palette).sort()).toEqual([...TONES].sort());
      for (const tone of TONES) expect(palette[tone]).toMatch(/\S/);
    }
  });
});

describe("severity", () => {
  it("is ordered from most to least severe", () => {
    expect(SEVERITY_ORDER).toEqual(["critical", "high", "medium", "low"]);
  });

  it("follows the contract colours (critical=red, high=orange, medium=amber, low=blue)", () => {
    expect(SEVERITY.critical.tone).toBe("red");
    expect(SEVERITY.high.tone).toBe("orange");
    expect(SEVERITY.medium.tone).toBe("amber");
    expect(SEVERITY.low.tone).toBe("blue");
  });

  it("has a label and description for each level", () => {
    for (const key of SEVERITY_ORDER) {
      expect(SEVERITY[key].label).toMatch(/^[A-Z]/);
      expect(SEVERITY[key].description).toBeTruthy();
    }
  });
});

describe("evidence status", () => {
  it("lists every status exactly once, strongest first", () => {
    expect(EVIDENCE_ORDER).toEqual(["confirmed", "corroborated", "single_source", "conflicting", "unverified"]);
    expect(new Set(EVIDENCE_ORDER).size).toBe(EVIDENCE_ORDER.length);
    expect(Object.keys(EVIDENCE).sort()).toEqual([...EVIDENCE_ORDER].sort());
  });

  it("follows the contract colours", () => {
    expect(EVIDENCE.confirmed.tone).toBe("green");
    expect(EVIDENCE.corroborated.tone).toBe("teal");
    expect(EVIDENCE.single_source.tone).toBe("amber");
    expect(EVIDENCE.conflicting.tone).toBe("violet");
    expect(EVIDENCE.unverified.tone).toBe("gray");
  });

  it("never relies on colour alone: every status has a label, icon and explanation", () => {
    for (const key of EVIDENCE_ORDER) {
      expect(EVIDENCE[key].label).toBeTruthy();
      expect(EVIDENCE[key].icon).toBeTruthy();
      expect(EVIDENCE[key].description).toBeTruthy();
    }
  });
});

describe("ordered vocabularies", () => {
  it("cover their maps", () => {
    expect(Object.keys(IMPORTANCE).sort()).toEqual([...IMPORTANCE_ORDER].sort());
    expect(Object.keys(PRIORITY).sort()).toEqual([...PRIORITY_ORDER].sort());
  });
});

describe("feedback", () => {
  it("only offers reasons that have a label", () => {
    for (const reasons of Object.values(FEEDBACK_REASONS_BY_VERDICT)) {
      for (const reason of reasons) expect(FEEDBACK_REASON[reason]).toBeTruthy();
    }
  });

  it("offers 'other' for both verdicts", () => {
    expect(FEEDBACK_REASONS_BY_VERDICT.relevant).toContain("other");
    expect(FEEDBACK_REASONS_BY_VERDICT.not_relevant).toContain("other");
  });
});

describe("approvals", () => {
  it("labels every approval status", () => {
    for (const status of ["pending", "approved", "rejected", "executed", "failed"] as const) {
      expect(APPROVAL_STATUS[status].label).toBeTruthy();
    }
  });
});
