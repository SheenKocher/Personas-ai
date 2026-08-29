import { REPORTS } from "@/constants/testIds";
import { FileText } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function Reports() {
  return (
    <div data-testid={REPORTS.container}>
      <div className="mb-8">
        <h1 className="text-2xl font-medium" style={{ color: "#F1F5F9" }}>
          Reports
        </h1>
        <p className="text-sm mt-1" style={{ color: "#94A3B8" }}>
          Aggregated friction analysis and test summaries
        </p>
      </div>

      <div
        data-testid={REPORTS.emptyState}
        className="rounded-xl flex flex-col items-center justify-center py-20"
        style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
      >
        <FileText className="w-12 h-12 mb-4" style={{ color: "#334155" }} />
        <h2 className="text-base font-medium mb-1" style={{ color: "#F1F5F9" }}>
          No reports yet
        </h2>
        <p className="text-sm mb-4" style={{ color: "#94A3B8" }}>
          Reports will appear here after completed test runs
        </p>
        <Button
          className="rounded-lg"
          style={{ background: "#2DD4BF", color: "#06231F" }}
          disabled
        >
          Coming Soon
        </Button>
      </div>
    </div>
  );
}
