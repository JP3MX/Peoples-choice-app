import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plane, ArrowRight } from "lucide-react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Capacitor } from "@capacitor/core";

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

  const loginWithGoogle = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setInfo("");
    setLoading(true);
    try {
      if (mode === "login" || mode === "register") {
        const path = mode === "login" ? "/auth/login" : "/auth/register";
        const body =
          mode === "login"
            ? { email, password }
            : { email, password, name, origin_url: window.location.origin };
        const { data } = await api.post(path, body);
        login(data.user);
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

          {(mode === "login" || mode === "register") && !Capacitor.isNativePlatform() && (
            <>
              <div className="flex items-center gap-3 my-5">
                <div className="h-px bg-border flex-1" />
                <span className="font-mono text-[10px] tracking-[0.2em] uppercase text-muted-foreground">or</span>
                <div className="h-px bg-border flex-1" />
              </div>
              <button
                type="button"
                data-testid="google-signin"
                onClick={loginWithGoogle}
                className="w-full border border-border bg-secondary/40 text-foreground font-mono text-sm tracking-[0.1em] uppercase py-3 flex items-center justify-center gap-3 hover:border-white/25 hover:bg-secondary transition-colors"
              >
                <svg className="h-4 w-4" viewBox="0 0 48 48" aria-hidden="true">
                  <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.9 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.4 6.1 29.5 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.3-.4-3.5z"/>
                  <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 16 19 13 24 13c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.4 6.1 29.5 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/>
                  <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35 26.7 36 24 36c-5.3 0-9.7-3.1-11.3-7.5l-6.5 5C9.6 39.6 16.2 44 24 44z"/>
                  <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.1-4.1 5.6l6.2 5.2C40.9 35.7 44 30.3 44 24c0-1.3-.1-2.3-.4-3.5z"/>
                </svg>
                Continue with Google
              </button>
            </>
          )}

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

          <div className="mt-8 flex justify-center gap-4 text-xs">
            <a href="/privacy" className="text-muted-foreground hover:text-primary">Privacy</a>
            <a href="/account-deletion" className="text-muted-foreground hover:text-primary">Delete account</a>
          </div>
        </form>
      </div>
    </div>
  );
}
