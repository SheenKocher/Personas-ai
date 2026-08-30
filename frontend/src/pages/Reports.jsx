import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { listRuns, getRunReport, getBatchReport } from "@/lib/api";
import { REPORTS } from "@/constants/testIds";
import { FileText, Activity, Copy, Check, Layers, User, ChevronDown, RefreshCw, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner, ErrorBanner, EmptyState } from "@/components/shared";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SEV_COLORS = { 1: "#FBBF24", 2: "#FBBF24", 3: "#F59E0B", 4: "#F43F5E", 5: "#F43F5E" };
const OUTCOME_COLORS = { success: "#10B981", gave_up: "#F43F5E", max_steps: "#F59E0B", in_progress: "#2DD4BF" };
const ISSUE_SEV = {
  critical: { c: "#F43F5E", label: "Critical" },
  high: { c: "#FB7185", label: "High" },
  medium: { c: "#F59E0B", label: "Medium" },
  low: { c: "#FBBF24", label: "Low" },
};

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard?.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1200);
      }}
      className="inline-flex items-center gap-1 text-[10px] font-mono hover:underline"
      style={{ color: "#64748B" }}
      title="Copy ID"
    >
      {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
      {text.slice(0, 8)}…
    </button>
  );
}

function ScreenRow({ screen }) {
  return (
    <div className="rounded-lg p-3 mb-2" style={{ background: "#0B0F1A", border: "0.5px solid #1E293B" }}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-sm font-medium truncate" style={{ color: "#F1F5F9" }}>{screen.screen}</span>
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-xs tabular-nums" style={{ color: "#F1F5F9" }}>Score: {screen.weighted_score}</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-md" style={{ background: `${SEV_COLORS[screen.max_severity] || "#64748B"}20`, color: SEV_COLORS[screen.max_severity] || "#64748B" }}>
            sev {screen.max_severity}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-3 text-[10px] mb-2" style={{ color: "#64748B" }}>
        <span>{screen.total_signals} signals</span>
        <span>{screen.affected_runs} run{screen.affected_runs !== 1 ? "s" : ""} affected</span>
      </div>
      <div className="space-y-0.5">
        {(screen.signals || []).slice(0, 6).map((s, i) => (
          <div key={i} className="flex items-start gap-2 text-xs">
            <span className="w-4 h-4 shrink-0 rounded flex items-center justify-center text-[9px] font-medium mt-0.5" style={{ background: `${SEV_COLORS[s.severity] || "#64748B"}20`, color: SEV_COLORS[s.severity] || "#64748B" }}>
              {s.severity}
            </span>
            <span style={{ color: "#94A3B8" }}>{s.description}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function OutcomePills({ counts }) {
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {Object.entries(counts).map(([oc, n]) => (
        <span key={oc} className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: `${OUTCOME_COLORS[oc] || "#64748B"}20`, color: OUTCOME_COLORS[oc] || "#64748B" }}>
          {n} {oc.replace("_", " ")}
        </span>
      ))}
    </div>
  );
}

function IssueCard({ issue }) {
  const sev = ISSUE_SEV[issue.severity] || ISSUE_SEV.medium;
  return (
    <div className="rounded-lg p-4 mb-3" style={{ background: "#0B0F1A", border: `0.5px solid ${sev.c}44` }}>
      <div className="flex items-start justify-between gap-3 mb-2">
        <span className="text-sm font-medium" style={{ color: "#F1F5F9" }}>{issue.title}</span>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-[10px] px-1.5 py-0.5 rounded-md font-medium" style={{ background: `${sev.c}22`, color: sev.c }}>{sev.label}</span>
          {issue.category && <span className="text-[10px] px-1.5 py-0.5 rounded-md" style={{ background: "#1E293B", color: "#94A3B8" }}>{issue.category}</span>}
        </div>
      </div>
      {issue.what_happened && (
        <p className="text-xs mb-1.5" style={{ color: "#CBD5E1" }}><span style={{ color: "#64748B" }}>What happened — </span>{issue.what_happened}</p>
      )}
      {issue.user_impact && (
        <p className="text-xs mb-1.5" style={{ color: "#CBD5E1" }}><span style={{ color: "#64748B" }}>Impact — </span>{issue.user_impact}</p>
      )}
      {issue.evidence && (
        <p className="text-[11px] font-mono mb-2 px-2 py-1 rounded" style={{ background: "#141B2E", color: "#94A3B8" }}>{issue.evidence}</p>
      )}
      {issue.recommendation && (
        <div className="flex items-start gap-2 text-xs rounded px-2 py-1.5" style={{ background: "#0f291f", color: "#6EE7B7" }}>
          <Wrench className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          <span>{issue.recommendation}</span>
        </div>
      )}
      {issue.affected_personas?.length > 0 && (
        <p className="text-[10px] mt-2" style={{ color: "#64748B" }}>Affected: {issue.affected_personas.join(", ")}</p>
      )}
    </div>
  );
}

function NarrativeReport({ report, onRegenerate, regenerating }) {
  const achieved = report.goal_achieved;
  return (
    <div>
      <div className="rounded-xl p-4 mb-4" style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            {achieved != null && (
              <span className="text-[10px] px-2 py-0.5 rounded-md font-medium" style={{ background: achieved ? "#10B98122" : "#F43F5E22", color: achieved ? "#10B981" : "#F43F5E" }}>
                {achieved ? "Goal reached" : "Goal not reached"}
              </span>
            )}
            {report.persona_name && <span className="text-xs" style={{ color: "#94A3B8" }}>{report.persona_name}</span>}
            {report.persona_count && <span className="text-xs" style={{ color: "#94A3B8" }}>{report.persona_count} personas</span>}
          </div>
          <button type="button" onClick={onRegenerate} disabled={regenerating} className="flex items-center gap-1 text-[11px] hover:underline shrink-0" style={{ color: "#64748B" }}>
            <RefreshCw className={`w-3 h-3 ${regenerating ? "animate-spin" : ""}`} /> {regenerating ? "Regenerating…" : "Regenerate"}
          </button>
        </div>
        <p className="text-sm font-medium mt-2" style={{ color: "#F1F5F9" }}>{report.headline}</p>
        {report.summary && <p className="text-xs mt-1.5 leading-relaxed" style={{ color: "#94A3B8" }}>{report.summary}</p>}
      </div>

      {(report.issues || []).length > 0 ? (
        <>
          <h3 className="text-xs uppercase tracking-wider mb-3" style={{ color: "#64748B" }}>
            {report.issues.length} issue{report.issues.length !== 1 ? "s" : ""} to fix
          </h3>
          {report.issues.map((it, i) => <IssueCard key={i} issue={it} />)}
        </>
      ) : (
        <div className="rounded-lg p-4 text-xs" style={{ background: "#0f291f", color: "#6EE7B7", border: "0.5px solid #10B98133" }}>
          No product issues found for this persona — the journey was clean.
        </div>
      )}

      {(report.positives || []).length > 0 && (
        <div className="mt-4">
          <h3 className="text-xs uppercase tracking-wider mb-2" style={{ color: "#64748B" }}>What worked</h3>
          <ul className="space-y-1">
            {report.positives.map((p, i) => (
              <li key={i} className="text-xs flex gap-2" style={{ color: "#94A3B8" }}><Check className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: "#10B981" }} />{p}</li>
            ))}
          </ul>
        </div>
      )}

      {(report.noise_ignored || []).length > 0 && (
        <p className="text-[11px] mt-4" style={{ color: "#475569" }}>
          Excluded as third-party / telemetry noise: {report.noise_ignored.join("; ")}
        </p>
      )}
    </div>
  );
}

