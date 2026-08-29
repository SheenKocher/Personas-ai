import { useEffect, useState } from "react";
import { listRuns } from "@/lib/api";
import { REPORTS } from "@/constants/testIds";
import { FileText, AlertTriangle, Activity } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner, ErrorBanner, EmptyState } from "@/components/shared";
import axios from "axios";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SEV_COLORS = { 1: "#FBBF24", 2: "#FBBF24", 3: "#F59E0B", 4: "#F43F5E", 5: "#F43F5E" };

function ScreenRow({ screen }) {
  return (
    <div className="rounded-lg p-3 mb-2" style={{ background: "#0B0F1A", border: "0.5px solid #1E293B" }}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-sm font-medium truncate" style={{ color: "#F1F5F9" }}>{screen.screen}</span>
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-xs tabular-nums" style={{ color: "#F1F5F9" }}>
            Score: {screen.weighted_score}
          </span>
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

export default function Reports() {
  const [batchId, setBatchId] = useState("");
  const [runIds, setRunIds] = useState("");
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [recentBatches, setRecentBatches] = useState([]);
  const [loadingBatches, setLoadingBatches] = useState(true);

  // Load recent runs to extract batch IDs
  useEffect(() => {
    listRuns({ limit: 50 })
      .then((runs) => {
        const batches = {};
        for (const r of runs) {
          const bid = r.batch_id;
          if (!bid) continue;
          if (!batches[bid]) batches[bid] = { id: bid, goal: r.goal || "", stage: r.stage, count: 0, outcome: r.outcome };
          batches[bid].count += 1;
        }
        setRecentBatches(Object.values(batches).slice(0, 10));
      })
      .catch(() => {})
      .finally(() => setLoadingBatches(false));
  }, []);

  const handleAggregate = async (bid, rids) => {
    setLoading(true);
    setError(null);
    setReport(null);
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

  return (
    <div data-testid={REPORTS.container}>
      <div className="mb-6">
        <h1 className="text-2xl font-medium" style={{ color: "#F1F5F9" }}>Reports</h1>
        <p className="text-sm mt-1" style={{ color: "#94A3B8" }}>Aggregated friction analysis ranked by worst screens</p>
      </div>

      {/* Query bar */}
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
              onClick={() => handleAggregate(batchId.trim(), runIds.trim())}
              disabled={loading || (!batchId.trim() && !runIds.trim())}
              className="rounded-lg h-9 w-full"
              style={{ background: "#2DD4BF", color: "#06231F" }}
            >
              {loading ? "Loading..." : "Aggregate signals"}
            </Button>
          </div>
        </div>
      </div>

      {/* Recent batches for quick access */}
      {!report && loadingBatches && <Spinner />}
      {!report && !loadingBatches && recentBatches.length > 0 && (
        <div className="mb-6">
          <h2 className="text-xs uppercase tracking-wider mb-3" style={{ color: "#64748B" }}>Recent batches</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {recentBatches.map((b) => (
              <button
                key={b.id}
                onClick={() => { setBatchId(b.id); handleAggregate(b.id, ""); }}
                className="rounded-lg p-3 text-left transition-colors hover:border-[#334155]"
                style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-mono truncate" style={{ color: "#94A3B8" }}>{b.id.slice(0, 12)}...</span>
                  <span className="text-[10px] uppercase tracking-wider" style={{ color: "#64748B" }}>{b.stage}</span>
                </div>
                <p className="text-xs truncate" style={{ color: "#F1F5F9" }}>{b.goal || "No goal"}</p>
                <span className="text-[10px]" style={{ color: "#64748B" }}>{b.count} run{b.count !== 1 ? "s" : ""}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Error */}
      {error && <ErrorBanner message={error} onRetry={() => handleAggregate(batchId.trim(), runIds.trim())} />}

      {/* Report */}
      {report && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-medium" style={{ color: "#F1F5F9" }}>
              {report.total_screens} screen{report.total_screens !== 1 ? "s" : ""} with signals
            </h2>
          </div>
          {(report.screens || []).length > 0 ? (
            report.screens.map((s, i) => <ScreenRow key={i} screen={s} />)
          ) : (
            <EmptyState icon={Activity} title="No signals found" description="This batch has no recorded friction signals" />
          )}
        </div>
      )}

      {/* Empty state */}
      {!report && !loading && !error && !loadingBatches && recentBatches.length === 0 && (
        <EmptyState
          icon={FileText}
          title="No reports yet"
          description="Reports appear after completed test runs with signals"
        />
      )}
    </div>
  );
}
