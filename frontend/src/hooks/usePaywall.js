import { useState, useEffect, useCallback } from "react";
import { CreditCard } from "lucide-react";
import { Button } from "@/components/ui/button";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * usePaywall hook — checks run credits and provides a checkout flow.
 * Returns { canRun, credits, loading, PaywallGate }
 *   - canRun: boolean, true if the user can start a run right now
 *   - credits: { free_used, paid_credits, total_runs, price }
 *   - loading: boolean
 *   - PaywallGate: React component to render when canRun is false
 *   - refresh: function to re-check credits
 */
export function usePaywall() {
  const [credits, setCredits] = useState(null);
  const [loading, setLoading] = useState(true);
  const [purchasing, setPurchasing] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/payments/credits`);
      setCredits(res.data);
    } catch {
      setCredits({ can_run: true, free_used: false, paid_credits: 0, total_runs: 0, price: 1.0 });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handlePurchase = async () => {
    setPurchasing(true);
    try {
      const res = await axios.post(`${API}/payments/checkout`, {
        origin_url: window.location.origin,
      });
      window.location.href = res.data.checkout_url;
    } catch {
      setPurchasing(false);
    }
  };

  const canRun = credits?.can_run ?? true;

  function PaywallGate() {
    if (canRun || loading) return null;
    return (
      <div
        data-testid="paywall-gate"
        className="rounded-xl p-4 flex items-center gap-4 mb-4"
        style={{ background: "#F59E0B10", border: "0.5px solid #F59E0B30" }}
      >
        <CreditCard className="w-5 h-5 shrink-0" style={{ color: "#F59E0B" }} />
        <div className="flex-1">
          <p className="text-sm font-medium" style={{ color: "#F1F5F9" }}>
            Free run used
          </p>
          <p className="text-xs" style={{ color: "#94A3B8" }}>
            Purchase a run credit (${credits?.price?.toFixed(2) || "1.00"}) to continue testing.
          </p>
        </div>
        <Button
          data-testid="paywall-purchase-btn"
          onClick={handlePurchase}
          disabled={purchasing}
          className="rounded-lg shrink-0"
          style={{ background: "#2DD4BF", color: "#06231F" }}
        >
          <CreditCard className="w-4 h-4 mr-1.5" />
          {purchasing ? "Redirecting..." : "Purchase credit"}
        </Button>
      </div>
    );
  }

  return { canRun, credits, loading, PaywallGate, refresh };
}