export default function Reports() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [batchId, setBatchId] = useState("");
  const [runIds, setRunIds] = useState("");
  const [runs, setRuns] = useState([]);
  const [loadingRuns, setLoadingRuns] = useState(true);

  const [selection, setSelection] = useState(null); // {kind:'run'|'batch'|'manual', id, label}
  const [narrative, setNarrative] = useState(null);
  const [narrLoading, setNarrLoading] = useState(false);
  const [narrError, setNarrError] = useState(null);
  const [regenerating, setRegenerating] = useState(false);

  const [raw, setRaw] = useState(null);
  const [showRaw, setShowRaw] = useState(false);

  const runReport = async (sel, refresh) => {
    setNarrError(null);
    if (refresh) setRegenerating(true); else { setNarrLoading(true); setNarrative(null); setRaw(null); }
    // Raw signal aggregate (fast) in parallel with the LLM narrative (slow)
    const aggParams =
      sel.kind === "batch" ? { batch_id: sel.id }
      : sel.kind === "run" ? { run_ids: sel.id }
      : sel.batchId ? { batch_id: sel.batchId } : { run_ids: sel.runIds };
    axios.get(`${API}/signals/aggregate`, { params: aggParams }).then((r) => setRaw(r.data)).catch(() => setRaw(null));

    try {
      let rep;
      if (sel.kind === "batch") rep = await getBatchReport(sel.id, refresh);
      else if (sel.kind === "run") rep = await getRunReport(sel.id, refresh);
      else if (sel.batchId) rep = await getBatchReport(sel.batchId, refresh);
      else {
        const first = (sel.runIds || "").split(",")[0].trim();
        rep = await getRunReport(first, refresh);
      }
      setNarrative(rep);
    } catch (e) {
      setNarrError(e?.response?.data?.detail || "Could not generate the report");
    } finally {
      setNarrLoading(false);
      setRegenerating(false);
    }
  };

  const open = (sel) => {
    setSelection(sel);
    setShowRaw(false);
    if (sel.kind === "batch") setSearchParams({ batch_id: sel.id });
    else if (sel.kind === "run") setSearchParams({ run_ids: sel.id });
    else if (sel.batchId) setSearchParams({ batch_id: sel.batchId });
    else setSearchParams({ run_ids: sel.runIds });
    runReport(sel, false);
  };

  const back = () => {
    setSelection(null);
    setNarrative(null);
    setRaw(null);
    setNarrError(null);
    setSearchParams({});
  };

  useEffect(() => {
    listRuns({ limit: 100 }).then(setRuns).catch(() => {}).finally(() => setLoadingRuns(false));
  }, []);

  // Deep link
  useEffect(() => {
    const bid = searchParams.get("batch_id");
    const rids = searchParams.get("run_ids");
    if (bid) open({ kind: "batch", id: bid });
    else if (rids && rids.includes(",")) open({ kind: "manual", runIds: rids });
    else if (rids) open({ kind: "run", id: rids });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { batches, standalone } = useMemo(() => {
    const byBatch = new Map();
    const solo = [];
    for (const r of runs) {
      if (r.batch_id) {
        if (!byBatch.has(r.batch_id)) byBatch.set(r.batch_id, { id: r.batch_id, stage: r.stage, goal: r.goal || "", started_at: r.started_at, runs: [], outcomes: {} });
        const b = byBatch.get(r.batch_id);
        b.runs.push(r);
        b.outcomes[r.outcome] = (b.outcomes[r.outcome] || 0) + 1;
      } else solo.push(r);
    }
    return {
      batches: Array.from(byBatch.values()).sort((a, b) => (b.started_at || "").localeCompare(a.started_at || "")),
      standalone: solo,
    };
  }, [runs]);

  return (
    <div data-testid={REPORTS.container}>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-medium" style={{ color: "#F1F5F9" }}>Reports</h1>
          <p className="text-sm mt-1" style={{ color: "#94A3B8" }}>What the synthetic users hit — and how to fix it</p>
        </div>
        {selection && (
          <Button onClick={back} variant="ghost" className="text-xs" style={{ color: "#94A3B8" }}>← Back to runs</Button>
        )}
      </div>

      {!selection && (
        <>
          <div className="rounded-xl p-4 mb-6" style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label className="text-[11px] uppercase tracking-wider mb-1 block" style={{ color: "#64748B" }}>Batch ID</label>
                <Input value={batchId} onChange={(e) => setBatchId(e.target.value)} placeholder="Paste batch ID" className="h-9 rounded-lg text-sm font-mono" style={{ background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" }} />
              </div>
              <div>
                <label className="text-[11px] uppercase tracking-wider mb-1 block" style={{ color: "#64748B" }}>Or run IDs (comma-separated)</label>
                <Input value={runIds} onChange={(e) => setRunIds(e.target.value)} placeholder="run1, run2, ..." className="h-9 rounded-lg text-sm font-mono" style={{ background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" }} />
              </div>
              <div className="flex items-end">
                <Button
                  data-testid="reports-aggregate-btn"
                  onClick={() => batchId.trim() ? open({ kind: "batch", id: batchId.trim() }) : open({ kind: "manual", runIds: runIds.trim() })}
                  disabled={!batchId.trim() && !runIds.trim()}
                  className="rounded-lg h-9 w-full"
                  style={{ background: "#2DD4BF", color: "#06231F" }}
                >
                  Open report
                </Button>
              </div>
            </div>
          </div>

          {loadingRuns && <Spinner />}
          {!loadingRuns && batches.length === 0 && standalone.length === 0 && (
            <EmptyState icon={FileText} title="No runs yet" description="Start a run, then come back to see its report" />
          )}

          {batches.length > 0 && (
            <div className="mb-6">
              <h2 className="text-xs uppercase tracking-wider mb-3 flex items-center gap-1.5" style={{ color: "#64748B" }}><Layers className="w-3 h-3" /> Batches</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {batches.map((b) => (
                  <button key={b.id} onClick={() => open({ kind: "batch", id: b.id })} className="rounded-lg p-3 text-left transition-colors hover:border-[#334155] w-full" style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] uppercase tracking-wider" style={{ color: "#64748B" }}>{b.stage}</span>
                      <CopyButton text={b.id} />
                    </div>
                    <p className="text-xs truncate mb-2" style={{ color: "#F1F5F9" }}>{b.goal || "No goal"}</p>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10px] shrink-0" style={{ color: "#64748B" }}>{b.runs.length} run{b.runs.length !== 1 ? "s" : ""}</span>
                      <OutcomePills counts={b.outcomes} />
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {standalone.length > 0 && (
            <div>
              <h2 className="text-xs uppercase tracking-wider mb-3 flex items-center gap-1.5" style={{ color: "#64748B" }}><User className="w-3 h-3" /> Individual runs</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {standalone.map((r) => (
                  <button key={r.id} onClick={() => open({ kind: "run", id: r.id })} className="rounded-lg p-3 text-left transition-colors hover:border-[#334155] w-full" style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium truncate" style={{ color: "#F1F5F9" }}>{r.persona?.name || "Unknown"}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded shrink-0" style={{ background: `${OUTCOME_COLORS[r.outcome] || "#64748B"}20`, color: OUTCOME_COLORS[r.outcome] || "#64748B" }}>
                        {(r.outcome || "").replace("_", " ")}
                      </span>
                    </div>
                    <p className="text-xs truncate" style={{ color: "#94A3B8" }}>{r.goal || r.target || "—"}</p>
                    <div className="flex items-center justify-between mt-2">
                      <span className="text-[10px] uppercase tracking-wider" style={{ color: "#64748B" }}>{r.stage}</span>
                      <CopyButton text={r.id} />
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {selection && (
        <div>
          {narrLoading && (
            <div className="rounded-xl p-6 flex items-center gap-3" style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
              <RefreshCw className="w-4 h-4 animate-spin" style={{ color: "#2DD4BF" }} />
              <span className="text-sm" style={{ color: "#94A3B8" }}>Analyzing the run and writing the report… first time can take ~1 min, then it's cached.</span>
            </div>
          )}

          {narrError && <ErrorBanner message={narrError} onRetry={() => runReport(selection, false)} />}

          {narrative && !narrLoading && (
            <NarrativeReport report={narrative} onRegenerate={() => runReport(selection, true)} regenerating={regenerating} />
          )}

          {/* Raw technical signals — collapsible */}
          {(raw || narrative) && (
            <div className="mt-6">
              <button type="button" onClick={() => setShowRaw((v) => !v)} className="flex items-center gap-1.5 text-xs uppercase tracking-wider" style={{ color: "#64748B" }}>
                <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showRaw ? "" : "-rotate-90"}`} />
                Technical signals {raw ? `(${raw.total_screens} screens)` : ""}
              </button>
              {showRaw && (
                <div className="mt-3">
                  {raw && (raw.screens || []).length > 0 ? (
                    raw.screens.map((s, i) => <ScreenRow key={i} screen={s} />)
                  ) : (
                    <p className="text-xs" style={{ color: "#64748B" }}>No raw signals recorded.</p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
