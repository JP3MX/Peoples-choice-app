import React, { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Plane, ArrowRight, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { api, formatApiErrorDetail } from "@/lib/api";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (!token) {
      setError("Missing reset token. Use the link from your email.");
      return;
    }
    if (password.length < 6) {
      setError("Password must be at least 6 characters");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    setLoading(true);
    try {
      await api.post("/auth/reset-password", { token, new_password: password });
      setDone(true);
      toast.success("Password updated");
      setTimeout(() => navigate("/login"), 1500);
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center p-6">
      <div className="w-full max-w-sm" data-testid="reset-password-page">
        <div className="flex items-center gap-2 mb-8">
          <div className="h-9 w-9 bg-accent flex items-center justify-center">
            <Plane className="h-5 w-5 text-white" strokeWidth={2.5} />
          </div>
          <span className="font-head font-black text-lg uppercase">Squawk King IA</span>
        </div>

        {done ? (
          <div className="border border-primary/40 bg-primary/10 p-6 text-center" data-testid="reset-success">
            <ShieldCheck className="h-10 w-10 text-primary mx-auto mb-3" />
            <h2 className="font-head font-bold text-xl mb-2">Password updated</h2>
            <p className="text-muted-foreground text-sm">Redirecting you to sign in…</p>
          </div>
        ) : (
          <form onSubmit={submit}>
            <p className="font-mono text-xs tracking-[0.3em] uppercase text-muted-foreground mb-2">Reset Access</p>
            <h2 className="font-head font-bold text-2xl mb-8">Set a new password</h2>

            {!token && (
              <div data-testid="reset-no-token" className="mb-4 border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive-foreground">
                This reset link is missing its token. Request a new link from the sign-in page.
              </div>
            )}

            <div className="mb-4">
              <label className="font-mono text-[11px] tracking-[0.2em] uppercase text-muted-foreground">New Password</label>
              <input
                data-testid="reset-password-input"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full bg-secondary border border-border px-3 py-2.5 outline-none focus:ring-2 focus:ring-accent text-sm font-mono"
                placeholder="min 6 characters"
              />
            </div>
            <div className="mb-6">
              <label className="font-mono text-[11px] tracking-[0.2em] uppercase text-muted-foreground">Confirm Password</label>
              <input
                data-testid="reset-confirm-input"
                type="password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="mt-1 w-full bg-secondary border border-border px-3 py-2.5 outline-none focus:ring-2 focus:ring-accent text-sm font-mono"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <div data-testid="reset-error" className="mb-4 border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive-foreground">
                {error}
              </div>
            )}

            <button
              data-testid="reset-submit"
              type="submit"
              disabled={loading}
              className="w-full bg-accent text-white font-mono text-sm tracking-[0.15em] uppercase py-3 flex items-center justify-center gap-2 hover:bg-accent/90 transition-colors disabled:opacity-50"
            >
              {loading ? "Updating…" : "Update Password"}
              {!loading && <ArrowRight className="h-4 w-4" />}
            </button>
            <button
              type="button"
              data-testid="reset-back"
              onClick={() => navigate("/login")}
              className="w-full mt-4 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Back to sign in
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
