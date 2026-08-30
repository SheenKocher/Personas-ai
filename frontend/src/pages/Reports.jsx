import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { listRuns } from "@/lib/api";
import { REPORTS } from "@/constants/testIds";
import { FileText, Activity, Copy, Check, Layers, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner, ErrorBanner, EmptyState } from "@/components/shared";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SEV_COLORS = { 1: "#FBBF24", 2: "#FBBF24", 3: "#F59E0B", 4: "#F43F5E", 5: "#F43F5E" };
const OUTCOME_COLORS = {
  success: "#10B981",
  gave_up: "#F43F5E",
  max_steps: "#F59E0B",
  in_progress: "#2DD4BF",
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
          <span
            className="text-[10px] px-1.5 py-0.5 rounded-md"
            style={{ background: `${SEV_COLORS[screen.max_severity] || "#64748B"}20`, color: SEV_COLORS[screen.max_severity] || "#64748B" }}
          >
            sev {screen.max_severity}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-3 text-[10px] mb-2" style={{ color: "#64748B" }}>
        <span>{screen.total_signals} signals</span>
        <span>{screen.affected_runs} run{screen.affected_runs !== 1 ? "s" : ""} affected</span>
        <span>{(screen.affected_personas || []).join(", ")}</span>
      </div>
      <div className="space-y-0.5">
        {(screen.signals || []).slice(0, 5).map((s, i) => (
          <div key={i} className="flex items-start gap-2 text-xs">
            <span
              className="w-4 h-4 shrink-0 rounded flex items-center justify-center text-[9px] font-medium mt-0.5"
              style={{ background: `${SEV_COLORS[s.severity] || "#64748B"}20`, color: SEV_COLORS[s.severity] || "#64748B" }}
            >
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
    <div className="flex items-center gap-1">
      {Object.entries(counts).map(([oc, n]) => (
        <span
          key={oc}
          className="text-[10px] px-1.5 py-0.5 rounded"
          style={{ background: `${OUTCOME_COLORS[oc] || "#64748B"}20`, color: OUTCOME_COLORS[oc] || "#64748B" }}
        >
          {n} {oc.replace("_", " ")}
        </span>
      ))}
    </div>
  );
}

export default function Reports() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [batchId, setBatchId] = useState("");
  const [runIds, setRunIds] = useState("");
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState(null);
  const [reportLabel, setReportLabel] = useState("");
  const [error, setError] = useState(null);
  const [runs, setRuns] = useState([]);
  const [loadingRuns, setLoadingRuns] = useState(true);

  const handleAggregate = async (bid, rids, label) => {
    setLoading(true);
    setError(null);
    setReport(null);
    setReportLabel(label || "");
    try {
      const params = {};
      if (bid) params.batch_id = bid;
      if (rids) params.run_ids = rids;
      const res = await axios.get(`${API}/signals/aggregate`, { params });
      setReport(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Aggregation failed");
    } finally {
      setLoading(false);
    }
  };

  // Load recent runs for the pick-list
  useEffect(() => {
    listRuns({ limit: 100 })
      .then(setRuns)
      .catch(() => {})
      .finally(() => setLoadingRuns(false));
  }, []);

  // Deep-link: /reports?batch_id=... or /reports?run_ids=...
  useEffect(() => {
    const bid = searchParams.get("batch_id");
    const rids = searchParams.get("run_ids");
    if (bid) {
      setBatchId(bid);
      handleAggregate(bid, "", `batch ${bid.slice(0, 8)}…`);
    } else if (rids) {
      setRunIds(rids);
      handleAggregate("", rids, `${rids.split(",").length} run(s)`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Group runs into batches + standalone
  const { batches, standalone } = useMemo(() => {
    const byBatch = new Map();
    const solo = [];
    for (const r of runs) {
      if (r.batch_id) {
        if (!byBatch.has(r.batch_id)) {
          byBatch.set(r.batch_id, {
            id: r.batch_id,
            stage: r.stage,
            goal: r.goal || "",
            started_at: r.started_at,
            runs: [],
            outcomes: {},
          });
        }
        const b = byBatch.get(r.batch_id);
        b.runs.push(r);
        b.outcomes[r.outcome] = (b.outcomes[r.outcome] || 0) + 1;
      } else {
        solo.push(r);
      }
    }
    return {
      batches: Array.from(byBatch.values()).sort((a, b) => (b.started_at || "").localeCompare(a.started_at || "")),
      standalone: solo,
    };
  }, [runs]);

  const openReport = (bid, rids, label) => {
    setSearchParams(bid ? { batch_id: bid } : { run_ids: rids });
    handleAggregate(bid, rids, label);
  };

  const clearReport = () => {
    setReport(null);
    setError(null);
    setReportLabel("");
    setSearchParams({});
  };

  return (
    <div data-testid={REPORTS.container}>
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-medium" style={{ color: "#F1F5F9" }}>Reports</h1>
          <p className="text-sm mt-1" style={{ color: "#94A3B8" }}>Aggregated friction analysis ranked by worst screens</p>
        </div>
        {report && (
          <Button onClick={clearReport} variant="ghost" className="text-xs" style={{ color: "#94A3B8" }}>
            ← Back to runs
          </Button>
        )}
      </div>

      {!report && (
        <>
          {/* Manual query bar (fallback) */}
          <div className="rounded-xl p-4 mb-6" style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label className="text-[11px] uppercase tracking-wider mb-1 block" style={{ color: "#64748B" }}>Batch ID</label>
                <Input
                  value={batchId}
                  onChange={(e) => setBatchId(e.target.value)}
                  placeholder="Paste batch ID"
                  className="h-9 rounded-lg text-sm font-mono"
                  style={{ background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" }}
                />
              </div>
              <div>
                <label className="text-[11px] uppercase tracking-wider mb-1 block" style={{ color: "#64748B" }}>Or run IDs (comma-separated)</label>
                <Input
                  value={runIds}
                  onChange={(e) => setRunIds(e.target.value)}
                  placeholder="run1, run2, ..."
                  className="h-9 rounded-lg text-sm font-mono"
                  style={{ background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" }}
                />
              </div>
              <div className="flex items-end">
                <Button
                  data-testid="reports-aggregate-btn"
                  onClick={() => openReport(batchId.trim(), runIds.trim(), batchId.trim() ? "batch" : "runs")}
                  disabled={loading || (!batchId.trim() && !runIds.trim())}
                  className="rounded-lg h-9 w-full"
                  style={{ background: "#2DD4BF", color: "#06231F" }}
                >
                  {loading ? "Loading..." : "Aggregate signals"}
                </Button>
              </div>
            </div>
          </div>

          {loadingRuns && <Spinner />}

          {!loadingRuns && batches.length === 0 && standalone.length === 0 && (
            <EmptyState icon={FileText} title="No runs yet" description="Start a run, then come back to see its friction report" />
          )}

          {/* Batches */}
          {batches.length > 0 && (
            <div className="mb-6">
              <h2 className="text-xs uppercase tracking-wider mb-3 flex items-center gap-1.5" style={{ color: "#64748B" }}>
                <Layers className="w-3 h-3" /> Batches
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {batches.map((b) => (
                  <button
                    key={b.id}
                    onClick={() => openReport(b.id, "", `batch ${b.id.slice(0, 8)}…`)}
                    className="rounded-lg p-3 text-left transition-colors hover:border-[#334155] w-full"
                    style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] uppercase tracking-wider" style={{ color: "#64748B" }}>{b.stage}</span>
                      <CopyButton text={b.id} />
                    </div>
                    <p className="text-xs truncate mb-2" style={{ color: "#F1F5F9" }}>{b.goal || "No goal"}</p>
                    <div className="flex items-center justify-between">
                      <span className="text-[10px]" style={{ color: "#64748B" }}>{b.runs.length} run{b.runs.length !== 1 ? "s" : ""}</span>
                      <OutcomePills counts={b.outcomes} />
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Standalone runs */}
          {standalone.length > 0 && (
            <div>
              <h2 className="text-xs uppercase tracking-wider mb-3 flex items-center gap-1.5" style={{ color: "#64748B" }}>
                <User className="w-3 h-3" /> Individual runs
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {standalone.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => openReport("", r.id, r.persona?.name || "run")}
                    className="rounded-lg p-3 text-left transition-colors hover:border-[#334155] w-full"
                    style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium truncate" style={{ color: "#F1F5F9" }}>{r.persona?.name || "Unknown"}</span>
                      <span
                        className="text-[10px] px-1.5 py-0.5 rounded shrink-0"
                        style={{ background: `${OUTCOME_COLORS[r.outcome] || "#64748B"}20`, color: OUTCOME_COLORS[r.outcome] || "#64748B" }}
                      >
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

      {error && <ErrorBanner message={error} onRetry={() => handleAggregate(batchId.trim(), runIds.trim(), reportLabel)} />}

      {report && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-medium" style={{ color: "#F1F5F9" }}>
                {report.total_screens} screen{report.total_screens !== 1 ? "s" : ""} with signals
              </h2>
              {reportLabel && <p className="text-xs mt-0.5" style={{ color: "#64748B" }}>{reportLabel}</p>}
            </div>
          </div>
          {(report.screens || []).length > 0 ? (
            report.screens.map((s, i) => <ScreenRow key={i} screen={s} />)
          ) : (
            <EmptyState icon={Activity} title="No signals found" description="This run/batch has no recorded friction signals" />
          )}
        </div>
      )}
    </div>
  );
}
