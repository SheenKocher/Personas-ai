import { useEffect, useRef, useState } from "react";
import { getRunLive } from "@/lib/api";
import { ExternalLink } from "lucide-react";

/**
 * Embeds the Browserbase live view for a run's browser session.
 * Polls GET /api/engine/run/{id}/live until the session ends.
 */
export default function LiveRunView({ runId }) {
  const [state, setState] = useState({ status: "loading" });
  const timer = useRef(null);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const data = await getRunLive(runId);
        if (cancelled) return;
        setState(data);
        // Keep polling while the session is still coming up or live.
        if (data.status === "pending" || data.status === "live") {
          timer.current = setTimeout(poll, 3000);
        }
      } catch (e) {
        if (cancelled) return;
        setState({ status: "error", detail: e?.response?.data?.detail || "Failed to load live view" });
        timer.current = setTimeout(poll, 5000);
      }
    };

    poll();
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [runId]);

  const { status, live_url, replay_url, detail } = state;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs" style={{ color: "#94A3B8" }}>
          {status === "live" && (
            <span className="flex items-center gap-1.5" style={{ color: "#F43F5E" }}>
              <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: "#F43F5E" }} />
              LIVE
            </span>
          )}
          {status === "pending" && "Waiting for browser session…"}
          {status === "loading" && "Connecting…"}
          {status === "ended" && "Session ended"}
          {status === "error" && (detail || "Live view unavailable")}
        </div>
        {replay_url && (
          <a
            href={replay_url}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 text-xs hover:underline"
            style={{ color: "#2DD4BF" }}
          >
            Open in Browserbase <ExternalLink className="w-3 h-3" />
          </a>
        )}
      </div>

      <div
        className="rounded-lg overflow-hidden flex items-center justify-center"
        style={{ background: "#0B0F1A", border: "0.5px solid #1E293B", aspectRatio: "16 / 10" }}
      >
        {status === "live" && live_url ? (
          <iframe
            title="Browserbase live view"
            src={live_url}
            className="w-full h-full"
            style={{ border: 0 }}
            sandbox="allow-same-origin allow-scripts"
            allow="fullscreen"
          />
        ) : (
          <div className="text-xs" style={{ color: "#64748B" }}>
            {status === "pending" || status === "loading"
              ? "Live view will appear here once the browser starts."
              : status === "ended"
              ? "The run has finished — use the recording link above."
              : "No live view available."}
          </div>
        )}
      </div>
    </div>
  );
}
