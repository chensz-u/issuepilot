import { type FormEvent, useState } from "react";

import "./styles.css";

type EvidenceArtifact = {
  id: string;
  kind: "repository" | "issue" | "workflow" | "commit" | "source" | "error";
  title: string;
  preview: string;
  source_url: string;
  tool: string;
};

type Hypothesis = {
  id: string;
  statement: string;
  status: "proposed" | "supported" | "rejected" | "insufficient_evidence";
  evidence_ids: string[];
};

type InvestigationStep = {
  id: string;
  title: string;
  command: string[];
  rationale: string;
  evidence_ids: string[];
  status: "proposed";
};

type QualityAssessment = {
  risk_level: "low" | "medium" | "high";
  supported_evidence_count: number;
  rejected_evidence_count: number;
  tool_error_count: number;
  approval_allowed: boolean;
  checks: { id: string; passed: boolean; detail: string }[];
};

export type Investigation = {
  id: string;
  repository: { owner: string; name: string };
  title: string;
  body: string;
  status: "running" | "awaiting_approval" | "approved" | "rejected" | "insufficient_evidence";
  evidence: EvidenceArtifact[];
  hypotheses: Hypothesis[];
  plan: InvestigationStep[];
  quality: QualityAssessment | null;
  draft: string;
  publishable_comment: string | null;
  published: boolean;
};

type InvestigationEvent = {
  sequence: number;
  name: string;
  payload: Record<string, unknown>;
};

type StartInvestigation = (request: {
  repository: string;
  title: string;
  body: string;
}) => Promise<Investigation>;
type ReplayEvents = (id: string) => Promise<InvestigationEvent[]>;
type Decide = (id: string, decision: "approve" | "reject") => Promise<Investigation>;

const defaultStart: StartInvestigation = async (request) => {
  const response = await fetch("/api/investigations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error("Investigation request failed");
  return response.json() as Promise<Investigation>;
};

const defaultReplay: ReplayEvents = async (id) => {
  const response = await fetch(`/api/investigations/${id}/events`);
  if (!response.ok) throw new Error("Trajectory request failed");
  const text = await response.text();
  return text
    .trim()
    .split("\n\n")
    .filter(Boolean)
    .map((block) => {
      const lines = Object.fromEntries(
        block.split("\n").map((line) => {
          const [key, ...value] = line.split(": ");
          return [key, value.join(": ")];
        }),
      );
      return {
        sequence: Number(lines.id),
        name: lines.event,
        payload: JSON.parse(lines.data) as Record<string, unknown>,
      };
    });
};

const defaultDecide: Decide = async (id, decision) => {
  const response = await fetch(`/api/investigations/${id}/approval`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  });
  if (!response.ok) throw new Error("Approval request failed");
  return response.json() as Promise<Investigation>;
};

