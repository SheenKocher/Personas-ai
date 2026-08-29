import { useEffect, useState, useCallback } from "react";
import { listPersonaPanels, createPersonaPanel, updatePersonaPanel, deletePersonaPanel } from "@/lib/api";
import { PERSONA_PANELS } from "@/constants/testIds";
import { Users, Plus, Pencil, Trash2, Eye, EyeOff, Keyboard, ZoomIn, Brain } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from "@/components/ui/select";
import { toast } from "sonner";

const disabilityIcons = {
  motor: Keyboard,
  blind: EyeOff,
  low_vision: ZoomIn,
  cognitive: Brain,
};

function PersonaChip({ persona }) {
  const accentColor = persona.accent_color || "#818CF8";
  const Icon = persona.disability ? disabilityIcons[persona.disability] : Eye;
  return (
    <div
      className="flex items-center gap-2 px-3 py-1.5 rounded-md text-xs"
      style={{ background: `${accentColor}15`, color: accentColor }}
    >
      {Icon && <Icon className="w-3.5 h-3.5" />}
      <span>{persona.name}</span>
    </div>
  );
}

export default function PersonaPanels() {
  const [panels, setPanels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingPanel, setEditingPanel] = useState(null);
  const [formData, setFormData] = useState({
    client_ref: "",
    audience_description: "",
    composition: "broad",
    personas: [],
  });

  const fetchPanels = useCallback(async () => {
    setLoading(true);
    const data = await listPersonaPanels();
    setPanels(data);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchPanels();
  }, [fetchPanels]);

  const openCreate = () => {
    setEditingPanel(null);
    setFormData({ client_ref: "", audience_description: "", composition: "broad", personas: [] });
    setDialogOpen(true);
  };

  const openEdit = (panel) => {
    setEditingPanel(panel);
    setFormData({
      client_ref: panel.client_ref,
      audience_description: panel.audience_description,
      composition: panel.composition,
      personas: panel.personas,
    });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    try {
      if (editingPanel) {
        await updatePersonaPanel(editingPanel.id, formData);
        toast.success("Panel updated");
      } else {
        await createPersonaPanel(formData);
        toast.success("Panel created");
      }
      setDialogOpen(false);
      fetchPanels();
    } catch {
      toast.error("Failed to save panel");
    }
  };

  const handleDelete = async (id) => {
    try {
      await deletePersonaPanel(id);
      toast.success("Panel deleted");
      fetchPanels();
    } catch {
      toast.error("Failed to delete panel");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 rounded-full animate-spin" style={{ borderColor: "#2DD4BF", borderTopColor: "transparent" }} />
      </div>
    );
  }

  return (
    <div data-testid={PERSONA_PANELS.container}>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-medium" style={{ color: "#F1F5F9" }}>
            Persona Panels
          </h1>
          <p className="text-sm mt-1" style={{ color: "#94A3B8" }}>
            Manage test persona configurations
          </p>
        </div>
        <Button
          data-testid={PERSONA_PANELS.createBtn}
          onClick={openCreate}
          className="rounded-lg"
          style={{ background: "#2DD4BF", color: "#06231F" }}
        >
          <Plus className="w-4 h-4 mr-2" />
          New Panel
        </Button>
      </div>

      {panels.length > 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {panels.map((panel) => (
            <div
              key={panel.id}
              data-testid={PERSONA_PANELS.panelCard}
              className="rounded-xl p-4"
              style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="text-sm font-medium" style={{ color: "#F1F5F9" }}>
                    {panel.client_ref || "Untitled Panel"}
                  </h3>
                  <p className="text-xs mt-1" style={{ color: "#64748B" }}>
                    {panel.audience_description || "No description"}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <span
                    className="text-xs px-2 py-0.5 rounded-md uppercase tracking-wider"
                    style={{ background: "rgba(45,212,191,0.15)", color: "#2DD4BF" }}
                  >
                    {panel.composition}
                  </span>
                  <button
                    data-testid={PERSONA_PANELS.editBtn}
                    onClick={() => openEdit(panel)}
                    className="p-1.5 rounded-md transition-colors hover:bg-white/5"
                    style={{ color: "#94A3B8" }}
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button
                    data-testid={PERSONA_PANELS.deleteBtn}
                    onClick={() => handleDelete(panel.id)}
                    className="p-1.5 rounded-md transition-colors hover:bg-white/5"
                    style={{ color: "#F43F5E" }}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {(panel.personas || []).map((p, i) => (
                  <PersonaChip key={i} persona={p} />
                ))}
              </div>
              <div className="mt-3 text-xs" style={{ color: "#64748B" }}>
                {(panel.personas || []).length} persona{(panel.personas || []).length !== 1 ? "s" : ""}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div
          data-testid={PERSONA_PANELS.emptyState}
          className="rounded-xl flex flex-col items-center justify-center py-20"
          style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
        >
          <Users className="w-12 h-12 mb-4" style={{ color: "#334155" }} />
          <h2 className="text-base font-medium mb-1" style={{ color: "#F1F5F9" }}>
            No panels yet
          </h2>
          <p className="text-sm mb-4" style={{ color: "#94A3B8" }}>
            Create a persona panel to get started
          </p>
          <Button
            onClick={openCreate}
            className="rounded-lg"
            style={{ background: "#2DD4BF", color: "#06231F" }}
          >
            <Plus className="w-4 h-4 mr-2" />
            Create Panel
          </Button>
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent
          data-testid={PERSONA_PANELS.panelDialog}
          className="max-w-lg"
          style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
        >
          <DialogHeader>
            <DialogTitle style={{ color: "#F1F5F9" }}>
              {editingPanel ? "Edit Panel" : "New Panel"}
            </DialogTitle>
            <DialogDescription style={{ color: "#94A3B8" }}>
              {editingPanel ? "Update the panel configuration" : "Configure a new persona panel"}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <label className="text-xs mb-1.5 block" style={{ color: "#64748B" }}>
                Client Reference
              </label>
              <Input
                value={formData.client_ref}
                onChange={(e) => setFormData({ ...formData, client_ref: e.target.value })}
                placeholder="e.g. my-project"
                className="rounded-lg"
                style={{
                  background: "#0B0F1A",
                  border: "0.5px solid #334155",
                  color: "#F1F5F9",
                }}
              />
            </div>
            <div>
              <label className="text-xs mb-1.5 block" style={{ color: "#64748B" }}>
                Audience Description
              </label>
              <Input
                value={formData.audience_description}
                onChange={(e) => setFormData({ ...formData, audience_description: e.target.value })}
                placeholder="Describe the target audience"
                className="rounded-lg"
                style={{
                  background: "#0B0F1A",
                  border: "0.5px solid #334155",
                  color: "#F1F5F9",
                }}
              />
            </div>
            <div>
              <label className="text-xs mb-1.5 block" style={{ color: "#64748B" }}>
                Composition
              </label>
              <Select
                value={formData.composition}
                onValueChange={(val) => setFormData({ ...formData, composition: val })}
              >
                <SelectTrigger
                  className="rounded-lg"
                  style={{
                    background: "#0B0F1A",
                    border: "0.5px solid #334155",
                    color: "#F1F5F9",
                  }}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
                  <SelectItem value="broad">Broad</SelectItem>
                  <SelectItem value="focused">Focused</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button
              data-testid={PERSONA_PANELS.cancelBtn}
              variant="outline"
              onClick={() => setDialogOpen(false)}
              className="rounded-lg"
              style={{ border: "0.5px solid #334155", color: "#94A3B8" }}
            >
              Cancel
            </Button>
            <Button
              data-testid={PERSONA_PANELS.saveBtn}
              onClick={handleSave}
              className="rounded-lg"
              style={{ background: "#2DD4BF", color: "#06231F" }}
            >
              {editingPanel ? "Update" : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
