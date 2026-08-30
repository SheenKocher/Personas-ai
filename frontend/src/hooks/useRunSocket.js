import { useEffect, useRef, useState } from "react";

const WS_URL = `${(process.env.REACT_APP_BACKEND_URL || "").replace(/^http/, "ws")}/api/ws/runs`;

/**
 * Subscribes to the live run event stream (step_update / run_complete /
 * run_paused / run_resumed) and returns only the events for `runId`.
 * One socket per mounted consumer — the backend broadcasts to everyone and
 * we filter client-side, since the server doesn't do per-run subscriptions.
 */
export default function useRunSocket(runId) {
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);

  useEffect(() => {
    if (!runId) return undefined;
    setEvents([]);

    let cancelled = false;
    let retryTimer = null;

    const connect = () => {
      if (cancelled) return;
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => !cancelled && setConnected(true);
      ws.onclose = () => {
        if (cancelled) return;
        setConnected(false);
        retryTimer = setTimeout(connect, 3000);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (evt) => {
        if (cancelled) return;
        try {
          const msg = JSON.parse(evt.data);
          if (msg.run_id === runId) {
            setEvents((prev) => [...prev, msg]);
          }
        } catch {
          // ignore malformed frames
        }
      };
    };

    connect();
    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      wsRef.current?.close();
    };
  }, [runId]);

  return { events, connected };
}