export function App({
  startInvestigation = defaultStart,
  replayEvents = defaultReplay,
  decide = defaultDecide,
}: {
  startInvestigation?: StartInvestigation;
  replayEvents?: ReplayEvents;
  decide?: Decide;
}) {
  const [repository, setRepository] = useState("chenyi-c/issuepilot");
  const [title, setTitle] = useState("Cache failure on Windows CI");
  const [body, setBody] = useState("The package cache is locked during the install job.");
  const [result, setResult] = useState<Investigation | null>(null);
  const [events, setEvents] = useState<InvestigationEvent[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const investigation = await startInvestigation({ repository, title, body });
      setResult(investigation);
      setEvents(await replayEvents(investigation.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Investigation request failed");
    } finally {
      setLoading(false);
    }
  }

  async function decideInvestigation(decision: "approve" | "reject") {
    if (!result) return;
    setLoading(true);
    setError("");
    try {
      setResult(await decide(result.id, decision));
      setEvents(await replayEvents(result.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Approval request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <header className="hero">
        <p className="eyebrow">V4 · AUDITABLE GITHUB INVESTIGATION AGENT</p>
        <h1>IssuePilot</h1>
        <p className="lede">
          Investigate repository failures through allowlisted GitHub tools, replayable evidence,
          durable checkpoints, and explicit human decisions.
        </p>
      </header>

      <section className="workspace">
        <form className="panel form-panel" onSubmit={submit}>
          <div className="panel-heading"><span>01</span><h2>Repository intake</h2></div>
          <label htmlFor="repository">Repository</label>
          <input id="repository" value={repository} onChange={(event) => setRepository(event.target.value)} required />
          <label htmlFor="issue-title">Issue title</label>
          <input id="issue-title" value={title} onChange={(event) => setTitle(event.target.value)} minLength={3} required />
          <label htmlFor="issue-body">Failure details</label>
          <textarea id="issue-body" value={body} onChange={(event) => setBody(event.target.value)} minLength={3} rows={8} required />
          <button disabled={loading}>{loading ? "Investigating…" : "Start investigation"}</button>
          {error ? <p className="error">{error}</p> : null}
        </form>

        <section className="panel evidence-panel" aria-live="polite">
          <div className="panel-heading"><span>02</span><h2>Investigation trajectory</h2></div>
          {result ? (
            <InvestigationView result={result} events={events} loading={loading} onDecide={decideInvestigation} />
          ) : (
            <div className="empty"><div className="signal" /><p>Start a repository investigation to reveal hypotheses, tool evidence, checkpoints, and approval state.</p></div>
          )}
        </section>
      </section>
    </main>
  );
}

const STATUS_LABELS: Record<Investigation["status"], string> = {
  running: "Investigation running",
  awaiting_approval: "Awaiting human approval",
  approved: "Human approved",
  rejected: "Human rejected",
  insufficient_evidence: "Approval blocked: insufficient evidence",
};

function InvestigationView({ result, events, loading, onDecide }: {
  result: Investigation;
  events: InvestigationEvent[];
  loading: boolean;
  onDecide: (decision: "approve" | "reject") => void;
}) {
  return (
    <div className="evidence-stack">
      <div className="status-row"><span className="mode">{result.repository.owner}/{result.repository.name}</span><span className="approval">{STATUS_LABELS[result.status]}</span></div>
      <section><h3>Hypotheses</h3><ol className="hypotheses">{result.hypotheses.map((item) => <li key={item.id}><strong>{item.status}</strong><span>{item.statement}</span></li>)}</ol></section>
      <section><h3>GitHub evidence</h3><ol className="citations">{result.evidence.map((item) => <li key={item.id}><a href={item.source_url} target="_blank" rel="noreferrer">{item.title}</a><code>{item.tool}</code><p>{item.preview}</p></li>)}</ol></section>
      <section><h3>Verification plan</h3><ol className="citations">{result.plan.map((step) => <li key={step.id}><strong>{step.title}</strong><code>{step.command.join(" ")}</code><p>{step.rationale}</p></li>)}</ol></section>
      {result.quality ? <section><h3>Quality policy</h3><p className="approval">{result.quality.risk_level.toUpperCase()} RISK</p><ol className="trace-spans">{result.quality.checks.map((check) => <li key={check.id}>{check.passed ? "PASS" : "REVIEW"} · {check.detail}</li>)}</ol></section> : null}
      <article className="draft"><h3>Cited draft</h3><pre>{result.draft}</pre></article>
      <section><h3>Replayable trajectory</h3><ol className="trace-spans">{events.map((event) => <li key={event.sequence}>{String(event.sequence).padStart(2, "0")} · {event.name}</li>)}</ol></section>
      {result.status === "awaiting_approval" ? <div className="decision-row">{result.quality?.approval_allowed !== false ? <button type="button" disabled={loading} onClick={() => onDecide("approve")}>Approve evidence draft</button> : null}<button className="secondary" type="button" disabled={loading} onClick={() => onDecide("reject")}>Reject draft</button></div> : null}
      <a className="secondary" href={`/api/investigations/${result.id}/audit.zip`} download>Download audit bundle</a>
      <p className="trace-id">THREAD / {result.id} · PUBLISHED / {String(result.published)}</p>
    </div>
  );
}
