// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App, type Diagnosis } from "./App";

const diagnosis: Diagnosis = {
  draft: "Use the supported installer and verify the cache.",
  mode: "deterministic_fallback",
  citations: [
    {
      document_id: "doc-1",
      title: "Windows cache repair",
      source_url: "https://example.com/issues/1",
      score: 1.42,
    },
  ],
  selected_tools: ["search_similar_issues", "get_repository_context"],
  tool_executions: [
    {
      name: "search_similar_issues",
      status: "completed",
      summary: "Resolved issue matches: Windows cache repair",
    },
  ],
  approval: { id: "approval-1", status: "pending", publishable_comment: null, published: false },
  trace_id: "trace-1",
};

describe("IssuePilot evidence console", () => {
  it("renders diagnosis evidence and truthful fallback state", async () => {
    const diagnose = vi.fn().mockResolvedValue(diagnosis);
    const getTrace = vi.fn().mockResolvedValue({
      id: "trace-1",
      mode: "deterministic_fallback",
      spans: [
        { name: "retrieve", duration_ms: 1.25, attributes: { hit_count: 1 } },
        { name: "execute_tools", duration_ms: 0.1, attributes: { execution_count: 1 } },
      ],
    });
    const approve = vi.fn().mockResolvedValue({
      ...diagnosis.approval,
      status: "approved",
      publishable_comment: diagnosis.draft,
    });
    render(<App diagnose={diagnose} getTrace={getTrace} approve={approve} />);

    fireEvent.change(screen.getByLabelText("Issue title"), {
      target: { value: "Install fails on Windows" },
    });
    fireEvent.change(screen.getByLabelText("Issue details"), {
      target: { value: "Version 2 reports a cache error" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run diagnosis" }));

    expect(await screen.findByText("Deterministic fallback")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Windows cache repair" })).toHaveAttribute(
      "href",
      "https://example.com/issues/1",
    );
    expect(screen.getByText("search_similar_issues")).toBeInTheDocument();
    expect(screen.getByText("Resolved issue matches: Windows cache repair")).toBeInTheDocument();
    expect(await screen.findByText("retrieve · 1.250 ms")).toBeInTheDocument();
    expect(screen.getByText("Pending human approval")).toBeInTheDocument();
    expect(diagnose).toHaveBeenCalledWith({
      title: "Install fails on Windows",
      body: "Version 2 reports a cache error",
    });
    fireEvent.click(screen.getByRole("button", { name: "Approve draft" }));
    expect(await screen.findByText("Human approved")).toBeInTheDocument();
    expect(approve).toHaveBeenCalledWith("approval-1");
  });
});
