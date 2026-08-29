import { DIFF } from "@/constants/testIds";
import { GitCompareArrows } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function CrossStageDiff() {
  return (
    <div data-testid={DIFF.container}>
      <div className="mb-8">
        <h1 className="text-2xl font-medium" style={{ color: "#F1F5F9" }}>
          Cross-Stage Diff
        </h1>
        <p className="text-sm mt-1" style={{ color: "#94A3B8" }}>
          Compare prototype vs. runtime friction signals side by side
        </p>
      </div>

      <div
        data-testid={DIFF.emptyState}
        className="rounded-xl flex flex-col items-center justify-center py-20"
        style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
      >
        <GitCompareArrows className="w-12 h-12 mb-4" style={{ color: "#334155" }} />
        <h2 className="text-base font-medium mb-1" style={{ color: "#F1F5F9" }}>
          No diff data yet
        </h2>
        <p className="text-sm mb-4" style={{ color: "#94A3B8" }}>
          Run both prototype and runtime stages to generate a comparison
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
