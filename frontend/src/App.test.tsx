// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App, type Investigation } from "./App";

const awaiting: Investigation = {
  id: "investigation-1",
  repository: { owner: "acme", name: "widget" },
  title: "Cache failure",
  body: "CI package cache is locked",
  status: "awaiting_approval",
  evidence: [
    {
      id: "issue-7",
      kind: "issue",
      title: "Cache repair",
      preview: "Stop the worker and clear only its cache.",
      source_url: "https://github.com/acme/widget/issues/7",
      tool: "search_issues",
    },
  ],
  hypotheses: [
    {
      id: "hypothesis-1",
      statement: "The worker may hold the package cache lock.",
      status: "supported",
      evidence_ids: ["issue-7"],
    },
  ],
  plan: [
    {
      id: "verify-supported-evidence",
      title: "Reproduce the supported repository evidence",
      command: ["python", "-m", "pytest", "-q"],
      rationale: "Run the repository test suite before changing code.",
      evidence_ids: ["issue-7"],
      status: "proposed",
    },
  ],
  draft: "Investigate the worker cache lock [issue-7].",
  publishable_comment: null,
  published: false,
};

describe("IssuePilot V3 investigation console", () => {
  it("renders repository evidence trajectory and human approval", async () => {
    const start = vi.fn().mockResolvedValue(awaiting);
    const replay = vi.fn().mockResolvedValue([
      { sequence: 1, name: "validate", payload: { status: "running" } },
      { sequence: 2, name: "tools", payload: {} },
      { sequence: 3, name: "awaiting_approval", payload: {} },
    ]);
    const decide = vi.fn().mockResolvedValue({
      ...awaiting,
      status: "approved",
      publishable_comment: awaiting.draft,
    });
    render(<App startInvestigation={start} replayEvents={replay} decide={decide} />);

    fireEvent.change(screen.getByLabelText("Repository"), { target: { value: "acme/widget" } });
    fireEvent.click(screen.getByRole("button", { name: "Start investigation" }));

    expect(await screen.findByText("Awaiting human approval")).toBeInTheDocument();
    expect(screen.getByText("The worker may hold the package cache lock.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cache repair" })).toHaveAttribute(
      "href",
      "https://github.com/acme/widget/issues/7",
    );
    expect(screen.getByText("search_issues")).toBeInTheDocument();
    expect(screen.getByText("python -m pytest -q")).toBeInTheDocument();
    expect(screen.getByText("02 · tools")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Approve evidence draft" }));
    expect(await screen.findByText("Human approved")).toBeInTheDocument();
    expect(decide).toHaveBeenCalledWith("investigation-1", "approve");
  });
});
