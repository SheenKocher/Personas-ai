import { useEffect, useMemo, useRef, useState } from "react";
import { getEngineRun, pauseRun, resumeRun } from "@/lib/api";
import useRunSocket from "@/hooks/useRunSocket";
import { Pause, Play, MousePointerClick, Keyboard, Navigation, Clock, ArrowDown, AlertTriangle, Flag, XCircle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { toast } from "sonner";

const OUTCOME_COLORS = {
  in_progress: "#2DD4BF",
  success: "#10B981",
  gave_up: "#F43F5E",
  max_steps: "#F59E0B",
};

const ACTION_ICONS = {
  click: MousePointerClick,
  type: Keyboard,
  key: Keyboard,
  navigate: Navigation,
  scroll: ArrowDown,
  wait: Clock,
  report_friction: Flag,
  give_up: XCircle,
  intent: MousePointerClick, // prototype stage
};

function describeAction(action = {}) {
  switch (action.type) {
    case "click":
      return `Click "${action.selector || "?"}"`;
    case "type":
      return `Type "${(action.text || "").slice(0, 40)}" into ${action.selector || "?"}`;
    case "scroll":
      return `Scroll ${action.direction || "down"}${action.amount ? ` ${action.amount}px` : ""}`;
    case "navigate":
      return `Navigate → ${action.url || "?"}`;
    case "wait":
      return `Wait ${action.duration_ms || 0}ms`;
    case "key":
      return `Press ${action.key || "?"}`;
    case "report_friction":
      return `Reported friction: ${action.description || ""}`;
    case "give_up":
      return `Gave up: ${action.reason || ""}`;
    case "intent":
      return action.matched_transition
        ? `"${action.intent}" → ${action.matched_transition}`
        : `"${action.intent}" (no matching interaction)`;
    default:
      return action.type || "Unknown action";
  }
}

function StepCard({ step }) {
  const Icon = ACTION_ICONS[step.action?.type] || MousePointerClick;
  const failed = step.action_result && step.action_result.success === false;
  const rejected = step.action_rejected;
  const statusColor = rejected ? "#F59E0B" : failed ? "#F43F5E" : "#10B981";

  return (
    <div className="rounded-lg p-3" style={{ background: "#0B0F1A", border: "0.5px solid #1E293B" }}>
      <div className="flex items-start gap-2.5">
        <div
          className="w-6 h-6 rounded-md flex items-center justify-center shrink-0 mt-0.5"
          style={{ background: `${statusColor}20`, color: statusColor }}
        >
          <Icon className="w-3.5 h-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider" style={{ color: "#64748B" }}>
              Step {(step.index ?? 0) + 1}
            </span>
            <span
              className="text-[9px] px-1.5 py-0.5 rounded-md font-medium"
              style={{ background: `${statusColor}15`, color: statusColor }}
            >
              {rejected ? "rejected" : failed ? "failed" : "ok"}
            </span>
          </div>
          <p className="text-xs mt-1 break-words" style={{ color: "#F1F5F9" }}>
            {describeAction(step.action)}
          </p>
          {step.reasoning && (
            <p className="text-xs mt-1.5 leading-relaxed italic break-words" style={{ color: "#94A3B8" }}>
              “{step.reasoning}”
            </p>
          )}
          {failed && step.action_result?.error && (
            <p className="text-[11px] mt-1 flex items-start gap-1" style={{ color: "#F43F5E" }}>
              <AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" />
              {step.action_result.error.slice(0, 200)}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Live activity feed for a single persona run: step-by-step action / result /
 * reasoning, plus pause/resume. Backfills from GET /api/engine/run/{id} on
 * mount, then streams new steps over the WS as they happen.
 */
export default function RunActivityFeed({ run, onRunUpdate }) {
  const runId = run?.id;
  const [detail, setDetail] = useState(null);
  const [steps, setSteps] = useState([]);
  const [pausing, setPausing] = useState(false);
  const { events, connected } = useRunSocket(runId);
  const seenSteps = useRef(new Set());
  const listRef = useRef(null);

  // Backfill
  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    getEngineRun(runId)
      .then((data) => {
        if (cancelled) return;
        setDetail(data);
        const initial = data.steps || [];
        initial.forEach((s) => seenSteps.current.add(s.index));
        setSteps(initial);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [runId]);

  // Apply live events on top of the backfill
  useEffect(() => {
    for (const evt of events) {
      if (evt.type === "step_update") {
        if (seenSteps.current.has(evt.step_index)) continue;
        seenSteps.current.add(evt.step_index);
        setSteps((prev) => [
          ...prev,
          {
            index: evt.step_index,
            action: evt.action,
            reasoning: evt.reasoning,
            location: evt.location,
            frustration_at_step: evt.frustration,
            action_result: { success: true },
            action_rejected: false,
          },
        ]);
        setDetail((prev) => (prev ? { ...prev, outcome: "in_progress" } : prev));
      } else if (evt.type === "run_complete") {
        setDetail((prev) => (prev ? { ...prev, outcome: evt.outcome, still_running: false } : prev));
        onRunUpdate?.({ outcome: evt.outcome });
      } else if (evt.type === "run_paused") {
        setDetail((prev) => (prev ? { ...prev, paused: true } : prev));
      } else if (evt.type === "run_resumed") {
        setDetail((prev) => (prev ? { ...prev, paused: false } : prev));
      }
    }
  }, [events, onRunUpdate]);

  // Auto-scroll to newest
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [steps.length]);

  const outcome = detail?.outcome || run?.outcome || "in_progress";
  const isRunning = outcome === "in_progress";
  const isPaused = !!detail?.paused;
  const frustrationBudget = run?.persona?.frustration_budget || 5;
  const currentFrustration = steps.length ? steps[steps.length - 1].frustration_at_step ?? 0 : 0;
  const maxSteps = 15;

  const orderedSteps = useMemo(() => [...steps].sort((a, b) => a.index - b.index), [steps]);

  const handleTogglePause = async () => {
    if (!runId) return;
    setPausing(true);
    try {
      if (isPaused) {
        await resumeRun(runId);
        setDetail((prev) => (prev ? { ...prev, paused: false } : prev));
      } else {
        await pauseRun(runId);
        setDetail((prev) => (prev ? { ...prev, paused: true } : prev));
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to update run state");
    } finally {
      setPausing(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          {isRunning && !isPaused && <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" style={{ color: "#2DD4BF" }} />}
          <span className="text-xs font-medium truncate" style={{ color: "#F1F5F9" }}>
            {orderedSteps.length}/{maxSteps} steps
          </span>
          <span
            className="text-[10px] px-1.5 py-0.5 rounded-md font-medium shrink-0"
            style={{ background: `${OUTCOME_COLORS[outcome]}15`, color: OUTCOME_COLORS[outcome] }}
          >
            {isPaused ? "Paused" : outcome.replace("_", " ")}
          </span>
          {!connected && isRunning && (
            <span className="text-[10px]" style={{ color: "#64748B" }}>reconnecting…</span>
          )}
        </div>
        {isRunning && (
          <Button
            size="sm"
            variant="outline"
            disabled={pausing}
            onClick={handleTogglePause}
            className="h-7 rounded-md text-xs gap-1.5 shrink-0"
            style={{ borderColor: "#334155", color: "#F1F5F9", background: "transparent" }}
          >
            {isPaused ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
            {isPaused ? "Resume" : "Pause"}
          </Button>
        )}
      </div>

      {/* Frustration meter */}
      <div className="mb-3">
        <div className="flex items-center justify-between text-[10px] mb-1" style={{ color: "#64748B" }}>
          <span>Frustration</span>
          <span>{currentFrustration}/{frustrationBudget}</span>
        </div>
        <Progress
          value={Math.min(100, (currentFrustration / frustrationBudget) * 100)}
          className="h-1.5"
        />
      </div>

      {/* Feed */}
      <div ref={listRef} className="flex-1 min-h-0 overflow-y-auto space-y-2 pr-1">
        {orderedSteps.length === 0 ? (
          <div className="text-xs italic py-6 text-center" style={{ color: "#475569" }}>
            {isRunning ? "Waiting for the first step…" : "No steps recorded"}
          </div>
        ) : (
          orderedSteps.map((s) => <StepCard key={s.index} step={s} />)
        )}
      </div>
    </div>
  );
}
