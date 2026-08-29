import { AlertTriangle } from "lucide-react";

export function Spinner({ size = "md" }) {
  const dim = size === "sm" ? "w-4 h-4" : size === "lg" ? "w-8 h-8" : "w-6 h-6";
  return (
    <div className="flex items-center justify-center h-64">
      <div
        className={`${dim} border-2 rounded-full animate-spin`}
        style={{ borderColor: "#2DD4BF", borderTopColor: "transparent" }}
      />
    </div>
  );
}

export function ErrorBanner({ message, onRetry }) {
  return (
    <div
      data-testid="error-banner"
      className="rounded-xl p-4 flex items-center gap-3"
      style={{ background: "#F43F5E10", border: "0.5px solid #F43F5E30" }}
    >
      <AlertTriangle className="w-5 h-5 shrink-0" style={{ color: "#F43F5E" }} />
      <span className="text-sm flex-1" style={{ color: "#F1F5F9" }}>
        {message || "Something went wrong"}
      </span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-xs px-3 py-1.5 rounded-lg shrink-0"
          style={{ background: "#F43F5E15", color: "#F43F5E" }}
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ icon: Icon, title, description }) {
  return (
    <div
      className="rounded-xl flex flex-col items-center justify-center py-16"
      style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}
    >
      {Icon && <Icon className="w-10 h-10 mb-3" style={{ color: "#334155" }} />}
      <h2 className="text-sm font-medium mb-1" style={{ color: "#F1F5F9" }}>{title}</h2>
      {description && <p className="text-xs" style={{ color: "#64748B" }}>{description}</p>}
    </div>
  );
}
