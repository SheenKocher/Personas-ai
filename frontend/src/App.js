import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import Layout from "@/components/Layout";
import LiveGrid from "@/pages/LiveGrid";
import PersonaPanels from "@/pages/PersonaPanels";
import NewRun from "@/pages/NewRun";
import Reports from "@/pages/Reports";
import CrossStageDiff from "@/pages/CrossStageDiff";

function App() {
  return (
    <BrowserRouter>
      <Toaster
        theme="dark"
        position="top-right"
        toastOptions={{
          style: {
            background: "#141B2E",
            border: "0.5px solid #1E293B",
            color: "#F1F5F9",
          },
        }}
      />
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<LiveGrid />} />
          <Route path="persona-panels" element={<PersonaPanels />} />
          <Route path="new-run" element={<NewRun />} />
          <Route path="reports" element={<Reports />} />
          <Route path="cross-stage-diff" element={<CrossStageDiff />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
