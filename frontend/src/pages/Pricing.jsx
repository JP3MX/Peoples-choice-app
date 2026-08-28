import React from "react";
import { useNavigate } from "react-router-dom";
import { Plane, ArrowLeft } from "lucide-react";
import PricingPlans from "@/components/PricingPlans";

export default function Pricing() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="border-b border-border px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="h-8 w-8 bg-accent flex items-center justify-center">
            <Plane className="h-5 w-5 text-white" strokeWidth={2.5} />
          </div>
          <span className="font-head font-black text-sm uppercase tracking-tight">Squawk King — Plans</span>
        </div>
        <button
          data-testid="back-to-app"
          onClick={() => navigate("/")}
          className="font-mono text-xs tracking-widest uppercase text-muted-foreground hover:text-foreground flex items-center gap-1.5 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Back to bay
        </button>
      </div>
      <div className="max-w-5xl mx-auto px-6 py-14">
        <p className="font-mono text-xs tracking-[0.3em] uppercase text-accent mb-3">Pricing</p>
        <h1 className="font-head font-black text-4xl sm:text-5xl uppercase tracking-tight leading-[0.95] mb-4">
          Troubleshoot without limits
        </h1>
        <p className="text-muted-foreground max-w-xl mb-12">
          Every account starts with a 7-day free trial of full troubleshooting. Then continue monthly or save with annual billing. Cancel anytime.
        </p>
        <PricingPlans />
      </div>
    </div>
  );
}
