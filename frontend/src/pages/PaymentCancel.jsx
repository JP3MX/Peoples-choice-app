import React from "react";
import { useNavigate } from "react-router-dom";
import { XCircle } from "lucide-react";

export default function PaymentCancel() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center p-6" data-testid="payment-cancel-page">
      <div className="max-w-md w-full border border-border bg-card p-8 text-center">
        <XCircle className="h-12 w-12 text-muted-foreground mx-auto mb-5" />
        <h1 className="font-head font-black text-2xl uppercase tracking-tight mb-2">Checkout canceled</h1>
        <p className="text-muted-foreground text-sm mb-6">No charge was made. You can pick a plan whenever you're ready.</p>
        <div className="flex gap-2">
          <button
            onClick={() => navigate("/pricing")}
            className="flex-1 bg-primary text-white py-3 font-mono text-xs tracking-[0.15em] uppercase hover:bg-primary/90 transition-colors"
          >
            View plans
          </button>
          <button
            onClick={() => navigate("/")}
            className="flex-1 border border-border py-3 font-mono text-xs tracking-[0.15em] uppercase hover:bg-secondary transition-colors"
          >
            Back to app
          </button>
        </div>
      </div>
    </div>
  );
}
