import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { EVIDENCE, EVIDENCE_ORDER } from "@/lib/labels";

import { EvidenceExplainerCard } from "./evidence-explainer-card";

describe("EvidenceExplainerCard", () => {
  it("lists every evidence status with its rule and marks the card's own status", () => {
    render(
      <TooltipProvider>
        <EvidenceExplainerCard status="single_source" />
      </TooltipProvider>,
    );
    expect(screen.getByText("How sure are we?")).toBeInTheDocument();

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(EVIDENCE_ORDER.length);
    EVIDENCE_ORDER.forEach((status, index) => {
      expect(items[index]).toHaveTextContent(EVIDENCE[status].label);
      expect(items[index]).toHaveTextContent(EVIDENCE[status].description ?? "");
    });

    const current = items.filter((item) => item.getAttribute("aria-current") === "true");
    expect(current).toHaveLength(1);
    expect(within(current[0]).getByText("Single source")).toBeInTheDocument();
    expect(within(current[0]).getByText("This card")).toBeInTheDocument();
  });
});
