import { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { listPersonaPanels } from "@/lib/api";
import {
  Upload, Plus, Trash2, ArrowRight, Play, Image as ImageIcon,
  RefreshCw, Eye, EyeOff, Keyboard, ZoomIn, Brain, Check,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import axios from "axios";
import { Spinner, ErrorBanner } from "@/components/shared";
import { usePaywall } from "@/hooks/usePaywall";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ACCENT_BY_DISABILITY = {
  standard: "#818CF8", motor: "#A78BFA", blind: "#38BDF8",
  low_vision: "#C084FC", cognitive: "#F472B6",
};

/* ── Screen node card ── */
function ScreenCard({ screen, isStart, onUpdate, onRemove, onSetStart, onUpload }) {
  const fileRef = useRef(null);
  const [uploading, setUploading] = useState(false);

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await axios.post(`${API}/prototype/upload-mockup`, form);
      onUpdate({ ...screen, image_url: res.data.url });
      toast.success(`Uploaded ${screen.name || screen.id}`);
    } catch { toast.error("Upload failed"); }
    finally { setUploading(false); }
  };

  return (
    <div
      data-testid={`screen-card-${screen.id}`}
      className="rounded-xl p-3 flex flex-col gap-2 min-w-[220px]"
      style={{
        background: "#141B2E",
        border: `0.5px solid ${isStart ? "#2DD4BF" : "#1E293B"}`,
      }}
    >
      {/* Image preview / upload zone */}
      <div
        className="h-32 rounded-lg overflow-hidden flex items-center justify-center cursor-pointer relative group"
        style={{ background: "#0B0F1A", border: "0.5px solid #1E293B" }}
        onClick={() => fileRef.current?.click()}
      >
        {screen.image_url ? (
          <>
            <img src={screen.image_url} alt={screen.name} className="w-full h-full object-cover" />
            <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
              <Upload className="w-5 h-5" style={{ color: "#F1F5F9" }} />
            </div>
          </>
        ) : uploading ? (
          <RefreshCw className="w-5 h-5 animate-spin" style={{ color: "#2DD4BF" }} />
        ) : (
          <div className="flex flex-col items-center gap-1">
            <Upload className="w-5 h-5" style={{ color: "#475569" }} />
            <span className="text-[10px]" style={{ color: "#475569" }}>Drop or click</span>
          </div>
        )}
        <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleFile} />
      </div>

      {/* Name + controls */}
      <div className="flex items-center gap-2">
        <Input
          value={screen.name}
          onChange={(e) => onUpdate({ ...screen, name: e.target.value })}
          className="h-7 text-xs rounded-md flex-1"
          style={{ background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" }}
          placeholder="Screen name"
        />
        <button
          onClick={onSetStart}
          title="Set as start screen"
          className="p-1 rounded"
          style={{ color: isStart ? "#2DD4BF" : "#475569" }}
        >
          <Play className="w-3.5 h-3.5" />
        </button>
        <button onClick={onRemove} className="p-1 rounded" style={{ color: "#F43F5E" }}>
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {isStart && (
        <span className="text-[9px] uppercase tracking-wider" style={{ color: "#2DD4BF" }}>
          start screen
        </span>
      )}
    </div>
  );
}

/* ── Transition row ── */
function TransitionRow({ t, screens, onUpdate, onRemove }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <Select value={t.from_screen} onValueChange={(v) => onUpdate({ ...t, from_screen: v })}>
        <SelectTrigger className="h-7 w-32 text-xs rounded" style={{ background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" }}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
          {screens.map((s) => <SelectItem key={s.id} value={s.id}>{s.name || s.id}</SelectItem>)}
        </SelectContent>
      </Select>
      <ArrowRight className="w-3.5 h-3.5 shrink-0" style={{ color: "#475569" }} />
      <Input
        value={t.label}
        onChange={(e) => onUpdate({ ...t, label: e.target.value })}
        placeholder='e.g. "click Pricing link"'
        className="h-7 text-xs rounded flex-1"
        style={{ background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" }}
      />
      <ArrowRight className="w-3.5 h-3.5 shrink-0" style={{ color: "#475569" }} />
      <Select value={t.to_screen} onValueChange={(v) => onUpdate({ ...t, to_screen: v })}>
        <SelectTrigger className="h-7 w-32 text-xs rounded" style={{ background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" }}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
          {screens.map((s) => <SelectItem key={s.id} value={s.id}>{s.name || s.id}</SelectItem>)}
        </SelectContent>
      </Select>
      <button onClick={onRemove} className="p-1 rounded" style={{ color: "#F43F5E" }}>
        <Trash2 className="w-3 h-3" />
      </button>
    </div>
  );
}


/* ══════════════════════════
   Page: Prototype Studio
   ══════════════════════════ */
export default function PrototypeStudio() {
  const navigate = useNavigate();
  const [graphs, setGraphs] = useState([]);
  const [activeGraphId, setActiveGraphId] = useState(null);
  const [graphName, setGraphName] = useState("New Flow");
  const [screens, setScreens] = useState([]);
  const [transitions, setTransitions] = useState([]);
  const [startScreen, setStartScreen] = useState("");
  const [panels, setPanels] = useState([]);
  const [panelId, setPanelId] = useState("");
  const [goal, setGoal] = useState("");
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [batchResult, setBatchResult] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const pollRef = useRef(null);
  const pollCountRef = useRef(0);
  const { canRun: paywallCanRun, PaywallGate } = usePaywall();

  // Cleanup polling on unmount
  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  useEffect(() => {
    setLoadError(null);
    Promise.all([
      axios.get(`${API}/prototype/graphs`).then((r) => setGraphs(r.data)),
      listPersonaPanels().then(setPanels),
    ]).catch((e) => setLoadError(e?.response?.data?.detail || "Failed to load data"));
  }, []);

  const loadGraph = (g) => {
    setActiveGraphId(g.id);
    setGraphName(g.name || "");
    setScreens(g.screens || []);
    setTransitions(g.transitions || []);
    setStartScreen(g.start_screen || "");
  };

  const addScreen = () => {
    const id = `screen_${Date.now()}`;
    const newScreen = { id, name: `Screen ${screens.length + 1}`, image_url: "" };
    setScreens([...screens, newScreen]);
    if (screens.length === 0) setStartScreen(id);
  };

  const updateScreen = (idx, updated) => {
    const next = [...screens]; next[idx] = updated; setScreens(next);
  };

  const removeScreen = (idx) => {
    const removed = screens[idx];
    setScreens(screens.filter((_, i) => i !== idx));
    setTransitions(transitions.filter((t) => t.from_screen !== removed.id && t.to_screen !== removed.id));
    if (startScreen === removed.id && screens.length > 1) {
      setStartScreen(screens.find((s, i) => i !== idx)?.id || "");
    }
  };

  const addTransition = () => {
    if (screens.length < 2) { toast.error("Add at least 2 screens first"); return; }
    setTransitions([...transitions, { from_screen: screens[0].id, label: "", to_screen: screens[1]?.id || screens[0].id }]);
  };

  const updateTransition = (idx, updated) => {
    const next = [...transitions]; next[idx] = updated; setTransitions(next);
  };

  const removeTransition = (idx) => setTransitions(transitions.filter((_, i) => i !== idx));

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = { name: graphName, screens, transitions, start_screen: startScreen };
      if (activeGraphId) {
        await axios.patch(`${API}/prototype/graphs/${activeGraphId}`, payload);
        toast.success("Graph updated");
      } else {
        const res = await axios.post(`${API}/prototype/graphs`, payload);
        setActiveGraphId(res.data.id);
        setGraphs((prev) => [res.data, ...prev]);
        toast.success("Graph saved");
      }
    } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };

  const handleRun = async () => {
    if (!activeGraphId) { toast.error("Save the graph first"); return; }
    if (!goal.trim()) { toast.error("Enter a goal"); return; }
    setRunning(true);
    setBatchResult(null);
    try {
      const body = { graph_id: activeGraphId, goal };
      if (panelId) body.persona_panel_id = panelId;
      const res = await axios.post(`${API}/prototype/run`, body);
      const batchId = res.data.batch_id;
      toast.success(`Prototype run started: ${res.data.persona_count} personas`);
      // Poll with timeout
      pollCountRef.current = 0;
      pollRef.current = setInterval(async () => {
        pollCountRef.current += 1;
        // Timeout after ~4 minutes (30 polls * 8s)
        if (pollCountRef.current > 30) {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setRunning(false);
          toast.error("Run timed out — check results on the Live Grid page");
          return;
        }
        try {
          const status = await axios.get(`${API}/engine/batch/${batchId}`);
          if (status.data.all_done) {
            clearInterval(pollRef.current);
            pollRef.current = null;
            setBatchResult(status.data);
            setRunning(false);
          }
        } catch {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setRunning(false);
          toast.error("Failed to check run status");
        }
      }, 8000);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Run failed");
      setRunning(false);
    }
  };

  const canRun = screens.length > 0 && transitions.length > 0 && goal.trim() && paywallCanRun;

  return (
    <div data-testid="prototype-studio-container">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-medium" style={{ color: "#F1F5F9" }}>Prototype Studio</h1>
          <p className="text-sm mt-0.5" style={{ color: "#94A3B8" }}>
            Build a mockup state graph, then run personas against it
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={activeGraphId || "__new__"}
            onValueChange={(v) => {
              if (v === "__new__") { setActiveGraphId(null); setScreens([]); setTransitions([]); setGraphName("New Flow"); return; }
              const g = graphs.find((g) => g.id === v);
              if (g) loadGraph(g);
            }}
          >
            <SelectTrigger className="h-9 rounded-lg text-sm min-w-[160px]" style={{ background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" }}>
              <SelectValue placeholder="Select graph" />
            </SelectTrigger>
            <SelectContent style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
              <SelectItem value="__new__" className="text-xs">+ New graph</SelectItem>
              {graphs.map((g) => <SelectItem key={g.id} value={g.id} className="text-xs">{g.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Graph name */}
      <div className="mb-4">
        <Input
          data-testid="graph-name-input"
          value={graphName}
          onChange={(e) => setGraphName(e.target.value)}
          className="h-9 rounded-lg text-sm max-w-xs"
          style={{ background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" }}
          placeholder="Flow name"
        />
      </div>

      {/* Screens row */}
      <div className="rounded-xl p-4 mb-4" style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs uppercase tracking-wider" style={{ color: "#64748B" }}>Screens</span>
          <Button onClick={addScreen} className="h-7 text-xs rounded-md" style={{ background: "#2DD4BF", color: "#06231F" }}>
            <Plus className="w-3 h-3 mr-1" /> Add screen
          </Button>
        </div>
        {screens.length > 0 ? (
          <div className="flex gap-3 overflow-x-auto pb-2" style={{ scrollbarWidth: "thin" }}>
            {screens.map((s, i) => (
              <ScreenCard
                key={s.id}
                screen={s}
                isStart={s.id === startScreen}
                onUpdate={(u) => updateScreen(i, u)}
                onRemove={() => removeScreen(i)}
                onSetStart={() => setStartScreen(s.id)}
              />
            ))}
          </div>
        ) : (
          <div className="flex items-center justify-center py-8">
            <p className="text-xs" style={{ color: "#475569" }}>Add screens for each mockup in your flow</p>
          </div>
        )}
      </div>

      {/* Transitions */}
      <div className="rounded-xl p-4 mb-4" style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs uppercase tracking-wider" style={{ color: "#64748B" }}>Transitions</span>
          <Button onClick={addTransition} className="h-7 text-xs rounded-md" style={{ background: "#2DD4BF", color: "#06231F" }}>
            <Plus className="w-3 h-3 mr-1" /> Add transition
          </Button>
        </div>
        <div className="space-y-2">
          {transitions.map((t, i) => (
            <TransitionRow key={i} t={t} screens={screens} onUpdate={(u) => updateTransition(i, u)} onRemove={() => removeTransition(i)} />
          ))}
          {transitions.length === 0 && (
            <p className="text-xs py-4 text-center" style={{ color: "#475569" }}>
              Define transitions between screens (e.g. "click Pricing link")
            </p>
          )}
        </div>
      </div>

      {/* Save */}
      <div className="flex justify-end mb-6">
        <Button onClick={handleSave} disabled={saving} className="rounded-lg h-9" style={{ background: "#2DD4BF", color: "#06231F" }}>
          <Check className="w-4 h-4 mr-1.5" /> {saving ? "Saving..." : "Save graph"}
        </Button>
      </div>

      {/* Paywall */}
      <PaywallGate />

      {/* Run config */}
      <div className="rounded-xl p-4 mb-4" style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
        <span className="text-xs uppercase tracking-wider block mb-3" style={{ color: "#64748B" }}>
          Run prototype test
        </span>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="text-[11px] mb-1 block" style={{ color: "#64748B" }}>Goal</label>
            <Input
              data-testid="proto-goal-input"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="e.g. Find the pricing page"
              className="h-8 rounded-lg text-xs"
              style={{ background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" }}
            />
          </div>
          <div>
            <label className="text-[11px] mb-1 block" style={{ color: "#64748B" }}>Persona Panel</label>
            <Select value={panelId || "__default__"} onValueChange={(v) => setPanelId(v === "__default__" ? "" : v)}>
              <SelectTrigger className="h-8 text-xs rounded-lg" style={{ background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" }}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
                <SelectItem value="__default__" className="text-xs">Seed panel (default)</SelectItem>
                {panels.map((p) => <SelectItem key={p.id} value={p.id} className="text-xs">{p.client_ref || p.id.slice(0, 8)}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-end">
            <Button
              data-testid="proto-run-btn"
              onClick={handleRun}
              disabled={!canRun || running}
              className="rounded-lg h-8 w-full"
              style={{ background: canRun && !running ? "#2DD4BF" : "#1C2540", color: canRun && !running ? "#06231F" : "#475569" }}
            >
              {running ? <><RefreshCw className="w-3.5 h-3.5 mr-1.5 animate-spin" /> Running...</> : <><Play className="w-3.5 h-3.5 mr-1.5" /> Run prototype</>}
            </Button>
          </div>
        </div>
      </div>

      {/* Batch results */}
      {batchResult && (
        <div className="rounded-xl p-4" style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs uppercase tracking-wider" style={{ color: "#64748B" }}>
              Results — {batchResult.total_runs} persona{batchResult.total_runs !== 1 ? "s" : ""}
            </span>
            {batchResult.batch_id && (
              <button
                type="button"
                onClick={() => navigate(`/reports?batch_id=${batchResult.batch_id}`)}
                className="text-xs hover:underline"
                style={{ color: "#2DD4BF" }}
              >
                View friction report →
              </button>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {(batchResult.runs || []).map((r) => {
              const oc = { success: "#10B981", gave_up: "#F43F5E", max_steps: "#F59E0B", in_progress: "#2DD4BF" };
              return (
                <div key={r.run_id} className="rounded-lg p-3" style={{ background: "#0B0F1A", border: "0.5px solid #1E293B" }}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium" style={{ color: "#F1F5F9" }}>{r.persona_name}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: `${oc[r.outcome] || "#64748B"}20`, color: oc[r.outcome] || "#64748B" }}>
                      {r.outcome}
                    </span>
                  </div>
                  <div className="flex gap-3 text-[10px]" style={{ color: "#64748B" }}>
                    <span>{r.total_steps} steps</span>
                    <span>{r.total_signals} signals</span>
                    {r.rejected_actions > 0 && <span style={{ color: "#F59E0B" }}>{r.rejected_actions} rejected</span>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
