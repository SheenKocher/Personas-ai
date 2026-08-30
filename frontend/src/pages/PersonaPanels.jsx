import { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  listPersonaPanels, createPersonaPanel, updatePersonaPanel, deletePersonaPanel,
} from "@/lib/api";
import { PERSONA_PANELS, GENERATE } from "@/constants/testIds";
import {
  Sparkles, RefreshCw, Play, Plus, Trash2, X, Check,
  Eye, EyeOff, Keyboard, ZoomIn, Brain, Search,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from "@/components/ui/tooltip";
import axios from "axios";
import { toast } from "sonner";
import { usePaywall } from "@/hooks/usePaywall";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/* ── Colour system: persona identity colours (indigo/violet/blue family) ── */
const ACCENT_BY_DISABILITY = {
  standard: "#818CF8",
  motor:    "#A78BFA",
  blind:    "#38BDF8",
  low_vision: "#C084FC",
  cognitive:  "#F472B6",
};
const accentFor = (p) => p.accent_color || ACCENT_BY_DISABILITY[p.disability || "standard"];

const ALL_ACTIONS = [
  "click", "type", "scroll", "navigate", "wait", "key", "report_friction", "give_up",
];

const PERCEPTION_CFG = {
  full:         { icon: Eye,     label: "Full perception" },
  ax_tree_only: { icon: EyeOff,  label: "AX tree only" },
  zoomed:       { icon: Search, label: "Zoomed view" },
};

const DISABILITY_OPTIONS = [
  { value: "none", label: "Standard" },
  { value: "motor", label: "Motor" },
  { value: "blind", label: "Blind" },
  { value: "low_vision", label: "Low vision" },
  { value: "cognitive", label: "Cognitive" },
];

const PERCEPTION_OPTIONS = [
  { value: "full", label: "Full" },
  { value: "ax_tree_only", label: "AX tree only" },
  { value: "zoomed", label: "Zoomed" },
];

/* ── Derive plain-language constraint sentence ── */
function constraintSummary(p) {
  const parts = [];
  const d = p.disability;
  const mode = p.perception_mode || "full";
  const budget = p.frustration_budget ?? 4;
  const actions = p.allowed_actions || [];

  if (d === "motor" || !actions.includes("click")) {
    parts.push("Can\u2019t click \u2014 keyboard only");
  }
  if (d === "blind" || mode === "ax_tree_only") {
    parts.push("Sees only the accessibility tree, no visuals");
  } else if (d === "low_vision" || mode === "zoomed") {
    parts.push(`Views at ${p.viewport_zoom ?? 2}\u00d7 zoom`);
  }
  if (d === "cognitive") {
    parts.push("Easily overwhelmed by dense content");
  }
  if (!d && mode === "full" && actions.includes("click") && parts.length === 0) {
    parts.push("Full perception, no constraints");
  }
  parts.push(`Gives up after ${budget} frustrating step${budget !== 1 ? "s" : ""}`);
  return parts.join(". ") + ".";
}

/* ── Inline save indicator (checkmark fade) ── */
function SaveTick({ visible }) {
  return (
    <span
      className="inline-flex items-center ml-1 transition-opacity duration-500"
      style={{ opacity: visible ? 1 : 0, color: "#2DD4BF" }}
    >
      <Check className="w-3 h-3" />
    </span>
  );
}

/* ── Editable tolerance-rule tag ── */
function RuleTag({ value, onChange, onRemove }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef(null);

  const commit = () => {
    setEditing(false);
    if (draft.trim() && draft !== value) onChange(draft.trim());
    else setDraft(value);
  };

  useEffect(() => { if (editing && inputRef.current) inputRef.current.focus(); }, [editing]);

  if (editing) {
    return (
      <span className="inline-flex items-center gap-1 rounded-md text-xs px-2 py-1" style={{ background: "#0B0F1A", border: "0.5px solid #334155" }}>
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") { setDraft(value); setEditing(false); } }}
          className="bg-transparent border-none outline-none text-xs w-48"
          style={{ color: "#F1F5F9" }}
        />
      </span>
    );
  }

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-md text-xs px-2 py-1 cursor-text group"
      style={{ background: "#0B0F1A", border: "0.5px solid #1E293B", color: "#94A3B8" }}
      onClick={() => setEditing(true)}
    >
      <span className="max-w-[220px] truncate">{value}</span>
      <button
        onClick={(e) => { e.stopPropagation(); onRemove(); }}
        className="opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ color: "#F43F5E" }}
      >
        <X className="w-3 h-3" />
      </button>
    </span>
  );
}


