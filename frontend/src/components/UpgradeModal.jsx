import React from "react";
import { X } from "lucide-react";
import PricingPlans from "@/components/PricingPlans";

export default function UpgradeModal({ open, onClose, reason }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 overflow-y-auto" data-testid="upgrade-modal">
      <div className="w-full max-w-4xl bg-background border border-border my-8">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div>
            <p className="font-mono text-[10px] tracking-[0.3em] uppercase text-accent">Upgrade Required</p>
            <h3 className="font-head font-black text-xl uppercase tracking-tight mt-0.5">Keep the shop running</h3>
          </div>
          <button data-testid="upgrade-modal-close" onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="p-6">
          {reason && (
            <div className="mb-6 border border-accent/40 bg-accent/10 px-4 py-3 text-sm text-accent" data-testid="upgrade-reason">
              {reason}
            </div>
          )}
          <PricingPlans onDone={onClose} />
        </div>
      </div>
    </div>
  );
}
