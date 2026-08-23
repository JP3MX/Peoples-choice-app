import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { api } from "@/lib/api";

const MAX_POLLS = 12;

export default function PaymentSuccess() {
  const navigate = useNavigate();
  const [state, setState] = useState("checking"); // checking | paid | timeout
  const [plan, setPlan] = useState(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get("session_id");
    if (!sessionId) {
      setState("timeout");
      return;
    }
    let polls = 0;
    let timer;
    const poll = async () => {
      try {
        const { data } = await api.get(`/payments/status/${sessionId}`);
        if (data.payment_status === "paid") {
          const st = await api.get("/billing/status");
          setPlan(st.data.plan);
          setState("paid");
          return;
        }
      } catch (e) {
        console.error("Payment status poll failed, retrying:", e);
      }
      polls += 1;
      if (polls >= MAX_POLLS) {
        setState("timeout");
        return;
      }
      timer = setTimeout(poll, 2000);
    };
    poll();
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center p-6" data-testid="payment-success-page">
      <div className="max-w-md w-full border border-border bg-card p-8 text-center">
        {state === "checking" && (
          <>
            <Loader2 className="h-10 w-10 text-primary animate-spin mx-auto mb-5" />
            <h1 className="font-head font-black text-2xl uppercase tracking-tight mb-2">Confirming payment</h1>
            <p className="text-muted-foreground text-sm">Hang tight while we activate your subscription…</p>
          </>
        )}
        {state === "paid" && (
          <>
            <CheckCircle2 className="h-12 w-12 text-primary mx-auto mb-5" />
            <h1 className="font-head font-black text-2xl uppercase tracking-tight mb-2" data-testid="payment-confirmed">
              You're on {plan}!
            </h1>
            <p className="text-muted-foreground text-sm mb-6">
              Subscription active. Troubleshooting is unlocked for your bay.
            </p>
            <button
              data-testid="go-to-app"
              onClick={() => navigate("/")}
              className="w-full bg-accent text-white py-3 font-mono text-xs tracking-[0.15em] uppercase hover:bg-accent/90 transition-colors"
            >
              Enter the hangar
            </button>
          </>
        )}
        {state === "timeout" && (
          <>
            <XCircle className="h-12 w-12 text-accent mx-auto mb-5" />
            <h1 className="font-head font-black text-2xl uppercase tracking-tight mb-2">Still processing</h1>
            <p className="text-muted-foreground text-sm mb-6">
              Payment is taking a moment. If it doesn't reflect shortly, refresh your billing status in the app.
            </p>
            <button
              onClick={() => navigate("/")}
              className="w-full border border-border py-3 font-mono text-xs tracking-[0.15em] uppercase hover:bg-secondary transition-colors"
            >
              Back to app
            </button>
          </>
        )}
      </div>
    </div>
  );
}
