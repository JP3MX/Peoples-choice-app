import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function AccountSettings() {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const { logout } = useAuth();
  const navigate = useNavigate();

  const removeAccount = async () => {
    if (confirmation !== "DELETE") {
      toast.error('Type DELETE to confirm');
      return;
    }
    setBusy(true);
    try {
      await api.delete("/auth/account", { data: { password } });
      logout();
      navigate("/login", { replace: true });
      toast.success("Account and associated data deleted");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Account deletion failed; nothing was deleted");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen bg-background text-foreground px-5 py-10">
      <section className="max-w-2xl mx-auto bg-card border border-border p-6 md:p-10">
        <p className="font-mono text-xs tracking-[0.25em] uppercase text-primary mb-3">Account Settings</p>
        <h1 className="font-head font-black text-3xl uppercase mb-8">Your data</h1>
        <div className="border border-destructive/50 bg-destructive/5 p-5">
          <h2 className="font-bold text-lg mb-2">Permanently delete account</h2>
          <p className="text-sm text-muted-foreground mb-5">This deletes your aircraft, manuals, media, sessions, messages, logbook drafts, and account. An active subscription is canceled first. This cannot be undone.</p>
          <label className="block text-xs font-mono uppercase tracking-wider mb-1">Current password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full bg-background border border-border px-3 py-2 mb-4" />
          <label className="block text-xs font-mono uppercase tracking-wider mb-1">Type DELETE</label>
          <input value={confirmation} onChange={(e) => setConfirmation(e.target.value)} className="w-full bg-background border border-border px-3 py-2 mb-4" />
          <button disabled={busy || !password} onClick={removeAccount} className="bg-destructive text-white px-4 py-2 font-mono text-xs uppercase disabled:opacity-50">
            {busy ? "Deleting…" : "Delete account permanently"}
          </button>
        </div>
        <div className="mt-8 flex flex-wrap gap-4 font-mono text-xs">
          <Link to="/" className="text-primary hover:underline">Return to app</Link>
          <Link to="/privacy" className="text-muted-foreground hover:text-foreground">Privacy</Link>
          <Link to="/terms" className="text-muted-foreground hover:text-foreground">Terms & Safety</Link>
        </div>
      </section>
    </main>
  );
}
