import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { EVIDENCE, EVIDENCE_ORDER, SEVERITY, SEVERITY_ORDER } from "@/lib/labels";

import { AreaChip, EvidenceBadge, MetaBadge, SeverityBadge, SeverityDot } from "./badges";

function renderWithTooltips(ui: React.ReactElement) {
  return render(<TooltipProvider>{ui}</TooltipProvider>);
}

describe("SeverityBadge", () => {
  it.each(SEVERITY_ORDER)("renders the %s label with screen-reader context", (severity) => {
    renderWithTooltips(<SeverityBadge severity={severity} withTooltip={false} />);
    const badge = screen.getByText(SEVERITY[severity].label);
    expect(badge).toBeInTheDocument();
    // Colour is never the only signal: the accessible text says what the badge means.
    expect(badge.closest("[data-slot=badge]") ?? badge).toHaveTextContent(`${SEVERITY[severity].label} severity`);
  });

  it("uses the severity tone classes", () => {
    renderWithTooltips(<SeverityBadge severity="critical" withTooltip={false} />);
    expect(screen.getByText("Critical").className).toMatch(/red/);
  });

  it("explains severity in a keyboard-reachable tooltip", async () => {
    const user = userEvent.setup();
    renderWithTooltips(<SeverityBadge severity="high" focusable />);
    await user.tab();
    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent(/High severity/);
    expect(tooltip).toHaveTextContent(/separately from evidence status/);
  });
});

describe("SeverityDot", () => {
  it("is decorative with a screen-reader label", () => {
    const { container } = render(<SeverityDot severity="medium" />);
    expect(screen.getByText("Medium severity")).toHaveClass("sr-only");
    expect(container.querySelector("[aria-hidden=true]")).not.toBeNull();
  });
});

describe("EvidenceBadge", () => {
  it.each(EVIDENCE_ORDER)("renders the %s label and an icon", (status) => {
    const { container } = renderWithTooltips(<EvidenceBadge status={status} explain={false} />);
    expect(screen.getByText(EVIDENCE[status].label)).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("explains the rule behind the status", async () => {
    const user = userEvent.setup();
    renderWithTooltips(<EvidenceBadge status="corroborated" focusable />);
    await user.tab();
    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent("Corroborated.");
    expect(tooltip).toHaveTextContent(/two independent publishers/);
  });

  it("can list every status with the current one highlighted", async () => {
    const user = userEvent.setup();
    renderWithTooltips(<EvidenceBadge status="conflicting" explain="all" focusable />);
    await user.tab();
    const tooltip = await screen.findByRole("tooltip");
    for (const status of EVIDENCE_ORDER) expect(tooltip).toHaveTextContent(EVIDENCE[status].label);
    expect(tooltip).toHaveTextContent(/▸ Conflicting/);
  });
});

describe("MetaBadge and chips", () => {
  it("renders a meta label without tooltip when asked", () => {
    renderWithTooltips(<MetaBadge meta={{ label: "Awaiting decision", tone: "amber" }} tooltip={false} />);
    expect(screen.getByText("Awaiting decision")).toBeInTheDocument();
  });

  it("renders area chips", () => {
    render(<AreaChip label="Pricing & fees" />);
    expect(screen.getByText("Pricing & fees")).toBeInTheDocument();
  });
});
