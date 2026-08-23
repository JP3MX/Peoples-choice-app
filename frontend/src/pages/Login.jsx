import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plane, ArrowRight, Wrench } from "lucide-react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function Login() {
  const [mode, setMode] = useState("login"); // login | register | forgot | reset
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [info, setInfo] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const switchMode = (m) => {
    setMode(m);
    setError("");
    setInfo("");
  };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setInfo("");
    setLoading(true);
    try {
      if (mode === "login" || mode === "register") {
        const path = mode === "login" ? "/auth/login" : "/auth/register";
        const body = mode === "login" ? { email, password } : { email, password, name };
        const { data } = await api.post(path, body);
        login(data.token, data.user);
        navigate("/");
      } else if (mode === "forgot") {
        await api.post("/auth/forgot-password", { email, origin_url: window.location.origin });
        setInfo("If an account with that email exists, a password reset link has been sent. Check your inbox.");
      }
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  const headers = {
    login: ["Access Hangar", "Sign in to your bay"],
    register: ["New Mechanic", "Create your account"],
    forgot: ["Reset Access", "Forgot your password?"],
  };
  const submitLabels = {
    login: "Sign In",
    register: "Create Account",
    forgot: "Send Reset Link",
  };

  return (
    <div className="min-h-screen w-full flex bg-background text-foreground">
      {/* Left brand panel */}
      <div className="hidden lg:flex flex-col justify-between w-[42%] border-r border-border p-12 grid-bg relative overflow-hidden">
        <div className="relative z-10 flex items-center gap-3">
          <div className="h-10 w-10 bg-accent flex items-center justify-center">
            <Plane className="h-6 w-6 text-white" strokeWidth={2.5} />
          </div>
          <span className="font-head font-black text-xl tracking-tight uppercase">Squawk King IA</span>
        </div>
        <div className="relative z-10 max-w-md">
          <p className="font-mono text-xs tracking-[0.3em] uppercase text-accent mb-4">Maintenance Troubleshooting Agent</p>
          <h1 className="font-head font-black text-4xl xl:text-5xl leading-[0.95] tracking-tight uppercase">
            Squawk in.<br />Root cause out.
          </h1>
          <p className="text-muted-foreground mt-6 leading-relaxed">
            A mechanic-first troubleshooting agent for piston trainers. Most-likely cause first, sequenced steps, and
            every aircraft-specific instruction cited to the approved manual and ATA chapter.
          </p>
        </div>
        <div className="relative z-10 font-mono text-[11px] tracking-widest uppercase text-muted-foreground/60">
          Cessna · Piper · Lycoming · Rotax
        </div>
      </div>

      {/* Right form */}
      <div className="flex-1 flex items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-sm" data-testid="auth-form">
          <div className="flex items-center gap-2 mb-8 lg:hidden">
            <div className="h-9 w-9 bg-accent flex items-center justify-center">
              <Plane className="h-5 w-5 text-white" strokeWidth={2.5} />
            </div>
            <span className="font-head font-black text-lg uppercase">Squawk King IA</span>
          </div>

          <p className="font-mono text-xs tracking-[0.3em] uppercase text-muted-foreground mb-2">
            {headers[mode][0]}
          </p>
          <h2 className="font-head font-bold text-2xl mb-8">{headers[mode][1]}</h2>

          {mode === "register" && (
            <div className="mb-4">
              <label className="font-mono text-[11px] tracking-[0.2em] uppercase text-muted-foreground">Name</label>
              <input
                data-testid="name-input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 w-full bg-secondary border border-border px-3 py-2.5 outline-none focus:ring-2 focus:ring-accent text-sm"
                placeholder="A&P Mechanic"
              />
            </div>
          )}

          {(mode === "login" || mode === "register" || mode === "forgot") && (
            <div className="mb-4">
              <label className="font-mono text-[11px] tracking-[0.2em] uppercase text-muted-foreground">Email</label>
              <input
                data-testid="email-input"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full bg-secondary border border-border px-3 py-2.5 outline-none focus:ring-2 focus:ring-accent text-sm font-mono"
                placeholder="mechanic@squawkking.io"
              />
            </div>
          )}

          {mode === "forgot" && (
            <p className="text-sm text-muted-foreground mb-6 -mt-1 leading-relaxed">
              Enter your account email and we'll send a secure reset link to your inbox. The link expires in 30 minutes.
            </p>
          )}

          {(mode === "login" || mode === "register") && (
            <div className="mb-2">
              <label className="font-mono text-[11px] tracking-[0.2em] uppercase text-muted-foreground">Password</label>
              <input
                data-testid="password-input"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full bg-secondary border border-border px-3 py-2.5 outline-none focus:ring-2 focus:ring-accent text-sm font-mono"
                placeholder="••••••••"
              />
            </div>
          )}

          {mode === "login" && (
            <button
              type="button"
              data-testid="forgot-link"
              onClick={() => switchMode("forgot")}
              className="text-xs text-primary hover:underline mb-6 block"
            >
              Forgot password?
            </button>
          )}
          {mode !== "login" && <div className="mb-6" />}

          {info && (
            <div data-testid="auth-info" className="mb-4 border border-primary/40 bg-primary/5 px-3 py-2 text-sm text-primary">
              {info}
            </div>
          )}
          {error && (
            <div data-testid="auth-error" className="mb-4 border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive-foreground">
              {error}
            </div>
          )}

          <button
            data-testid="auth-submit"
            type="submit"
            disabled={loading}
            className="w-full bg-accent text-white font-mono text-sm tracking-[0.15em] uppercase py-3 flex items-center justify-center gap-2 hover:bg-accent/90 transition-colors disabled:opacity-50"
          >
            {loading ? "Working…" : submitLabels[mode]}
            {!loading && <ArrowRight className="h-4 w-4" />}
          </button>

          {mode === "login" && (
            <button type="button" data-testid="auth-toggle" onClick={() => switchMode("register")} className="w-full mt-4 text-sm text-muted-foreground hover:text-foreground transition-colors">
              No account? Register a mechanic
            </button>
          )}
          {mode === "register" && (
            <button type="button" data-testid="auth-toggle" onClick={() => switchMode("login")} className="w-full mt-4 text-sm text-muted-foreground hover:text-foreground transition-colors">
              Already registered? Sign in
            </button>
          )}
          {mode === "forgot" && (
            <button type="button" data-testid="back-to-login" onClick={() => switchMode("login")} className="w-full mt-4 text-sm text-muted-foreground hover:text-foreground transition-colors">
              Back to sign in
            </button>
          )}

          <div className="mt-8 border border-border bg-secondary/40 p-3 flex items-start gap-2">
            <Wrench className="h-4 w-4 text-primary mt-0.5 shrink-0" />
            <p className="font-mono text-[11px] text-muted-foreground leading-relaxed">
              Demo: mechanic@squawkking.io / squawk123
            </p>
          </div>
        </form>
      </div>
    </div>
  );
}
