import React, { useState } from "react";
import { X, KeyRound } from "lucide-react";
import { toast } from "sonner";
import { api, formatApiErrorDetail } from "@/lib/api";

export default function ChangePasswordModal({ open, onClose }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (!open) return null;

  const reset = () => {
    setCurrent("");
    setNext("");
    setConfirm("");
    setError("");
  };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (next.length < 6) {
      setError("New password must be at least 6 characters");
      return;
    }
    if (next !== confirm) {
      setError("New passwords do not match");
      return;
    }
    setLoading(true);
    try {
      await api.post("/auth/change-password", { current_password: current, new_password: next });
      toast.success("Password changed successfully");
      reset();
      onClose();
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" data-testid="change-password-modal">
      <div className="w-full max-w-sm bg-card border border-border">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-accent" />
            <h3 className="font-head font-bold text-sm uppercase tracking-tight">Change Password</h3>
          </div>
          <button data-testid="change-password-close" onClick={() => { reset(); onClose(); }} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
        <form onSubmit={submit} className="p-5 space-y-4">
          <div>
            <label className="font-mono text-[10px] tracking-[0.2em] uppercase text-muted-foreground">Current Password</label>
            <input data-testid="current-password-input" type="password" required value={current} onChange={(e) => setCurrent(e.target.value)}
              className="mt-1 w-full bg-secondary border border-border px-3 py-2.5 outline-none focus:ring-2 focus:ring-accent text-sm font-mono" placeholder="••••••••" />
          </div>
          <div>
            <label className="font-mono text-[10px] tracking-[0.2em] uppercase text-muted-foreground">New Password</label>
            <input data-testid="new-password-input" type="password" required value={next} onChange={(e) => setNext(e.target.value)}
              className="mt-1 w-full bg-secondary border border-border px-3 py-2.5 outline-none focus:ring-2 focus:ring-accent text-sm font-mono" placeholder="min 6 characters" />
          </div>
          <div>
            <label className="font-mono text-[10px] tracking-[0.2em] uppercase text-muted-foreground">Confirm New Password</label>
            <input data-testid="confirm-password-input" type="password" required value={confirm} onChange={(e) => setConfirm(e.target.value)}
              className="mt-1 w-full bg-secondary border border-border px-3 py-2.5 outline-none focus:ring-2 focus:ring-accent text-sm font-mono" placeholder="••••••••" />
          </div>
          {error && (
            <div data-testid="change-password-error" className="border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive-foreground">{error}</div>
          )}
          <button data-testid="change-password-submit" type="submit" disabled={loading}
            className="w-full bg-accent text-white font-mono text-xs tracking-[0.15em] uppercase py-3 hover:bg-accent/90 transition-colors disabled:opacity-50">
            {loading ? "Updating…" : "Update Password"}
          </button>
        </form>
      </div>
    </div>
  );
}
