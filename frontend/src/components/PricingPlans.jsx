import React, { useEffect, useState } from "react";
import { Check, Loader2, Zap, Settings } from "lucide-react";
import { toast } from "sonner";
import { api, formatApiErrorDetail } from "@/lib/api";

const TIER_ACCENT = {
  basic: "border-border",
  pro: "border-primary",
  unlimited: "border-accent",
};

export default function PricingPlans({ compact = false, onDone }) {
  const [plans, setPlans] = useState([]);
  const [status, setStatus] = useState(null);
  const [loadingKey, setLoadingKey] = useState(null);
  const [portalLoading, setPortalLoading] = useState(false);

  useEffect(() => {
    api.get("/billing/status").then((r) => {
      setPlans(r.data.plans || []);
      setStatus(r.data);
    });
  }, []);

  const subscribe = async (lookup_key) => {
    setLoadingKey(lookup_key);
    try {
      const { data } = await api.post("/payments/checkout", {
        lookup_key,
        origin_url: window.location.origin,
      });
      onDone?.();
      window.location.href = data.checkout_url;
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Checkout failed");
      setLoadingKey(null);
    }
  };

  const openPortal = async () => {
    setPortalLoading(true);
    try {
      const { data } = await api.post("/billing/portal", { return_url: window.location.href });
      window.location.href = data.portal_url;
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Could not open billing portal");
      setPortalLoading(false);
    }
  };

  const currentTier = status?.plan;

  return (
    <div>
      {status && (
        <div className="mb-6 flex items-center gap-2 font-mono text-[11px] tracking-widest uppercase text-muted-foreground" data-testid="current-plan-line">
          <Zap className="h-3.5 w-3.5 text-accent" />
          {status.trial_active
            ? `Free trial · ${status.trial_days_left} day${status.trial_days_left === 1 ? "" : "s"} left`
            : currentTier && currentTier !== "none" && currentTier !== "trial"
            ? `Current plan: ${currentTier}${status.remaining != null ? ` · ${status.remaining} tokens left` : ""}`
            : "Trial ended — choose a plan to keep troubleshooting"}
        </div>
      )}
      <div className={`grid gap-4 ${compact ? "grid-cols-1" : "md:grid-cols-3"}`}>
        {plans.map((p) => {
          const isCurrent = currentTier === p.tier;
          return (
            <div
              key={p.lookup_key}
              data-testid={`plan-card-${p.tier}`}
              className={`border ${TIER_ACCENT[p.tier]} bg-card p-6 flex flex-col ${p.tier === "pro" ? "relative" : ""}`}
            >
              {p.tier === "pro" && (
                <span className="absolute -top-2.5 left-6 bg-primary text-white font-mono text-[9px] tracking-[0.2em] uppercase px-2 py-0.5">
                  Popular
                </span>
              )}
              <p className="font-mono text-[11px] tracking-[0.3em] uppercase text-muted-foreground">{p.name}</p>
              <div className="mt-3 flex items-baseline gap-1">
                <span className="font-head font-black text-4xl">${p.price}</span>
                <span className="text-muted-foreground text-sm">/mo</span>
              </div>
              <ul className="mt-5 space-y-2 flex-1">
                {p.features.map((f, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-foreground/85">
                    <Check className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                    {f}
                  </li>
                ))}
              </ul>
              <button
                data-testid={`subscribe-${p.tier}`}
                disabled={loadingKey || isCurrent}
                onClick={() => subscribe(p.lookup_key)}
                className={`mt-6 w-full py-3 font-mono text-xs tracking-[0.15em] uppercase flex items-center justify-center gap-2 transition-colors disabled:opacity-60 ${
                  p.tier === "unlimited"
                    ? "bg-accent text-white hover:bg-accent/90"
                    : "bg-primary text-white hover:bg-primary/90"
                }`}
              >
                {loadingKey === p.lookup_key ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : isCurrent ? (
                  "Current Plan"
                ) : (
                  `Choose ${p.name}`
                )}
              </button>
            </div>
          );
        })}
      </div>
      <p className="mt-5 font-mono text-[10px] text-muted-foreground/60 text-center">
        Test mode · use card 4242 4242 4242 4242, any future expiry, any CVC.
      </p>
      {status?.can_manage && (
        <div className="mt-6 text-center">
          <button
            data-testid="manage-subscription"
            onClick={openPortal}
            disabled={portalLoading}
            className="inline-flex items-center gap-2 border border-border px-5 py-2.5 font-mono text-xs tracking-[0.15em] uppercase hover:bg-secondary transition-colors disabled:opacity-50"
          >
            {portalLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Settings className="h-4 w-4" />}
            Manage / Cancel Subscription
          </button>
          <p className="mt-2 font-mono text-[10px] text-muted-foreground/60">
            Update payment method, switch plans, or cancel in the Stripe billing portal.
          </p>
        </div>
      )}
    </div>
  );
}
