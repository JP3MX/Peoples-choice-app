import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function AccountSettings() {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const { logout } = useAuth();
  const navigate = useNavigate();

  const deleteAccount = async () => {
    if (confirm !== "DELETE") {
      setError("Type DELETE exactly to confirm.");
      return;
    }
    setWorking(true);
    setError("");
    try {
      await api.delete("/auth/account", { data: { password, confirm } });
      logout();
      navigate("/login", { replace: true });
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail) || "Account deletion failed.");
    } finally {
      setWorking(false);
    }
  };

  return (
    <main className="min-h-screen bg-background text-foreground px-6 py-12">
      <div className="max-w-xl mx-auto space-y-8">
        <div>
          <button onClick={() => navigate("/")} className="text-primary underline mb-6">Back to app</button>
          <h1 className="font-head font-black text-4xl uppercase">Account Settings</h1>
        </div>
        <section className="border border-destructive/50 p-5 space-y-4">
          <h2 className="font-head font-bold text-xl text-destructive">Permanently delete account</h2>
          <p className="text-sm text-muted-foreground">This cancels active billing and permanently deletes your stored aircraft, sessions, messages, logbook drafts, manuals, media, and account.</p>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Current password" className="w-full bg-secondary border border-border px-3 py-2.5" />
          <input value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="Type DELETE" className="w-full bg-secondary border border-border px-3 py-2.5 font-mono" />
          {error && <p className="text-sm text-destructive">{error}</p>}
          <button disabled={working || confirm !== "DELETE"} onClick={deleteAccount} className="w-full bg-destructive text-white py-3 font-mono uppercase disabled:opacity-40">
            {working ? "Deleting…" : "Delete account permanently"}
          </button>
        </section>
        <div className="flex gap-4 text-sm">
          <Link className="text-primary underline" to="/privacy">Privacy policy</Link>
          <Link className="text-primary underline" to="/account-deletion">Deletion information</Link>
        </div>
      </div>
    </main>
  );
}
