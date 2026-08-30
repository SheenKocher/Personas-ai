import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { CheckCircle, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/shared";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function PaymentSuccess() {
  const [params] = useSearchParams();
  const sessionId = params.get("session_id");
  const [status, setStatus] = useState("checking");

  useEffect(() => {
    if (!sessionId) { setStatus("error"); return; }
    let attempts = 0;
    const poll = setInterval(async () => {
      attempts += 1;
      if (attempts > 15) { clearInterval(poll); setStatus("timeout"); return; }
      try {
        const res = await axios.get(`${API}/payments/status/${sessionId}`);
        if (res.data.payment_status === "paid") {
          clearInterval(poll);
          setStatus("paid");
        }
      } catch {
        clearInterval(poll);
        setStatus("error");
      }
    }, 2000);
    return () => clearInterval(poll);
  }, [sessionId]);

  return (
    <div className="max-w-md mx-auto mt-20 text-center">
      {status === "checking" && (
        <>
          <Spinner />
          <p className="text-sm mt-4" style={{ color: "#94A3B8" }}>Confirming payment...</p>
        </>
      )}
      {status === "paid" && (
        <div className="rounded-xl p-8" style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
          <CheckCircle className="w-12 h-12 mx-auto mb-4" style={{ color: "#10B981" }} />
          <h1 className="text-xl font-medium mb-2" style={{ color: "#F1F5F9" }}>Payment confirmed</h1>
          <p className="text-sm mb-6" style={{ color: "#94A3B8" }}>Your run credit is ready to use.</p>
          <Link to="/">
            <Button data-testid="payment-success-continue" className="rounded-lg" style={{ background: "#2DD4BF", color: "#06231F" }}>
              Back to app
            </Button>
          </Link>
        </div>
      )}
      {(status === "error" || status === "timeout") && (
        <div className="rounded-xl p-8" style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
          <XCircle className="w-12 h-12 mx-auto mb-4" style={{ color: "#F43F5E" }} />
          <h1 className="text-xl font-medium mb-2" style={{ color: "#F1F5F9" }}>
            {status === "timeout" ? "Still processing" : "Something went wrong"}
          </h1>
          <p className="text-sm mb-6" style={{ color: "#94A3B8" }}>
            {status === "timeout" ? "Payment may still be processing. Check back shortly." : "Please try again."}
          </p>
          <Link to="/">
            <Button className="rounded-lg" style={{ background: "#2DD4BF", color: "#06231F" }}>Back to app</Button>
          </Link>
        </div>
      )}
    </div>
  );
}

export function PaymentCancel() {
  return (
    <div className="max-w-md mx-auto mt-20 text-center">
      <div className="rounded-xl p-8" style={{ background: "#141B2E", border: "0.5px solid #1E293B" }}>
        <XCircle className="w-12 h-12 mx-auto mb-4" style={{ color: "#F59E0B" }} />
        <h1 className="text-xl font-medium mb-2" style={{ color: "#F1F5F9" }}>Payment cancelled</h1>
        <p className="text-sm mb-6" style={{ color: "#94A3B8" }}>No charge was made. You can try again anytime.</p>
        <Link to="/">
          <Button data-testid="payment-cancel-back" className="rounded-lg" style={{ background: "#2DD4BF", color: "#06231F" }}>
            Back to app
          </Button>
        </Link>
      </div>
    </div>
  );
}
