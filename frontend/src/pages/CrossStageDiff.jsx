import { useEffect, useState } from "react";
import { DIFF } from "@/constants/testIds";
import {
  GitCompareArrows, AlertTriangle, CheckCircle, ArrowUpRight,
  ArrowDownRight, Minus, Plus, ChevronDown, ChevronUp, Search,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const VERDICT_CONFIG = {
  regression:         { color: "#F43F5E", bg: "#F43F5E15", icon: ArrowUpRight, label: "Regression", desc: "Worse in runtime" },
  improvement:        { color: "#10B981", bg: "#10B98115", icon: ArrowDownRight, label: "Improved",   desc: "Better in runtime" },
  unchanged:          { color: "#64748B", bg: "#64748B15", icon: Minus,          label: "Unchanged",  desc: "Same friction level" },
  clean:              { color: "#2DD4BF", bg: "#2DD4BF15", icon: CheckCircle,    label: "Clean",      desc: "No signals in either stage" },
  new_in_runtime:     { color: "#F59E0B", bg: "#F59E0B15", icon: Plus,           label: "New",        desc: "Only appeared in runtime" },
  missing_in_runtime: { color: "#94A3B8", bg: "#94A3B815", icon: Minus,          label: "Removed",    desc: "Only in prototype" },
};

const OUTCOME_COLORS = {
  success: "#10B981", gave_up: "#F43F5E", max_steps: "#F59E0B", in_progress: "#2DD4BF",
};

const SEV_COLORS = {
  1: "#FBBF24", 2: "#FBBF24", 3: "#F59E0B", 4: "#F43F5E", 5: "#F43F5E",
};

const CHANGE_LABELS = {
  new_in_runtime: { color: "#F43F5E", label: "New in runtime" },
  fixed_in_runtime: { color: "#10B981", label: "Fixed in runtime" },
  severity_changed: { color: "#F59E0B", label: "Severity changed" },
};


/* ── Summary pill ── */
function SummaryPill({ count, label, color }) {
  return (
    <div className="flex items-center gap-2 rounded-lg px-4 py-3" style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
      <span className="text-2xl font-medium tabular-nums" style={{ color }}>{count}</span>
      <span className="text-xs" style={{ color: "#94A3B8" }}>{label}</span>
    </div>
  );
}

/* ── Persona outcome row ── */
function OutcomeRow({ name, proto, runtime }) {
  const protoColor = OUTCOME_COLORS[proto] || "#64748B";
  const runtimeColor = OUTCOME_COLORS[runtime] || "#64748B";
  const changed = proto !== runtime && proto !== "—" && runtime !== "—";
  return (
    <div className="flex items-center gap-3 text-xs py-1.5" style={{ borderBottom: "0.5px solid #1E293B" }}>
      <span className="flex-1 truncate" style={{ color: "#F1F5F9" }}>{name}</span>
      <span className="w-20 text-center rounded-md px-2 py-0.5" style={{ background: `${protoColor}15`, color: protoColor }}>
        {proto || "—"}
      </span>
      <span style={{ color: "#475569" }}>{"\u2192"}</span>
      <span className="w-20 text-center rounded-md px-2 py-0.5" style={{ background: `${runtimeColor}15`, color: runtimeColor }}>
        {runtime || "—"}
      </span>
      {changed && (
        <span className="w-5">
          {OUTCOME_COLORS[runtime] === "#F43F5E" ? (
            <AlertTriangle className="w-3.5 h-3.5" style={{ color: "#F43F5E" }} />
          ) : OUTCOME_COLORS[runtime] === "#10B981" ? (
            <CheckCircle className="w-3.5 h-3.5" style={{ color: "#10B981" }} />
          ) : null}
        </span>
      )}
    </div>
  );
}


/* ── Signal line ── */
function SignalLine({ signal, side }) {
  const sevColor = SEV_COLORS[signal.severity] || "#64748B";
  return (
    <div className="flex items-start gap-2 py-1">
      <span
        className="shrink-0 w-5 h-5 rounded flex items-center justify-center text-[10px] font-medium mt-0.5"
        style={{ background: `${sevColor}20`, color: sevColor }}
      >
        {signal.severity}
      </span>
      <span className="text-xs leading-relaxed" style={{ color: "#94A3B8" }}>
        {signal.description}
      </span>
    </div>
  );
}

/* ── Change line ── */
function ChangeLine({ change }) {
  const cfg = CHANGE_LABELS[change.change] || { color: "#94A3B8", label: change.change };
  return (
    <div className="flex items-start gap-2 py-1">
      <span
        className="shrink-0 text-[9px] uppercase tracking-wider rounded-md px-1.5 py-0.5 font-medium mt-0.5"
        style={{ background: `${cfg.color}15`, color: cfg.color }}
      >
        {cfg.label}
      </span>
      <span className="text-xs leading-relaxed" style={{ color: "#F1F5F9" }}>
        {change.description}
        {change.change === "severity_changed" && (
          <span className="ml-1" style={{ color: "#64748B" }}>
            ({change.old_severity} {"\u2192"} {change.new_severity})
          </span>
        )}
      </span>
    </div>
  );
}


/* ── Screen diff card ── */
function ScreenDiffCard({ data }) {
  const [expanded, setExpanded] = useState(data.verdict === "regression");
  const vc = VERDICT_CONFIG[data.verdict] || VERDICT_CONFIG.unchanged;
  const VerdictIcon = vc.icon;
  const deltaSign = data.delta_score > 0 ? "+" : "";
  const hasChanges = data.changed_signals?.length > 0;

  return (
    <div
      data-testid={`diff-screen-${data.screen}`}
      className="rounded-xl overflow-hidden"
      style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
    >
      {/* Header */}
      <button
        className="w-full flex items-center gap-3 px-5 py-4 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: vc.bg }}>
          <VerdictIcon className="w-4 h-4" style={{ color: vc.color }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium truncate" style={{ color: "#F1F5F9" }}>
              {data.screen}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-md font-medium shrink-0" style={{ background: vc.bg, color: vc.color }}>
              {vc.label}
            </span>
          </div>
          <span className="text-xs" style={{ color: "#64748B" }}>{vc.desc}</span>
        </div>
        {/* Score comparison */}
        <div className="flex items-center gap-4 shrink-0">
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-wider" style={{ color: "#64748B" }}>Proto</div>
            <div className="text-sm tabular-nums" style={{ color: "#818CF8" }}>{data.prototype.weighted_score}</div>
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-wider" style={{ color: "#64748B" }}>Runtime</div>
            <div className="text-sm tabular-nums" style={{ color: "#2DD4BF" }}>{data.runtime.weighted_score}</div>
          </div>
          {data.delta_score !== 0 && (
            <span
              className="text-xs font-medium tabular-nums px-1.5 py-0.5 rounded-md"
              style={{
                background: data.delta_score > 0 ? "#F43F5E15" : "#10B98115",
                color: data.delta_score > 0 ? "#F43F5E" : "#10B981",
              }}
            >
              {deltaSign}{data.delta_score}
            </span>
          )}
          {expanded ? <ChevronUp className="w-4 h-4" style={{ color: "#475569" }} /> : <ChevronDown className="w-4 h-4" style={{ color: "#475569" }} />}
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="px-5 pb-5 pt-0" style={{ borderTop: "0.5px solid #1E293B" }}>
          {/* Changed signals — the headline */}
          {hasChanges && (
            <div className="mb-4 pt-3">
              <h4 className="text-xs uppercase tracking-wider mb-2" style={{ color: "#F1F5F9" }}>
                What changed
              </h4>
              <div className="rounded-lg p-3" style={{ background: "#0B0F1A", border: "0.5px solid #1E293B" }}>
                {data.changed_signals.map((c, i) => <ChangeLine key={i} change={c} />)}
              </div>
            </div>
          )}

          {/* Side-by-side signals */}
          <div className="grid grid-cols-2 gap-4 pt-2">
            <div>
              <h4 className="text-[10px] uppercase tracking-wider mb-2 flex items-center gap-1.5" style={{ color: "#818CF8" }}>
                <span className="w-2 h-2 rounded-full" style={{ background: "#818CF8" }} />
                Prototype ({data.prototype.signal_count} signals)
              </h4>
              <div className="space-y-0.5">
                {data.prototype.signals.length > 0 ? (
                  data.prototype.signals.map((s, i) => <SignalLine key={i} signal={s} side="proto" />)
                ) : (
                  <span className="text-xs italic" style={{ color: "#475569" }}>No signals</span>
                )}
              </div>
            </div>
            <div>
              <h4 className="text-[10px] uppercase tracking-wider mb-2 flex items-center gap-1.5" style={{ color: "#2DD4BF" }}>
                <span className="w-2 h-2 rounded-full" style={{ background: "#2DD4BF" }} />
                Runtime ({data.runtime.signal_count} signals)
              </h4>
              <div className="space-y-0.5">
                {data.runtime.signals.length > 0 ? (
                  data.runtime.signals.map((s, i) => <SignalLine key={i} signal={s} side="runtime" />)
                ) : (
                  <span className="text-xs italic" style={{ color: "#475569" }}>No signals</span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


/* ══════════════════════════════════════════════
   Page: Cross-Stage Diff — Regression Report
   ══════════════════════════════════════════════ */
export default function CrossStageDiff() {
  const [goal, setGoal] = useState("");
  const [protoBatchId, setProtoBatchId] = useState("");
  const [runtimeBatchId, setRuntimeBatchId] = useState("");
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  const handleCompare = async () => {
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const params = {};
      if (goal.trim()) params.goal = goal.trim();
      if (protoBatchId.trim()) params.prototype_batch_id = protoBatchId.trim();
      if (runtimeBatchId.trim()) params.runtime_batch_id = runtimeBatchId.trim();
      const res = await axios.get(`${API}/diff`, { params });
      setReport(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to generate diff");
    } finally {
      setLoading(false);
    }
  };

  const summary = report?.summary;
  const personas = report?.outcomes_by_persona || {};

  return (
    <div data-testid={DIFF.container}>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-medium" style={{ color: "#F1F5F9" }}>
          Cross-Stage Diff
        </h1>
        <p className="text-sm mt-0.5" style={{ color: "#94A3B8" }}>
          Compare prototype vs. runtime — find regressions before your users do
        </p>
      </div>

      {/* Query bar */}
      <div
        className="rounded-xl p-4 mb-6"
        style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
      >
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="md:col-span-2">
            <label className="text-[11px] uppercase tracking-wider mb-1 block" style={{ color: "#64748B" }}>
              Goal (matches runs by goal text)
            </label>
            <Input
              data-testid="diff-goal-input"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder='e.g. "Find the pricing page"'
              className="h-9 rounded-lg text-sm"
              style={{ background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" }}
            />
          </div>
          <div>
            <label className="text-[11px] uppercase tracking-wider mb-1 block" style={{ color: "#64748B" }}>
              Prototype batch (optional)
            </label>
            <Input
              value={protoBatchId}
              onChange={(e) => setProtoBatchId(e.target.value)}
              placeholder="batch ID"
              className="h-9 rounded-lg text-sm font-mono"
              style={{ background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" }}
            />
          </div>
          <div className="flex items-end">
            <Button
              data-testid="diff-compare-btn"
              onClick={handleCompare}
              disabled={loading || (!goal.trim() && !protoBatchId.trim() && !runtimeBatchId.trim())}
              className="rounded-lg h-9 w-full"
              style={{ background: "#2DD4BF", color: "#06231F" }}
            >
              {loading ? (
                <span className="flex items-center gap-1.5">
                  <span className="w-3.5 h-3.5 border-2 rounded-full animate-spin" style={{ borderColor: "#06231F", borderTopColor: "transparent" }} />
                  Comparing...
                </span>
              ) : (
                <><Search className="w-4 h-4 mr-1.5" /> Compare stages</>
              )}
            </Button>
          </div>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="rounded-xl p-4 mb-6 flex items-center gap-3" style={{ background: "#F43F5E15", border: "0.5px solid #F43F5E30" }}>
          <AlertTriangle className="w-5 h-5 shrink-0" style={{ color: "#F43F5E" }} />
          <span className="text-sm" style={{ color: "#F43F5E" }}>{error}</span>
        </div>
      )}

      {/* Report */}
      {report && (
        <>
          {/* Goal + Summary */}
          <div className="mb-6">
            <div className="flex items-baseline gap-2 mb-4">
              <GitCompareArrows className="w-5 h-5" style={{ color: "#2DD4BF" }} />
              <h2 className="text-lg font-medium" style={{ color: "#F1F5F9" }}>
                {report.goal || "All runs"}
              </h2>
              <span className="text-xs" style={{ color: "#64748B" }}>
                {report.prototype_runs} prototype {"\u00b7"} {report.runtime_runs} runtime runs
              </span>
            </div>

            {/* Summary pills */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
              <SummaryPill count={summary.regressions} label="Regressions" color="#F43F5E" />
              <SummaryPill count={summary.improvements} label="Improvements" color="#10B981" />
              <SummaryPill count={summary.unchanged} label="Unchanged" color="#64748B" />
              <SummaryPill count={summary.total_screens} label="Screens compared" color="#F1F5F9" />
            </div>

            {/* Persona outcomes */}
            {Object.keys(personas).length > 0 && (
              <div className="rounded-xl p-4 mb-6" style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
                <h3 className="text-xs uppercase tracking-wider mb-3" style={{ color: "#64748B" }}>
                  Outcome by persona
                </h3>
                <div className="flex items-center gap-3 mb-2 text-[10px] uppercase tracking-wider" style={{ color: "#475569" }}>
                  <span className="flex-1">Persona</span>
                  <span className="w-20 text-center" style={{ color: "#818CF8" }}>Prototype</span>
                  <span className="w-4" />
                  <span className="w-20 text-center" style={{ color: "#2DD4BF" }}>Runtime</span>
                  <span className="w-5" />
                </div>
                {Object.entries(personas).map(([name, oc]) => (
                  <OutcomeRow key={name} name={name} proto={oc.prototype} runtime={oc.runtime} />
                ))}
              </div>
            )}
          </div>

          {/* Screen-by-screen diff cards */}
          <div className="space-y-3">
            <h3 className="text-xs uppercase tracking-wider" style={{ color: "#64748B" }}>
              Screen-by-screen comparison ({report.screens.length})
            </h3>
            {report.screens.map((s, i) => (
              <ScreenDiffCard key={i} data={s} />
            ))}
          </div>
        </>
      )}

      {/* Empty state — no report yet */}
      {!report && !loading && !error && (
        <div
          data-testid={DIFF.emptyState}
          className="rounded-xl flex flex-col items-center justify-center py-16"
          style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
        >
          <GitCompareArrows className="w-10 h-10 mb-3" style={{ color: "#334155" }} />
          <h2 className="text-sm font-medium mb-1" style={{ color: "#F1F5F9" }}>
            Enter a goal to compare stages
          </h2>
          <p className="text-xs" style={{ color: "#64748B" }}>
            The diff finds screens where prototype and runtime friction diverge
          </p>
        </div>
      )}
    </div>
  );
}
