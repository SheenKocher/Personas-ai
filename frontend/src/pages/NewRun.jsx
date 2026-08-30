import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listPersonaPanels, engineRun } from "@/lib/api";
import { NEW_RUN } from "@/constants/testIds";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from "@/components/ui/select";
import { toast } from "sonner";
import { Spinner, ErrorBanner } from "@/components/shared";

function FieldLabel({ children }) {
  return (
    <label className="text-[11px] uppercase tracking-wider mb-1.5 block" style={{ color: "#64748B" }}>
      {children}<span style={{ color: "#F43F5E" }}> *</span>
    </label>
  );
}

export default function NewRun() {
  const navigate = useNavigate();
  const [panels, setPanels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({
    target: "",
    goal: "",
    stage: "prototype",
    panel_id: "",
    persona_index: "",
  });

  const load = () => {
    setLoading(true);
    setError(null);
    listPersonaPanels()
      .then(setPanels)
      .catch((e) => setError(e?.response?.data?.detail || "Failed to load panels"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const selectedPanel = panels.find((p) => p.id === form.panel_id);
  const selectedPersona =
    selectedPanel && form.persona_index !== ""
      ? selectedPanel.personas[parseInt(form.persona_index)]
      : null;

  // Every field must be filled before a run can start.
  const isComplete =
    form.target.trim() !== "" &&
    form.goal.trim() !== "" &&
    form.stage !== "" &&
    form.panel_id !== "" &&
    form.persona_index !== "";

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!isComplete) {
      toast.error("Fill in every field before starting a run");
      return;
    }
    setSubmitting(true);
    try {
      let target = form.target.trim();
      if (form.stage === "runtime" && !/^https?:\/\//i.test(target)) {
        target = `https://${target}`;
      }
      await engineRun({
        target_url: target,
        goal: form.goal.trim(),
        stage: form.stage,
        persona: selectedPersona || null,
        persona_panel_id: form.panel_id,
        persona_index: parseInt(form.persona_index),
      });
      toast.success("Run started");
      navigate("/");
    } catch (e) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail;
      toast.error(
        status === 402
          ? "Payment required — the first run is free; buy a credit for further runs."
          : detail || "Failed to start run"
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <Spinner />;
  if (error) return <ErrorBanner message={error} onRetry={load} />;

  const inputStyle = { background: "#0B0F1A", border: "0.5px solid #334155", color: "#F1F5F9" };
  const dropdownStyle = { background: "#141B2E", border: "0.5px solid #1E293B" };
  const canSubmit = isComplete && !submitting;

  return (
    <div data-testid={NEW_RUN.container} className="max-w-xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-medium" style={{ color: "#F1F5F9" }}>New Run</h1>
        <p className="text-sm mt-1" style={{ color: "#94A3B8" }}>Configure and start a synthetic user test run</p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="rounded-xl p-6 space-y-5"
        style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
      >
        <div>
          <FieldLabel>Target URL</FieldLabel>
          <Input data-testid={NEW_RUN.targetInput} value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })} placeholder="https://example.com" className="rounded-lg" style={inputStyle} />
        </div>

        <div>
          <FieldLabel>Goal</FieldLabel>
          <Input data-testid={NEW_RUN.goalInput} value={form.goal} onChange={(e) => setForm({ ...form, goal: e.target.value })} placeholder="e.g. Complete the checkout flow" className="rounded-lg" style={inputStyle} />
        </div>

        <div>
          <FieldLabel>Stage</FieldLabel>
          <Select value={form.stage} onValueChange={(val) => setForm({ ...form, stage: val })}>
            <SelectTrigger data-testid={NEW_RUN.stageSelect} className="rounded-lg" style={inputStyle}><SelectValue /></SelectTrigger>
            <SelectContent style={dropdownStyle}>
              <SelectItem value="prototype">Prototype</SelectItem>
              <SelectItem value="runtime">Runtime</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div>
          <FieldLabel>Persona Panel</FieldLabel>
          <Select value={form.panel_id} onValueChange={(val) => setForm({ ...form, panel_id: val, persona_index: "" })}>
            <SelectTrigger data-testid={NEW_RUN.panelSelect} className="rounded-lg" style={inputStyle}><SelectValue placeholder="Select a panel" /></SelectTrigger>
            <SelectContent style={dropdownStyle}>
              {panels.map((p) => (
                <SelectItem key={p.id} value={p.id}>{p.client_ref || p.id} ({(p.personas || []).length} personas)</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div>
          <FieldLabel>Persona</FieldLabel>
          <Select
            value={form.persona_index}
            onValueChange={(val) => setForm({ ...form, persona_index: val })}
            disabled={!selectedPanel || (selectedPanel.personas || []).length === 0}
          >
            <SelectTrigger className="rounded-lg" style={inputStyle}>
              <SelectValue placeholder={selectedPanel ? "Select a persona" : "Select a panel first"} />
            </SelectTrigger>
            <SelectContent style={dropdownStyle}>
              {(selectedPanel?.personas || []).map((p, i) => (
                <SelectItem key={i} value={String(i)}>{p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {selectedPersona && (
          <div className="rounded-lg p-3" style={{ background: "#0B0F1A", border: "0.5px solid #334155" }}>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-3 h-3 rounded-full" style={{ background: selectedPersona.accent_color || "#818CF8" }} />
              <span className="text-sm font-medium" style={{ color: "#F1F5F9" }}>{selectedPersona.name}</span>
            </div>
            <p className="text-xs" style={{ color: "#94A3B8" }}>{selectedPersona.traits}</p>
            {selectedPersona.tolerance_rules && (
              <div className="mt-2 space-y-1">
                {selectedPersona.tolerance_rules.map((rule, i) => (
                  <div key={i} className="text-xs font-mono" style={{ color: "#64748B" }}>{rule}</div>
                ))}
              </div>
            )}
          </div>
        )}

        <div>
          <Button
            data-testid={NEW_RUN.startBtn}
            type="submit"
            disabled={!canSubmit}
            className="w-full rounded-lg"
            style={{
              background: "#2DD4BF",
              color: "#06231F",
              opacity: canSubmit ? 1 : 0.45,
              cursor: canSubmit ? "pointer" : "not-allowed",
            }}
          >
            <Play className="w-4 h-4 mr-2" />
            {submitting ? "Starting..." : "Start Run"}
          </Button>
          {!isComplete && (
            <p className="text-[11px] mt-2 text-center" style={{ color: "#64748B" }}>
              All fields are required to start a run.
            </p>
          )}
        </div>
      </form>
    </div>
  );
}
