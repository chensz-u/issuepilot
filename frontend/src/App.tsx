import { type FormEvent, useState } from "react";

import "./styles.css";

type Citation = {
  document_id: string;
  title: string;
  source_url: string;
  score: number;
};

type Approval = {
  id: string;
  status: "pending" | "approved" | "blocked";
  publishable_comment: string | null;
  published: boolean;
};

type ToolExecution = {
  name: string;
  status: "completed";
  summary: string;
};

type Trace = {
  id: string;
  mode: string;
  spans: Array<{
    name: string;
    duration_ms: number;
    attributes: Record<string, string | number | boolean>;
  }>;
};

export type Diagnosis = {
  draft: string;
  mode: "deterministic_fallback" | "model";
  citations: Citation[];
  selected_tools: string[];
  tool_executions: ToolExecution[];
  approval: Approval;
  trace_id: string;
};

type Diagnose = (request: { title: string; body: string }) => Promise<Diagnosis>;
type GetTrace = (id: string) => Promise<Trace>;
type Approve = (id: string) => Promise<Approval>;

const defaultDiagnose: Diagnose = async (request) => {
  const response = await fetch("/api/diagnoses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error("Diagnosis request failed");
  return response.json() as Promise<Diagnosis>;
};

const defaultGetTrace: GetTrace = async (id) => {
  const response = await fetch(`/api/traces/${id}`);
  if (!response.ok) throw new Error("Trace request failed");
  return response.json() as Promise<Trace>;
};

const defaultApprove: Approve = async (id) => {
  const response = await fetch(`/api/approvals/${id}`, { method: "POST" });
  if (!response.ok) throw new Error("Approval request failed");
  return response.json() as Promise<Approval>;
};

export function App({
  diagnose = defaultDiagnose,
  getTrace = defaultGetTrace,
  approve = defaultApprove,
}: {
  diagnose?: Diagnose;
  getTrace?: GetTrace;
  approve?: Approve;
}) {
  const [title, setTitle] = useState("Install fails on Windows");
  const [body, setBody] = useState("Version 2 reports a locked package cache error");
  const [result, setResult] = useState<Diagnosis | null>(null);
  const [trace, setTrace] = useState<Trace | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [approvalLoading, setApprovalLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const diagnosis = await diagnose({ title, body });
      setResult(diagnosis);
      setTrace(await getTrace(diagnosis.trace_id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Diagnosis request failed");
    } finally {
      setLoading(false);
    }
  }

  async function approveDraft() {
    if (!result) return;
    setApprovalLoading(true);
    setError("");
    try {
      const approval = await approve(result.approval.id);
      setResult({ ...result, approval });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Approval request failed");
    } finally {
      setApprovalLoading(false);
    }
  }

  return (
    <main>
      <header className="hero">
        <p className="eyebrow">EVIDENCE-FIRST ISSUE COPILOT</p>
        <h1>IssuePilot</h1>
        <p className="lede">
          Diagnose public GitHub issues with grounded retrieval, controlled tools, human approval,
          and inspectable traces.
        </p>
      </header>

      <section className="workspace">
        <form className="panel form-panel" onSubmit={submit}>
          <div className="panel-heading">
            <span>01</span>
            <h2>Issue intake</h2>
          </div>
          <label htmlFor="issue-title">Issue title</label>
          <input
            id="issue-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            minLength={3}
            required
          />
          <label htmlFor="issue-body">Issue details</label>
          <textarea
            id="issue-body"
            value={body}
            onChange={(event) => setBody(event.target.value)}
            minLength={3}
            rows={8}
            required
          />
          <button disabled={loading}>{loading ? "Tracing…" : "Run diagnosis"}</button>
          {error ? <p className="error">{error}</p> : null}
        </form>

        <section className="panel evidence-panel" aria-live="polite">
          <div className="panel-heading">
            <span>02</span>
            <h2>Evidence trace</h2>
          </div>
          {result ? (
            <Evidence
              result={result}
              trace={trace}
              onApprove={approveDraft}
              approvalLoading={approvalLoading}
            />
          ) : (
            <EmptyState />
          )}
        </section>
      </section>
    </main>
  );
}

function Evidence({
  result,
  trace,
  onApprove,
  approvalLoading,
}: {
  result: Diagnosis;
  trace: Trace | null;
  onApprove: () => void;
  approvalLoading: boolean;
}) {
  const approvalLabel = {
    pending: "Pending human approval",
    approved: "Human approved",
    blocked: "Approval blocked: no grounded evidence",
  }[result.approval.status];

  return (
    <div className="evidence-stack">
      <div className="status-row">
        <span className="mode">
          {result.mode === "model" ? "Model generated" : "Deterministic fallback"}
        </span>
        <span className="approval">{approvalLabel}</span>
      </div>
      <article className="draft">
        <h3>Draft diagnosis</h3>
        <pre>{result.draft}</pre>
      </article>
      <div>
        <h3>Retrieved evidence</h3>
        <ol className="citations">
          {result.citations.map((citation) => (
            <li key={citation.document_id}>
              <a href={citation.source_url} target="_blank" rel="noreferrer">
                {citation.title}
              </a>
              <span>{citation.score.toFixed(3)}</span>
            </li>
          ))}
        </ol>
      </div>
      <div>
        <h3>Controlled tools</h3>
        <div className="tools">
          {result.selected_tools.map((tool) => (
            <code key={tool}>{tool}</code>
          ))}
        </div>
        <ul className="tool-results">
          {result.tool_executions.map((execution) => (
            <li key={execution.name}>{execution.summary}</li>
          ))}
        </ul>
      </div>
      <div>
        <h3>Execution trace</h3>
        <ol className="trace-spans">
          {trace?.spans.map((span) => (
            <li key={span.name}>
              {span.name} · {span.duration_ms.toFixed(3)} ms
            </li>
          ))}
        </ol>
      </div>
      {result.approval.status === "pending" ? (
        <button type="button" disabled={approvalLoading} onClick={onApprove}>
          {approvalLoading ? "Approving…" : "Approve draft"}
        </button>
      ) : null}
      <p className="trace-id">TRACE / {result.trace_id}</p>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="empty">
      <div className="signal" />
      <p>Submit an issue to reveal retrieval scores, citations, selected tools, and approval state.</p>
    </div>
  );
}