/* ══════════════════════════════════════════════════
   PersonaCard — single card, all fields inline-editable
   ══════════════════════════════════════════════════ */
function PersonaCard({ persona, index, onChange, onRemove }) {
  const accent = accentFor(persona);
  const perc = PERCEPTION_CFG[persona.perception_mode] || PERCEPTION_CFG.full;
  const PercIcon = perc.icon;
  const [savedField, setSavedField] = useState(null);

  const flash = (field) => { setSavedField(field); setTimeout(() => setSavedField(null), 1200); };

  const update = (field, value) => {
    onChange(index, { ...persona, [field]: value });
    flash(field);
  };

  const toggleAction = (action) => {
    const cur = persona.allowed_actions || [];
    const next = cur.includes(action) ? cur.filter((a) => a !== action) : [...cur, action];
    update("allowed_actions", next);
  };

  const updateRule = (rIdx, val) => {
    const rules = [...(persona.tolerance_rules || [])];
    rules[rIdx] = val;
    update("tolerance_rules", rules);
  };
  const addRule = () => update("tolerance_rules", [...(persona.tolerance_rules || []), "New rule"]);
  const removeRule = (rIdx) => update("tolerance_rules", (persona.tolerance_rules || []).filter((_, i) => i !== rIdx));

  return (
    <div
      data-testid={`${GENERATE.personaCard}-${index}`}
      className="rounded-xl flex flex-col min-w-[310px] max-w-[370px] shrink-0"
      style={{ background: "#141B2E", border: "0.5px solid #1E293B", borderTop: `3px solid ${accent}` }}
    >
      {/* ── Header ── */}
      <div className="px-4 pt-4 pb-2 flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <input
            data-testid={`${GENERATE.personaName}-${index}`}
            value={persona.name || ""}
            onChange={(e) => update("name", e.target.value)}
            className="bg-transparent border-none outline-none text-sm font-medium w-full truncate"
            style={{ color: "#F1F5F9" }}
          />
          <SaveTick visible={savedField === "name"} />
        </div>
        <button
          data-testid={`${GENERATE.removePersona}-${index}`}
          onClick={() => onRemove(index)}
          className="p-1 rounded hover:bg-white/5 shrink-0 mt-0.5"
          style={{ color: "#F43F5E" }}
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* ── Traits ── */}
      <div className="px-4 pb-2">
        <textarea
          data-testid={`${GENERATE.personaTraits}-${index}`}
          value={persona.traits || ""}
          onChange={(e) => update("traits", e.target.value)}
          rows={2}
          className="bg-transparent border-none outline-none text-xs w-full resize-none leading-relaxed"
          style={{ color: "#94A3B8" }}
        />
      </div>

      {/* ── Constraint summary ── */}
      <div className="px-4 pb-3">
        <p className="text-[11px] leading-relaxed font-medium" style={{ color: accent }}>
          {constraintSummary(persona)}
        </p>
      </div>

      {/* ── Perception mode ── */}
      <div className="px-4 pb-3 flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <PercIcon className="w-3.5 h-3.5" style={{ color: accent }} />
          <Select value={persona.perception_mode || "full"} onValueChange={(v) => update("perception_mode", v)}>
            <SelectTrigger className="h-6 text-[11px] rounded border-0 bg-transparent px-1 w-auto gap-1" style={{ color: "#94A3B8" }}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
              {PERCEPTION_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value} className="text-xs">{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
          <SaveTick visible={savedField === "perception_mode"} />
        </div>
        <div className="flex items-center gap-1.5">
          <Select value={persona.disability || "none"} onValueChange={(v) => update("disability", v === "none" ? null : v)}>
            <SelectTrigger className="h-6 text-[11px] rounded border-0 bg-transparent px-1 w-auto gap-1" style={{ color: "#94A3B8" }}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
              {DISABILITY_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value} className="text-xs">{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* ── Action chips ── */}
      <div className="px-4 pb-3">
        <div className="flex flex-wrap gap-1">
          {ALL_ACTIONS.map((action) => {
            const enabled = (persona.allowed_actions || []).includes(action);
            return (
              <button
                key={action}
                data-testid={`${GENERATE.actionToggle}-${index}-${action}`}
                onClick={() => toggleAction(action)}
                className="px-1.5 py-0.5 rounded text-[10px] font-mono transition-all"
                style={{
                  background: enabled ? `${accent}15` : "transparent",
                  color: enabled ? accent : "#475569",
                  border: `0.5px solid ${enabled ? `${accent}30` : "#1E293B"}`,
                  textDecoration: enabled ? "none" : "line-through",
                  opacity: enabled ? 1 : 0.5,
                }}
              >
                {action}
              </button>
            );
          })}
        </div>
        <SaveTick visible={savedField === "allowed_actions"} />
      </div>

      {/* ── Inline numerics: frustration + temperature ── */}
      <div className="px-4 pb-3 flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] uppercase tracking-wider" style={{ color: "#64748B" }}>Frustration</span>
          <input
            type="number" min={1} max={10}
            value={persona.frustration_budget ?? 4}
            onChange={(e) => update("frustration_budget", parseInt(e.target.value) || 4)}
            className="w-10 h-6 text-xs text-center rounded-md bg-transparent outline-none"
            style={{ color: "#F1F5F9", border: "0.5px solid #334155" }}
          />
          <SaveTick visible={savedField === "frustration_budget"} />
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] uppercase tracking-wider" style={{ color: "#64748B" }}>Temp</span>
          <input
            type="number" step={0.1} min={0.1} max={1.0}
            value={persona.temperature ?? 0.6}
            onChange={(e) => update("temperature", parseFloat(e.target.value) || 0.6)}
            className="w-12 h-6 text-xs text-center rounded-md bg-transparent outline-none"
            style={{ color: "#F1F5F9", border: "0.5px solid #334155" }}
          />
          <SaveTick visible={savedField === "temperature"} />
        </div>
      </div>

      {/* ── Tolerance rules (tag list) ── */}
      <div className="px-4 pb-4 flex-1">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[10px] uppercase tracking-wider" style={{ color: "#64748B" }}>Tolerance rules</span>
          <button onClick={addRule} className="text-[10px] flex items-center gap-0.5" style={{ color: "#2DD4BF" }}>
            <Plus className="w-3 h-3" /> add
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {(persona.tolerance_rules || []).map((rule, rIdx) => (
            <RuleTag
              key={rIdx}
              value={rule}
              onChange={(val) => updateRule(rIdx, val)}
              onRemove={() => removeRule(rIdx)}
            />
          ))}
          {(!persona.tolerance_rules || persona.tolerance_rules.length === 0) && (
            <span className="text-[10px] italic" style={{ color: "#475569" }}>No rules — click add</span>
          )}
        </div>
        <SaveTick visible={savedField === "tolerance_rules"} />
      </div>
    </div>
  );
}


