import { useEffect, useRef, useState } from "react";
import { listRuns, listPersonaPanels } from "@/lib/api";
import { LIVE_GRID } from "@/constants/testIds";
import { Grid3X3, Eye, EyeOff, Keyboard, ZoomIn, Brain, Radio } from "lucide-react";
import { Spinner, ErrorBanner, EmptyState } from "@/components/shared";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import LiveRunView from "@/components/LiveRunView";
import RunActivityFeed from "@/components/RunActivityFeed";

const disabilityIcons = {
  motor: Keyboard,
  blind: EyeOff,
  low_vision: ZoomIn,
  cognitive: Brain,
};

const outcomeStyles = {
  in_progress: { color: "#2DD4BF", label: "Running" },
  success: { color: "#10B981", label: "Succeeded" },
  gave_up: { color: "#F43F5E", label: "Gave Up" },
  max_steps: { color: "#F59E0B", label: "Max Steps" },
};

function PersonaTile({ persona, index }) {
  const isScreenReader = persona.perception_mode === "ax_tree_only";
  const DisabilityIcon = persona.disability ? disabilityIcons[persona.disability] : Eye;
  const accentColor = persona.accent_color || "#818CF8";

  return (
    <div
      data-testid={`${LIVE_GRID.personaTile}-${index}`}
      className="rounded-xl overflow-hidden transition-colors"
      style={{ background: "#141B2E", border: `1px solid ${accentColor}` }}
    >
      <div className="h-48 relative flex items-center justify-center">
        {isScreenReader ? (
          <div className="mono-block w-full h-full overflow-auto p-3 text-xs leading-relaxed">
            <div style={{ color: "#64748B" }}>// AX-tree transcript</div>
            <div style={{ color: "#94A3B8" }}>{"<main role=\"main\">"}</div>
            <div style={{ color: "#94A3B8" }} className="pl-4">{"<heading level=1> Page Title"}</div>
            <div style={{ color: "#94A3B8" }} className="pl-4">{"<button> Submit Form"}</div>
            <div style={{ color: "#94A3B8" }} className="pl-4">{"<textbox> Enter email..."}</div>
            <div style={{ color: "#64748B" }}>// awaiting run data</div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2">
            <div
              className="w-16 h-16 rounded-lg flex items-center justify-center"
              style={{ background: `${accentColor}15` }}
            >
              {DisabilityIcon && <DisabilityIcon className="w-7 h-7" style={{ color: accentColor }} />}
            </div>
            <span className="text-xs" style={{ color: "#64748B" }}>No active run</span>
          </div>
        )}
      </div>
      <div className="px-4 py-3" style={{ borderTop: "0.5px solid #1E293B" }}>
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium" style={{ color: "#F1F5F9" }}>{persona.name}</span>
          {persona.disability && (
            <span
              className="text-xs px-2 py-0.5 rounded-md"
              style={{ background: `${accentColor}15`, color: accentColor }}
            >
              {persona.disability}
            </span>
          )}
        </div>
        <p className="text-xs mt-1 truncate" style={{ color: "#64748B" }}>{persona.traits}</p>
      </div>
    </div>
  );
}

function RunCard({ run, onClick }) {
  const outcome = outcomeStyles[run.outcome] || outcomeStyles.in_progress;
  const isRunning = run.outcome === "in_progress";
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={LIVE_GRID.runCard}
      className="text-left rounded-xl p-4 transition-colors hover:border-[#334155] w-full"
      style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium" style={{ color: "#F1F5F9" }}>
          {run.persona?.name || "Unknown Persona"}
        </span>
        <span
          className="text-xs px-2 py-0.5 rounded-md font-medium flex items-center gap-1"
          style={{ background: `${outcome.color}15`, color: outcome.color }}
        >
          {isRunning && <Radio className="w-3 h-3" />}
          {outcome.label}
        </span>
      </div>
      <div className="flex items-center gap-3 text-xs" style={{ color: "#64748B" }}>
        <span className="uppercase tracking-wider">{run.stage}</span>
        <span className="truncate">{run.target || "\u2014"}</span>
      </div>
      {run.goal && (
        <p className="text-xs mt-2 truncate" style={{ color: "#94A3B8" }}>{run.goal}</p>
      )}
      <p className="text-[10px] mt-2" style={{ color: "#475569" }}>
        {isRunning ? "Click to watch live \u2192" : "Click for session replay \u2192"}
      </p>
    </button>
  );
}

export default function LiveGrid() {
  const [panels, setPanels] = useState([]);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedRun, setSelectedRun] = useState(null);
  const pollRef = useRef(null);

  const load = ({ silent } = {}) => {
    if (!silent) setLoading(true);
    setError(null);
    Promise.all([listPersonaPanels(), listRuns()])
      .then(([p, r]) => { setPanels(p); setRuns(r); })
      .catch((e) => setError(e?.response?.data?.detail || "Failed to load data"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  // Auto-refresh the run list while any run is still in progress.
  useEffect(() => {
    const anyRunning = runs.some((r) => r.outcome === "in_progress");
    if (anyRunning && !pollRef.current) {
      pollRef.current = setInterval(() => load({ silent: true }), 5000);
    } else if (!anyRunning && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };
  }, [runs]);

  const allPersonas = panels.flatMap((p) => p.personas || []);

  if (loading) return <Spinner />;
  if (error) return <ErrorBanner message={error} onRetry={load} />;

  return (
    <div data-testid={LIVE_GRID.container}>
      <div className="mb-8">
        <h1 className="text-2xl font-medium" style={{ color: "#F1F5F9" }}>Live Grid</h1>
        <p className="text-sm mt-1" style={{ color: "#94A3B8" }}>Real-time persona activity overview</p>
      </div>

      {allPersonas.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 mb-10">
          {allPersonas.map((persona, i) => (
            <PersonaTile key={i} persona={persona} index={i} />
          ))}
        </div>
      ) : (
        <EmptyState icon={Grid3X3} title="No personas yet" description="Create a persona panel to populate the live grid" />
      )}

      <div className="mt-6">
        <h2 className="text-lg font-medium mb-4" style={{ color: "#F1F5F9" }}>Recent Runs</h2>
        {runs.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {runs.map((run) => (
              <RunCard key={run.id} run={run} onClick={() => setSelectedRun(run)} />
            ))}
          </div>
        ) : (
          <div
            className="rounded-xl flex flex-col items-center justify-center py-12"
            style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
          >
            <p className="text-sm" style={{ color: "#64748B" }}>No runs yet. Start a new run to see activity here.</p>
          </div>
        )}
      </div>

      <Dialog open={!!selectedRun} onOpenChange={(o) => !o && setSelectedRun(null)}>
        <DialogContent
          className="max-w-5xl"
          style={{ background: "#141B2E", border: "0.5px solid #1E293B", color: "#F1F5F9" }}
        >
          <DialogHeader>
            <DialogTitle className="text-sm font-medium">
              {selectedRun?.persona?.name || "Run"} — {selectedRun?.goal || selectedRun?.target}
            </DialogTitle>
          </DialogHeader>
          {selectedRun && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" style={{ height: "60vh" }}>
              <div className="min-h-0 overflow-y-auto pr-1">
                <LiveRunView runId={selectedRun.id} stage={selectedRun.stage} />
              </div>
              <div className="min-h-0">
                <RunActivityFeed
                  run={selectedRun}
                  onRunUpdate={(patch) => setSelectedRun((r) => (r ? { ...r, ...patch } : r))}
                />
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
