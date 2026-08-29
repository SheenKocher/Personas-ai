import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createPersonaPanel } from "@/lib/api";
import { GENERATE } from "@/constants/testIds";
import {
  Sparkles, Save, RefreshCw, Plus, Trash2, ChevronDown, ChevronUp,
  Eye, EyeOff, Keyboard, ZoomIn, Brain,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ALL_ACTIONS = ["click", "type", "scroll", "navigate", "wait", "key", "report_friction", "give_up"];
const DISABILITIES = [
  { value: "none", label: "None" },
  { value: "motor", label: "Motor" },
  { value: "blind", label: "Blind" },
  { value: "low_vision", label: "Low Vision" },
  { value: "cognitive", label: "Cognitive" },
];
const PERCEPTION_MODES = [
  { value: "full", label: "Full" },
  { value: "ax_tree_only", label: "AX Tree Only" },
  { value: "zoomed", label: "Zoomed" },
];

const disabilityIcons = { motor: Keyboard, blind: EyeOff, low_vision: ZoomIn, cognitive: Brain };

const inputStyle = { background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" };
const labelStyle = { color: "#64748B" };

function PersonaCard({ persona, index, onChange, onRemove }) {
  const [expanded, setExpanded] = useState(false);
  const accentColor = persona.accent_color || "#818CF8";
  const Icon = persona.disability ? disabilityIcons[persona.disability] : Eye;

  const update = (field, value) => onChange(index, { ...persona, [field]: value });

  const toggleAction = (action) => {
    const current = persona.allowed_actions || [];
    const next = current.includes(action)
      ? current.filter((a) => a !== action)
      : [...current, action];
    update("allowed_actions", next);
  };

  const updateRule = (ruleIdx, value) => {
    const rules = [...(persona.tolerance_rules || [])];
    rules[ruleIdx] = value;
    update("tolerance_rules", rules);
  };

  const addRule = () => update("tolerance_rules", [...(persona.tolerance_rules || []), ""]);
  const removeRule = (ruleIdx) => {
    const rules = (persona.tolerance_rules || []).filter((_, i) => i !== ruleIdx);
    update("tolerance_rules", rules);
  };

  return (
    <div
      data-testid={`${GENERATE.personaCard}-${index}`}
      className="rounded-xl overflow-hidden"
      style={{ background: "#141B2E", border: `1px solid ${accentColor}40` }}
    >
      {/* Card header */}
      <div className="px-4 py-3 flex items-center justify-between" style={{ borderBottom: "0.5px solid #1E293B" }}>
        <div className="flex items-center gap-3 min-w-0">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
            style={{ background: `${accentColor}20` }}
          >
            {Icon && <Icon className="w-4 h-4" style={{ color: accentColor }} />}
          </div>
          <div className="min-w-0">
            <Input
              data-testid={`${GENERATE.personaName}-${index}`}
              value={persona.name || ""}
              onChange={(e) => update("name", e.target.value)}
              className="h-7 text-sm font-medium border-0 bg-transparent px-0 focus-visible:ring-0"
              style={{ color: "#F1F5F9" }}
            />
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {persona.disability && (
            <Badge className="text-[10px] px-1.5 py-0" style={{ background: `${accentColor}20`, color: accentColor, border: "none" }}>
              {persona.disability}
            </Badge>
          )}
          <button onClick={() => setExpanded(!expanded)} className="p-1 rounded" style={{ color: "#94A3B8" }}>
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
          <button
            data-testid={`${GENERATE.removePersona}-${index}`}
            onClick={() => onRemove(index)}
            className="p-1 rounded hover:bg-white/5"
            style={{ color: "#F43F5E" }}
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Traits — always visible */}
      <div className="px-4 py-3">
        <label className="text-[11px] mb-1 block" style={labelStyle}>Traits</label>
        <Textarea
          data-testid={`${GENERATE.personaTraits}-${index}`}
          value={persona.traits || ""}
          onChange={(e) => update("traits", e.target.value)}
          rows={2}
          className="text-xs rounded-lg resize-none"
          style={inputStyle}
        />
      </div>

      {/* Expandable detail section */}
      {expanded && (
        <div className="px-4 pb-4 space-y-3" style={{ borderTop: "0.5px solid #1E293B" }}>
          {/* Row: disability + perception + zoom + temperature + frustration */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-3">
            <div>
              <label className="text-[11px] mb-1 block" style={labelStyle}>Disability</label>
              <Select value={persona.disability || "none"} onValueChange={(v) => update("disability", v === "none" ? null : v)}>
                <SelectTrigger className="h-8 text-xs rounded-lg" style={inputStyle}><SelectValue /></SelectTrigger>
                <SelectContent style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
                  {DISABILITIES.map((d) => <SelectItem key={d.value} value={d.value}>{d.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-[11px] mb-1 block" style={labelStyle}>Perception</label>
              <Select value={persona.perception_mode || "full"} onValueChange={(v) => update("perception_mode", v)}>
                <SelectTrigger className="h-8 text-xs rounded-lg" style={inputStyle}><SelectValue /></SelectTrigger>
                <SelectContent style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
                  {PERCEPTION_MODES.map((m) => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-[11px] mb-1 block" style={labelStyle}>Frustration Budget</label>
              <Input
                type="number"
                min={1}
                max={10}
                value={persona.frustration_budget ?? 4}
                onChange={(e) => update("frustration_budget", parseInt(e.target.value) || 4)}
                className="h-8 text-xs rounded-lg"
                style={inputStyle}
              />
            </div>
            <div>
              <label className="text-[11px] mb-1 block" style={labelStyle}>Temperature</label>
              <Input
                type="number"
                step="0.1"
                min={0.1}
                max={1.0}
                value={persona.temperature ?? 0.6}
                onChange={(e) => update("temperature", parseFloat(e.target.value) || 0.6)}
                className="h-8 text-xs rounded-lg"
                style={inputStyle}
              />
            </div>
            <div>
              <label className="text-[11px] mb-1 block" style={labelStyle}>Viewport Zoom</label>
              <Input
                type="number"
                step="0.5"
                min={1.0}
                max={4.0}
                value={persona.viewport_zoom ?? 1.0}
                onChange={(e) => update("viewport_zoom", parseFloat(e.target.value) || 1.0)}
                className="h-8 text-xs rounded-lg"
                style={inputStyle}
              />
            </div>
          </div>

          {/* Allowed actions */}
          <div>
            <label className="text-[11px] mb-1.5 block" style={labelStyle}>Allowed Actions</label>
            <div className="flex flex-wrap gap-1.5">
              {ALL_ACTIONS.map((action) => {
                const active = (persona.allowed_actions || []).includes(action);
                return (
                  <button
                    key={action}
                    data-testid={`${GENERATE.actionToggle}-${index}-${action}`}
                    onClick={() => toggleAction(action)}
                    className="px-2 py-1 rounded-md text-[11px] font-mono transition-colors"
                    style={{
                      background: active ? "rgba(45,212,191,0.15)" : "transparent",
                      color: active ? "#2DD4BF" : "#64748B",
                      border: `0.5px solid ${active ? "#2DD4BF40" : "#334155"}`,
                    }}
                  >
                    {action}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Tolerance rules */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-[11px]" style={labelStyle}>Tolerance Rules</label>
              <button onClick={addRule} className="text-[11px] flex items-center gap-1" style={{ color: "#2DD4BF" }}>
                <Plus className="w-3 h-3" /> Add
              </button>
            </div>
            <div className="space-y-1.5">
              {(persona.tolerance_rules || []).map((rule, ruleIdx) => (
                <div key={ruleIdx} className="flex items-center gap-1.5">
                  <Input
                    value={rule}
                    onChange={(e) => updateRule(ruleIdx, e.target.value)}
                    className="h-7 text-xs rounded-lg flex-1"
                    style={inputStyle}
                    placeholder="e.g. flag any page that feels slow to respond"
                  />
                  <button onClick={() => removeRule(ruleIdx)} className="p-1 shrink-0" style={{ color: "#F43F5E" }}>
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Accent color */}
          <div>
            <label className="text-[11px] mb-1 block" style={labelStyle}>Accent Color</label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={persona.accent_color || "#818CF8"}
                onChange={(e) => update("accent_color", e.target.value)}
                className="w-7 h-7 rounded border-0 cursor-pointer"
                style={{ background: "transparent" }}
              />
              <span className="text-xs font-mono" style={{ color: "#94A3B8" }}>{persona.accent_color}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


export default function GeneratePanel() {
  const navigate = useNavigate();
  const [audience, setAudience] = useState("");
  const [count, setCount] = useState(4);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState(null); // { personas, composition, rationale }
  const [clientRef, setClientRef] = useState("");

  const handleGenerate = async () => {
    if (!audience.trim()) { toast.error("Enter an audience description"); return; }
    setGenerating(true);
    setResult(null);
    try {
      const res = await axios.post(`${API}/generate-personas`, {
        audience_description: audience.trim(),
        count,
      });
      setResult(res.data);
      setClientRef("");
      toast.success(`Generated ${res.data.personas.length} personas`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const updatePersona = (index, updated) => {
    const next = [...result.personas];
    next[index] = updated;
    setResult({ ...result, personas: next });
  };

  const removePersona = (index) => {
    const next = result.personas.filter((_, i) => i !== index);
    setResult({ ...result, personas: next });
  };

  const handleSave = async () => {
    if (!result || !result.personas.length) return;
    setSaving(true);
    try {
      await createPersonaPanel({
        client_ref: clientRef || `gen-${Date.now()}`,
        audience_description: audience,
        composition: result.composition || "broad",
        personas: result.personas,
      });
      toast.success("Panel saved");
      navigate("/persona-panels");
    } catch {
      toast.error("Failed to save panel");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div data-testid={GENERATE.container} className="max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-medium" style={{ color: "#F1F5F9" }}>
          Generate Persona Panel
        </h1>
        <p className="text-sm mt-1" style={{ color: "#94A3B8" }}>
          Describe your audience and let AI create a diverse test panel
        </p>
      </div>

      {/* Input section */}
      <div
        className="rounded-xl p-5 mb-6"
        style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
      >
        <label className="text-xs font-medium mb-2 block" style={labelStyle}>
          Audience Description
        </label>
        <Textarea
          data-testid={GENERATE.audienceInput}
          value={audience}
          onChange={(e) => setAudience(e.target.value)}
          placeholder='e.g. "Tier-2 city shopkeepers, 35-55, low English literacy, budget Android, distrust upfront payment"'
          rows={3}
          className="rounded-lg mb-4 text-sm"
          style={inputStyle}
        />
        <div className="flex items-end gap-4">
          <div>
            <label className="text-xs mb-1.5 block" style={labelStyle}>Persona Count</label>
            <Select value={String(count)} onValueChange={(v) => setCount(parseInt(v))}>
              <SelectTrigger data-testid={GENERATE.countSelect} className="w-20 h-9 rounded-lg text-sm" style={inputStyle}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
                {[3, 4, 5].map((n) => <SelectItem key={n} value={String(n)}>{n}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <Button
            data-testid={GENERATE.generateBtn}
            onClick={handleGenerate}
            disabled={generating || !audience.trim()}
            className="rounded-lg h-9"
            style={{ background: "#2DD4BF", color: "#06231F" }}
          >
            {generating ? (
              <>
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4 mr-2" />
                Generate Panel
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Generated personas */}
      {result && result.personas && result.personas.length > 0 && (
        <>
          {/* Rationale */}
          {result.rationale && (
            <div
              className="rounded-lg px-4 py-3 mb-4 text-xs font-mono"
              style={{ background: "#0B0F1A", border: "0.5px solid #1E293B", color: "#94A3B8" }}
            >
              {result.rationale}
            </div>
          )}

          {/* Persona cards */}
          <div className="space-y-3 mb-6">
            {result.personas.map((persona, i) => (
              <PersonaCard
                key={i}
                persona={persona}
                index={i}
                onChange={updatePersona}
                onRemove={removePersona}
              />
            ))}
          </div>

          {/* Save section */}
          <div
            className="rounded-xl p-5 flex items-end gap-4"
            style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
          >
            <div className="flex-1">
              <label className="text-xs mb-1.5 block" style={labelStyle}>Panel Name</label>
              <Input
                data-testid={GENERATE.clientRefInput}
                value={clientRef}
                onChange={(e) => setClientRef(e.target.value)}
                placeholder="e.g. tier2-shopkeepers-v1"
                className="rounded-lg"
                style={inputStyle}
              />
            </div>
            <Button
              data-testid={GENERATE.saveBtn}
              onClick={handleSave}
              disabled={saving || !result.personas.length}
              className="rounded-lg h-9"
              style={{ background: "#2DD4BF", color: "#06231F" }}
            >
              <Save className="w-4 h-4 mr-2" />
              {saving ? "Saving..." : "Save Panel"}
            </Button>
          </div>
        </>
      )}

      {/* Empty state when nothing generated yet */}
      {!result && !generating && (
        <div
          className="rounded-xl flex flex-col items-center justify-center py-16"
          style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
        >
          <Sparkles className="w-10 h-10 mb-3" style={{ color: "#334155" }} />
          <p className="text-sm" style={{ color: "#94A3B8" }}>
            Describe your audience above to generate a test panel
          </p>
        </div>
      )}
    </div>
  );
}
