import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Plane, Plus, MessageSquare, Trash2, LogOut, ChevronDown, PanelRightClose, PanelRightOpen, KeyRound, Zap, UserCog,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import ChatPanel from "@/components/ChatPanel";
import Workbench from "@/components/Workbench";
import ChangePasswordModal from "@/components/ChangePasswordModal";
import UpgradeModal from "@/components/UpgradeModal";

export default function Workspace() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [aircraftList, setAircraftList] = useState([]);
  const [showWorkbench, setShowWorkbench] = useState(true);
  const [acMenu, setAcMenu] = useState(false);
  const [showChangePw, setShowChangePw] = useState(false);
  const [billing, setBilling] = useState(null);
  const [showUpgrade, setShowUpgrade] = useState(false);
  const [upgradeReason, setUpgradeReason] = useState("");

  const activeAircraft = aircraftList.find((a) => a.id === activeSession?.aircraft_id) || null;

  const loadBilling = useCallback(async () => {
    const { data } = await api.get("/billing/status");
    setBilling(data);
  }, []);

  const loadSessions = useCallback(async () => {
    const { data } = await api.get("/sessions");
    setSessions(data);
    return data;
  }, []);
  const loadAircraft = useCallback(async () => {
    const { data } = await api.get("/aircraft");
    setAircraftList(data);
  }, []);

  useEffect(() => {
    (async () => {
      await loadAircraft();
      await loadBilling();
      const s = await loadSessions();
      if (s.length > 0) setActiveSession(s[0]);
    })();
  }, [loadSessions, loadAircraft, loadBilling]);

  const handlePaywall = (reason) => {
    setUpgradeReason(reason);
    setShowUpgrade(true);
  };

  const newSession = async () => {
    const { data } = await api.post("/sessions", { title: "New Troubleshooting Session", aircraft_id: activeAircraft?.id || null });
    setSessions((s) => [data, ...s]);
    setActiveSession(data);
  };

  const delSession = async (id, e) => {
    e.stopPropagation();
    await api.delete(`/sessions/${id}`);
    const next = sessions.filter((s) => s.id !== id);
    setSessions(next);
    if (activeSession?.id === id) setActiveSession(next[0] || null);
  };

  const assignAircraft = async (ac) => {
    setAcMenu(false);
    if (!activeSession) {
      const { data } = await api.post("/sessions", { title: "New Troubleshooting Session", aircraft_id: ac.id });
      setSessions((s) => [data, ...s]);
      setActiveSession(data);
      return;
    }
    const { data } = await api.put(`/sessions/${activeSession.id}`, { aircraft_id: ac.id, title: activeSession.title });
    setActiveSession(data);
    setSessions((s) => s.map((x) => (x.id === data.id ? data : x)));
    toast.success(`Aircraft set: ${ac.make} ${ac.model}`);
  };

  const addAircraft = async () => {
    const { data } = await api.post("/aircraft", { make: "", model: "", tail_number: "New Aircraft", confirmed: false });
    await loadAircraft();
    assignAircraft(data);
  };

  const onAircraftSaved = (updated) => {
    setAircraftList((l) => l.map((a) => (a.id === updated.id ? updated : a)));
  };

  return (
    <div className="h-screen w-full flex bg-background text-foreground overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 border-r border-border flex flex-col shrink-0">
        <div className="px-4 py-4 border-b border-border flex items-center gap-2.5">
          <div className="h-8 w-8 bg-accent flex items-center justify-center shrink-0">
            <Plane className="h-5 w-5 text-white" strokeWidth={2.5} />
          </div>
          <div className="min-w-0">
            <p className="font-head font-black text-sm uppercase tracking-tight leading-none">Squawk King</p>
            <p className="font-mono text-[9px] tracking-[0.2em] uppercase text-accent mt-0.5">IA · Maint. Agent</p>
          </div>
        </div>

        {/* plan / billing */}
        <div className="px-3 py-3 border-b border-border">
          <button
            data-testid="billing-badge"
            onClick={() => navigate("/pricing")}
            className="w-full border border-border bg-secondary/40 px-3 py-2 flex items-center justify-between hover:border-accent/60 transition-colors group"
          >
            <span className="flex items-center gap-1.5 min-w-0">
              <Zap className="h-3.5 w-3.5 text-accent shrink-0" />
              <span className="font-mono text-[10px] tracking-widest uppercase truncate">
                {!billing
                  ? "…"
                  : billing.trial_active
                  ? `Trial · ${billing.trial_days_left}d left`
                  : billing.plan && billing.plan !== "none"
                  ? `${billing.plan}${billing.remaining != null ? ` · ${billing.remaining} left` : ""}`
                  : "Trial ended"}
              </span>
            </span>
            <span className="font-mono text-[9px] tracking-widest uppercase text-accent opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
              {billing && billing.plan === "unlimited" ? "Plans" : "Upgrade"}
            </span>
          </button>
        </div>

        {/* aircraft selector */}
        <div className="p-3 border-b border-border relative">
          <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-muted-foreground mb-2">Active Aircraft</p>
          <button
            data-testid="aircraft-selector"
            onClick={() => setAcMenu(!acMenu)}
            className="w-full border border-border bg-secondary/40 px-3 py-2.5 flex items-center justify-between hover:border-white/20 transition-colors"
          >
            <span className="font-mono text-xs truncate text-left">
              {activeAircraft ? `${activeAircraft.tail_number || activeAircraft.make} · ${activeAircraft.make} ${activeAircraft.model}` : "None selected"}
            </span>
            <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
          </button>
          {acMenu && (
            <div className="absolute left-3 right-3 mt-1 z-20 bg-card border border-border shadow-xl" data-testid="aircraft-menu">
              {aircraftList.map((a) => (
                <button
                  key={a.id}
                  data-testid={`aircraft-option-${a.id}`}
                  onClick={() => assignAircraft(a)}
                  className="w-full text-left px-3 py-2 hover:bg-secondary transition-colors border-b border-border last:border-0"
                >
                  <span className="font-mono text-xs">{a.tail_number || "—"}</span>
                  <span className="block text-[11px] text-muted-foreground">{a.make} {a.model} {a.confirmed ? "· ✓" : ""}</span>
                </button>
              ))}
              <button onClick={addAircraft} data-testid="aircraft-add" className="w-full text-left px-3 py-2 text-primary font-mono text-xs flex items-center gap-1.5 hover:bg-secondary transition-colors">
                <Plus className="h-3.5 w-3.5" /> Add aircraft
              </button>
            </div>
          )}
        </div>

        {/* sessions */}
        <div className="p-3">
          <button
            data-testid="new-session"
            onClick={newSession}
            className="w-full bg-primary text-white py-2.5 font-mono text-xs tracking-widest uppercase flex items-center justify-center gap-2 hover:bg-primary/90 transition-colors"
          >
            <Plus className="h-4 w-4" /> New Squawk
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-3 space-y-1" data-testid="session-list">
          {sessions.map((s) => (
            <button
              key={s.id}
              data-testid={`session-${s.id}`}
              onClick={() => setActiveSession(s)}
              className={`w-full group flex items-center gap-2 px-3 py-2.5 text-left transition-colors border ${
                activeSession?.id === s.id ? "border-accent/50 bg-accent/10" : "border-transparent hover:bg-secondary"
              }`}
            >
              <MessageSquare className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <span className="flex-1 text-xs truncate">{s.title}</span>
              <Trash2
                onClick={(e) => delSession(s.id, e)}
                className="h-3.5 w-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-destructive transition-opacity"
              />
            </button>
          ))}
        </div>

        {/* user */}
        <div className="border-t border-border p-3 flex items-center justify-between">
          <div className="min-w-0">
            <p className="text-xs font-medium truncate">{user?.name}</p>
            <p className="font-mono text-[10px] text-muted-foreground truncate">{user?.email}</p>
          </div>
          <div className="flex items-center gap-1">
            <button data-testid="account-settings-btn" onClick={() => navigate("/account")} title="Account settings" className="text-muted-foreground hover:text-primary transition-colors p-1">
              <UserCog className="h-4 w-4" />
            </button>
            <button data-testid="change-password-btn" onClick={() => setShowChangePw(true)} title="Change password" className="text-muted-foreground hover:text-primary transition-colors p-1">
              <KeyRound className="h-4 w-4" />
            </button>
            <button data-testid="logout-btn" onClick={logout} title="Sign out" className="text-muted-foreground hover:text-accent transition-colors p-1">
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Center chat */}
      <main className="flex-1 min-w-0 flex flex-col relative">
        <button
          data-testid="toggle-workbench"
          onClick={() => setShowWorkbench(!showWorkbench)}
          className="absolute top-3 right-3 z-10 h-8 w-8 border border-border bg-card flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
        >
          {showWorkbench ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
        </button>
        {activeSession ? (
          <ChatPanel
            session={activeSession}
            aircraft={activeAircraft}
            onPaywall={handlePaywall}
            onSessionUpdate={(s) => {
              setActiveSession(s);
              setSessions((list) => list.map((x) => (x.id === s.id ? s : x)));
            }}
          />
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
            <Plane className="h-10 w-10 text-accent mb-4" />
            <h2 className="font-head font-black text-2xl uppercase tracking-tight mb-2">No active squawk</h2>
            <p className="text-muted-foreground text-sm mb-6 max-w-sm">Start a new troubleshooting session to begin diagnosing a symptom.</p>
            <button onClick={newSession} className="bg-accent text-white px-6 py-3 font-mono text-xs tracking-widest uppercase hover:bg-accent/90 transition-colors">
              Start New Squawk
            </button>
          </div>
        )}
      </main>

      {/* Right workbench */}
      {showWorkbench && (
        <section className="w-[380px] shrink-0">
          <Workbench aircraft={activeAircraft} onAircraftSaved={onAircraftSaved} />
        </section>
      )}

      <ChangePasswordModal open={showChangePw} onClose={() => setShowChangePw(false)} />
      <UpgradeModal
        open={showUpgrade}
        reason={upgradeReason}
        onClose={() => {
          setShowUpgrade(false);
          loadBilling();
        }}
      />
    </div>
  );
}
