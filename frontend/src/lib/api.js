import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API });

// --- Runs ---
export const createRun = (data) => api.post("/runs", data).then((r) => r.data);
// Starts the actual persona engine in the background (perceive→think→act loop).
// Use this to START a run; createRun() is only a bare DB insert and never executes.
export const engineRun = (data) => api.post("/engine/run", data).then((r) => r.data);
export const getEngineRun = (id) => api.get(`/engine/run/${id}`).then((r) => r.data);
// Embeddable Browserbase live-view URL for a running session.
export const getRunLive = (id) => api.get(`/engine/run/${id}/live`).then((r) => r.data);
// LLM-generated developer-facing report.
export const getRunReport = (id, refresh) =>
  api.get(`/reports/run/${id}`, { params: refresh ? { refresh: true } : {} }).then((r) => r.data);
export const getBatchReport = (id, refresh) =>
  api.get(`/reports/batch/${id}`, { params: refresh ? { refresh: true } : {} }).then((r) => r.data);
export const listRuns = (params) => api.get("/runs", { params }).then((r) => r.data);
export const getRun = (id) => api.get(`/runs/${id}`).then((r) => r.data);
export const updateRun = (id, data) => api.patch(`/runs/${id}`, data).then((r) => r.data);
export const deleteRun = (id) => api.delete(`/runs/${id}`).then((r) => r.data);

// --- Steps ---
export const createStep = (data) => api.post("/steps", data).then((r) => r.data);
export const listSteps = (params) => api.get("/steps", { params }).then((r) => r.data);
export const getStep = (id) => api.get(`/steps/${id}`).then((r) => r.data);
export const deleteStep = (id) => api.delete(`/steps/${id}`).then((r) => r.data);

// --- Signals ---
export const createSignal = (data) => api.post("/signals", data).then((r) => r.data);
export const listSignals = (params) => api.get("/signals", { params }).then((r) => r.data);
export const getSignal = (id) => api.get(`/signals/${id}`).then((r) => r.data);
export const deleteSignal = (id) => api.delete(`/signals/${id}`).then((r) => r.data);

// --- Persona Panels ---
export const createPersonaPanel = (data) => api.post("/persona-panels", data).then((r) => r.data);
export const listPersonaPanels = (params) => api.get("/persona-panels", { params }).then((r) => r.data);
export const getPersonaPanel = (id) => api.get(`/persona-panels/${id}`).then((r) => r.data);
export const updatePersonaPanel = (id, data) => api.patch(`/persona-panels/${id}`, data).then((r) => r.data);
export const deletePersonaPanel = (id) => api.delete(`/persona-panels/${id}`).then((r) => r.data);

// --- Seed ---
export const seedData = () => api.post("/seed").then((r) => r.data);

// --- Persona Generator ---
export const generatePersonas = (data) => api.post("/generate-personas", data).then((r) => r.data);

// --- Prototype ---
export const listScreenGraphs = () => api.get("/prototype/graphs").then((r) => r.data);
export const getScreenGraph = (id) => api.get(`/prototype/graphs/${id}`).then((r) => r.data);
export const createScreenGraph = (data) => api.post("/prototype/graphs", data).then((r) => r.data);
export const updateScreenGraph = (id, data) => api.patch(`/prototype/graphs/${id}`, data).then((r) => r.data);
export const deleteScreenGraph = (id) => api.delete(`/prototype/graphs/${id}`).then((r) => r.data);
export const runPrototype = (data) => api.post("/prototype/run", data);

export default api;