/* ══════════════════════════════════════════════════
   Page: Persona Panel Editor
   ══════════════════════════════════════════════════ */
export default function PersonaPanels() {
  const navigate = useNavigate();

  /* Panel state */
  const [panels, setPanels] = useState([]);
  const [activePanelId, setActivePanelId] = useState(null);
  const [loading, setLoading] = useState(true);

  /* Editor state */
  const [audience, setAudience] = useState("");
  const [composition, setComposition] = useState("broad");
  const [clientRef, setClientRef] = useState("");
  const [personas, setPersonas] = useState([]);
  const [targetUrl, setTargetUrl] = useState("");

  /* UI state */
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const saveTimer = useRef(null);
  const { canRun: paywallCanRun, PaywallGate } = usePaywall();

  /* Fetch panels */
  const fetchPanels = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listPersonaPanels();
      setPanels(data);
      if (!activePanelId && data.length > 0) {
        loadPanel(data[0]);
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load panels");
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { fetchPanels(); }, [fetchPanels]);

  const loadPanel = (panel) => {
    setActivePanelId(panel.id);
    setAudience(panel.audience_description || "");
    setComposition(panel.composition || "broad");
    setClientRef(panel.client_ref || "");
    setPersonas(panel.personas || []);
    setDirty(false);
  };

  /* Auto-save with debounce */
  const scheduleAutoSave = useCallback(() => {
    setDirty(true);
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      if (!activePanelId) return;
      try {
        await updatePersonaPanel(activePanelId, {
          audience_description: audience,
          composition,
          client_ref: clientRef,
          personas,
        });
        setDirty(false);
      } catch (e) {
        console.error("Auto-save failed", e);
      }
    }, 1500);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePanelId, audience, composition, clientRef, personas]);

  const updatePersona = (index, updated) => {
    const next = [...personas];
    next[index] = updated;
    setPersonas(next);
    scheduleAutoSave();
  };

  const removePersona = (index) => {
    setPersonas(personas.filter((_, i) => i !== index));
    scheduleAutoSave();
  };

  /* Generate */
  const handleGenerate = async () => {
    if (!audience.trim()) return;
    setGenerating(true);
    try {
      const res = await axios.post(`${API}/generate-personas`, {
        audience_description: audience.trim(),
        count: 4,
      });
      const generated = res.data.personas || [];
      setPersonas(generated);
      setComposition(res.data.composition || "broad");
      setDirty(true);

      // If editing existing panel, auto-save. If new, create.
      if (activePanelId) {
        await updatePersonaPanel(activePanelId, {
          audience_description: audience,
          composition: res.data.composition || "broad",
          personas: generated,
        });
        setDirty(false);
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Generation failed");
    }
    finally { setGenerating(false); }
  };

  /* Save new panel */
  const handleSaveNew = async () => {
    if (!personas.length) return;
    setSaving(true);
    try {
      const created = await createPersonaPanel({
        client_ref: clientRef || `panel-${Date.now()}`,
        audience_description: audience,
        composition,
        personas,
      });
      setActivePanelId(created.id);
      setDirty(false);
      fetchPanels();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to save panel");
    }
    finally { setSaving(false); }
  };

  /* Delete panel */
  const handleDelete = async () => {
    if (!activePanelId) return;
    try {
      await deletePersonaPanel(activePanelId);
      setActivePanelId(null);
      setPersonas([]);
      setAudience("");
      setClientRef("");
      fetchPanels();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to delete panel");
    }
  };

  /* New blank panel */
  const handleNew = () => {
    setActivePanelId(null);
    setPersonas([]);
    setAudience("");
    setClientRef("");
    setComposition("broad");
    setDirty(false);
  };

  /* Can run? */
  const canRun = personas.length > 0 && targetUrl.trim().length > 0 && paywallCanRun;

  const handleRun = () => {
    // Navigate to new-run with panel pre-selected
    navigate(`/new-run?panel=${activePanelId || ""}&target=${encodeURIComponent(targetUrl)}`);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 rounded-full animate-spin" style={{ borderColor: "#2DD4BF", borderTopColor: "transparent" }} />
      </div>
    );
  }

  return (
    <TooltipProvider delayDuration={200}>
      <div data-testid={PERSONA_PANELS.container}>

        {/* ── Page header ── */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-medium" style={{ color: "#F1F5F9" }}>Persona Panels</h1>
            <p className="text-sm mt-0.5" style={{ color: "#94A3B8" }}>Generate, inspect, and tune synthetic test personas</p>
          </div>
          <div className="flex items-center gap-2">
            {/* Panel selector */}
            <Select
              value={activePanelId || "__new__"}
              onValueChange={(v) => {
                if (v === "__new__") { handleNew(); return; }
                const p = panels.find((p) => p.id === v);
                if (p) loadPanel(p);
              }}
            >
              <SelectTrigger
                data-testid="panel-selector"
                className="h-9 rounded-lg text-sm min-w-[180px]"
                style={{ background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" }}
              >
                <SelectValue placeholder="Select panel" />
              </SelectTrigger>
              <SelectContent style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
                <SelectItem value="__new__" className="text-xs">
                  <span className="flex items-center gap-1.5"><Plus className="w-3 h-3" /> New panel</span>
                </SelectItem>
                {panels.map((p) => (
                  <SelectItem key={p.id} value={p.id} className="text-xs">
                    {p.client_ref || p.audience_description?.slice(0, 30) || p.id.slice(0, 8)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {activePanelId && (
              <button
                data-testid={PERSONA_PANELS.deleteBtn}
                onClick={handleDelete}
                className="p-2 rounded-lg hover:bg-white/5 transition-colors"
                style={{ color: "#F43F5E" }}
              >
                <Trash2 className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* ── Audience + generate bar ── */}
        <div
          className="rounded-xl p-4 mb-5"
          style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
        >
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="text-[11px] uppercase tracking-wider mb-1.5 block" style={{ color: "#64748B" }}>
                Audience description
              </label>
              <Textarea
                data-testid={GENERATE.audienceInput}
                value={audience}
                onChange={(e) => { setAudience(e.target.value); scheduleAutoSave(); }}
                placeholder='e.g. "Tier-2 city shopkeepers, 35-55, low English literacy, budget Android, distrust upfront payment"'
                rows={2}
                className="rounded-lg text-sm resize-none"
                style={{ background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" }}
              />
            </div>
            <div className="flex flex-col justify-between shrink-0 gap-2 pt-5">
              {/* Composition toggle */}
              <div className="flex rounded-lg overflow-hidden" style={{ border: "0.5px solid #334155" }}>
                {["broad", "focused"].map((c) => (
                  <button
                    key={c}
                    onClick={() => { setComposition(c); scheduleAutoSave(); }}
                    className="px-3 py-1.5 text-[11px] uppercase tracking-wider transition-colors"
                    style={{
                      background: composition === c ? "#2DD4BF15" : "transparent",
                      color: composition === c ? "#2DD4BF" : "#64748B",
                    }}
                  >
                    {c}
                  </button>
                ))}
              </div>
              <Button
                data-testid={GENERATE.generateBtn}
                onClick={handleGenerate}
                disabled={generating || !audience.trim()}
                className="rounded-lg h-9"
                style={{ background: "#2DD4BF", color: "#06231F" }}
              >
                {generating ? (
                  <><RefreshCw className="w-4 h-4 mr-1.5 animate-spin" /> Generating</>
                ) : (
                  <><Sparkles className="w-4 h-4 mr-1.5" /> Generate panel</>
                )}
              </Button>
            </div>
          </div>

          {/* Client ref + save (for new panels) */}
          {!activePanelId && personas.length > 0 && (
            <div className="flex items-end gap-3 mt-3 pt-3" style={{ borderTop: "0.5px solid #1E293B" }}>
              <div className="flex-1">
                <label className="text-[11px] uppercase tracking-wider mb-1 block" style={{ color: "#64748B" }}>Panel name</label>
                <Input
                  data-testid={GENERATE.clientRefInput}
                  value={clientRef}
                  onChange={(e) => setClientRef(e.target.value)}
                  placeholder="e.g. tier2-shopkeepers-v1"
                  className="h-8 rounded-lg text-sm"
                  style={{ background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" }}
                />
              </div>
              <Button
                data-testid={GENERATE.saveBtn}
                onClick={handleSaveNew}
                disabled={saving}
                className="rounded-lg h-8 text-xs"
                style={{ background: "#2DD4BF", color: "#06231F" }}
              >
                {saving ? "Saving..." : "Save panel"}
              </Button>
            </div>
          )}
        </div>

        {/* ── Persona cards row ── */}
        {personas.length > 0 ? (
          <div className="relative mb-5">
            <div
              className="flex gap-4 overflow-x-auto pb-4 pr-8"
              style={{ scrollbarWidth: "thin" }}
            >
              {personas.map((p, i) => (
                <PersonaCard
                  key={i}
                  persona={p}
                  index={i}
                  onChange={updatePersona}
                  onRemove={removePersona}
                />
              ))}
            </div>
            {/* Scroll fade affordance */}
            {personas.length > 3 && (
              <div
                className="absolute right-0 top-0 bottom-4 w-16 pointer-events-none"
                style={{ background: "linear-gradient(to right, transparent, #0B0F1A)" }}
              />
            )}
          </div>
        ) : (
          <div
            className="rounded-xl flex flex-col items-center justify-center py-16 mb-5"
            style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
          >
            <Sparkles className="w-10 h-10 mb-3" style={{ color: "#334155" }} />
            <p className="text-sm mb-1" style={{ color: "#F1F5F9" }}>No personas yet</p>
            <p className="text-xs" style={{ color: "#64748B" }}>
              Describe your audience above and click Generate panel
            </p>
          </div>
        )}

        {/* ── PaywallGate ── */}
        <PaywallGate />

        {/* ── Run bar ── */}
        <div
          className="rounded-xl p-4 flex items-end gap-4"
          style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
        >
          <div className="flex-1">
            <label className="text-[11px] uppercase tracking-wider mb-1 block" style={{ color: "#64748B" }}>
              Target URL
            </label>
            <Input
              data-testid="panel-target-url"
              value={targetUrl}
              onChange={(e) => setTargetUrl(e.target.value)}
              placeholder="https://example.com"
              className="h-9 rounded-lg text-sm"
              style={{ background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" }}
            />
          </div>
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Button
                  data-testid="panel-run-btn"
                  disabled={!canRun}
                  onClick={handleRun}
                  className="rounded-lg h-9"
                  style={{
                    background: canRun ? "#2DD4BF" : "#1C2540",
                    color: canRun ? "#06231F" : "#475569",
                    cursor: canRun ? "pointer" : "not-allowed",
                  }}
                >
                  <Play className="w-4 h-4 mr-1.5" />
                  Run this panel
                </Button>
              </span>
            </TooltipTrigger>
            {!canRun && (
              <TooltipContent
                side="top"
                className="text-xs"
                style={{ background: "#1C2540", color: "#94A3B8", border: "0.5px solid #334155" }}
              >
                {personas.length === 0
                  ? "Generate at least one persona first"
                  : "Enter a target URL to run against"}
              </TooltipContent>
            )}
          </Tooltip>
        </div>

        {/* ── Auto-save indicator ── */}
        {dirty && activePanelId && (
          <div className="mt-2 text-[10px] text-right" style={{ color: "#64748B" }}>
            Saving changes...
          </div>
        )}
      </div>
    </TooltipProvider>
  );
}
