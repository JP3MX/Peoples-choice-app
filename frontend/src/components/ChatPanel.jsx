import React, { useEffect, useRef, useState } from "react";
import { Send, Plane, AlertTriangle, FileText, History, ShieldCheck, Wrench, Cpu, ChevronDown, Flag } from "lucide-react";
import { api, API, getToken } from "@/lib/api";
import Markdown from "@/components/Markdown";
import { toast } from "sonner";

const STOP_MESSAGE =
  "Approved maintenance data required. Please provide or upload the applicable manual before continuing.";

function CitationRow({ citations }) {
  if (!citations || citations.length === 0) return null;
  return (
    <div className="mt-4 pt-3 border-t border-border" data-testid="message-citations">
      <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-muted-foreground mb-2 flex items-center gap-1.5">
        <ShieldCheck className="h-3 w-3 text-primary" /> Approved Sources Cited
      </p>
      <div className="flex flex-wrap gap-2">
        {citations.map((c, i) => (
          <span
            key={i}
            className={`font-mono text-[11px] px-2 py-1 border ${
              c.status === "superseded"
                ? "border-accent/50 bg-accent/10 text-accent"
                : "border-primary/40 bg-primary/10 text-primary"
            }`}
          >
            {c.doc_name} · ATA {c.ata || "n/a"} · p.{c.page}
            {c.status === "superseded" ? " · HISTORICAL" : ""}
          </span>
        ))}
      </div>
    </div>
  );
}

function CorpusRow({ corpus }) {
  if (!corpus || corpus.length === 0) return null;
  return (
    <div className="mt-3 pt-3 border-t border-border/60">
      <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-muted-foreground mb-2 flex items-center gap-1.5">
        <History className="h-3 w-3 text-accent" /> Matched History (reference only)
      </p>
      <div className="space-y-1">
        {corpus.map((r, i) => (
          <p key={i} className="text-xs text-muted-foreground leading-snug">
            <span className="font-mono text-foreground/70">{r.make} {r.model}</span> · {r.symptom}
          </p>
        ))}
      </div>
    </div>
  );
}

export default function ChatPanel({ session, aircraft, onCitations, onSessionUpdate, onPaywall }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [streamMeta, setStreamMeta] = useState(null);
  const [models, setModels] = useState([]);
  const [modelMenu, setModelMenu] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    api.get("/models").then((r) => setModels(r.data.models || []));
  }, []);

  const currentModel = session?.model || "gpt-5.4";
  const currentLabel = models.find((m) => m.id === currentModel)?.label || currentModel;

  const changeModel = async (id) => {
    setModelMenu(false);
    if (!session || id === currentModel) return;
    const { data } = await api.put(`/sessions/${session.id}`, { model: id, title: session.title });
    onSessionUpdate?.(data);
  };

  useEffect(() => {
    if (!session) return;
    setMessages([]);
    fetch(`${API}/sessions/${session.id}/messages`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then((r) => r.json())
      .then((data) => setMessages(Array.isArray(data) ? data : []));
  }, [session]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, streamText]);

  const send = async () => {
    const text = input.trim();
    if (!text || streaming || !session) return;
    setInput("");
    const tmpId = `tmp-${Date.now()}`;
    setMessages((m) => [...m, { role: "user", content: text, id: tmpId }]);
    setStreaming(true);
    setStreamText("");
    setStreamMeta(null);

    let acc = "";
    let meta = null;
    try {
      const res = await fetch(`${API}/sessions/${session.id}/message`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({ text }),
      });
      if (res.status === 402) {
        let detail = "Upgrade required to continue troubleshooting.";
        try {
          detail = (await res.json()).detail || detail;
        } catch (e) {
          console.error("Failed to parse 402 response body:", e);
        }
        setMessages((m) => m.filter((x) => x.id !== tmpId));
        setStreaming(false);
        setInput(text);
        onPaywall?.(detail);
        return;
      }
      if (!res.ok || !res.body) {
        throw new Error(`Request failed (${res.status})`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop();
        for (const part of parts) {
          const line = part.replace(/^data:\s*/, "").trim();
          if (!line) continue;
          let evt;
          try { evt = JSON.parse(line); } catch { continue; }
          if (evt.type === "meta") {
            meta = evt.meta;
            setStreamMeta(evt.meta);
            onCitations?.(evt.meta.citations || []);
          } else if (evt.type === "delta") {
            acc += evt.content;
            setStreamText(acc);
          } else if (evt.type === "error") {
            acc += `\n\n**Error:** ${evt.content}`;
            setStreamText(acc);
          }
        }
      }
    } catch (e) {
      console.error("Chat stream failed:", e);
      acc += `\n\n**Connection error.** Please retry.`;
      setStreamText(acc);
    }
    setMessages((m) => [
      ...m,
      { role: "assistant", content: acc, citations: meta?.citations, corpus: meta?.corpus, id: `a-${Date.now()}` },
    ]);
    setStreaming(false);
    setStreamText("");
    setStreamMeta(null);
  };

  const reportMessage = async (message) => {
    const reason = window.prompt("Why are you reporting this AI response? Do not include private information.");
    if (!reason?.trim()) return;
    try {
      await api.post("/reports", {
        session_id: session.id,
        message_id: message.id,
        reason: reason.trim(),
        content: message.content,
      });
      toast.success("AI response reported for review");
    } catch {
      toast.error("Report could not be submitted");
    }
  };

  const isConfirmed = aircraft && aircraft.confirmed;

  return (
    <div className="flex flex-col h-full bg-background">
      {/* status strip */}
      <div className="border-b border-border pl-14 pr-12 sm:px-6 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <Wrench className="h-4 w-4 text-accent shrink-0" />
          <div className="min-w-0">
            <p className="font-head font-bold text-sm truncate">{session?.title || "Troubleshooting"}</p>
            <p className="font-mono text-[10px] tracking-widest uppercase text-muted-foreground truncate">
              {aircraft ? `${aircraft.make} ${aircraft.model}` : "No aircraft selected"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {/* model selector */}
          <div className="relative hidden sm:block">
            <button
              data-testid="model-selector"
              onClick={() => setModelMenu(!modelMenu)}
              className="font-mono text-[10px] tracking-widest uppercase px-2 py-1 border border-border bg-secondary/40 flex items-center gap-1.5 hover:border-white/25 transition-colors text-foreground/80"
              title="ChatGPT model powering this session"
            >
              <Cpu className="h-3 w-3 text-primary" />
              {currentLabel}
              <ChevronDown className="h-3 w-3 text-muted-foreground" />
            </button>
            {modelMenu && (
              <div className="absolute right-0 mt-1 z-30 w-56 bg-card border border-border shadow-xl" data-testid="model-menu">
                <p className="font-mono text-[9px] tracking-[0.2em] uppercase text-muted-foreground px-3 py-2 border-b border-border">
                  OpenAI ChatGPT Models
                </p>
                {models.map((m) => (
                  <button
                    key={m.id}
                    data-testid={`model-option-${m.id}`}
                    onClick={() => changeModel(m.id)}
                    className={`w-full text-left px-3 py-2 border-b border-border last:border-0 hover:bg-secondary transition-colors ${
                      m.id === currentModel ? "bg-primary/10" : ""
                    }`}
                  >
                    <span className={`font-mono text-xs ${m.id === currentModel ? "text-primary" : "text-foreground"}`}>{m.label}</span>
                    <span className="block text-[10px] text-muted-foreground">{m.note}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div
            className={`font-mono text-[10px] tracking-widest uppercase px-2 py-1 border flex items-center gap-1.5 ${
              isConfirmed
                ? "border-primary/50 bg-primary/10 text-primary"
                : "border-accent/50 bg-accent/10 text-accent"
            }`}
            data-testid="applicability-status"
          >
            {isConfirmed ? <ShieldCheck className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
            <span className="hidden sm:inline">{isConfirmed ? "Applicability Confirmed" : "Preliminary Only"}</span>
          </div>
        </div>
      </div>

      {/* messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6 space-y-6" data-testid="chat-messages">
        {messages.length === 0 && !streaming && (
          <div className="max-w-lg mx-auto text-center pt-16">
            <div className="h-12 w-12 bg-accent flex items-center justify-center mx-auto mb-5">
              <Plane className="h-7 w-7 text-white" strokeWidth={2.5} />
            </div>
            <h3 className="font-head font-black text-2xl uppercase tracking-tight mb-3">Report a squawk</h3>
            <p className="text-muted-foreground text-sm leading-relaxed mb-6">
              Describe the symptom. I'll lead with the most likely cause, ask up to two clarifying questions, then walk
              sequenced steps. Aircraft-specific steps require a confirmed profile and an approved manual.
            </p>
            <div className="grid gap-2 text-left">
              {[
                "Rough mag drop on runup, right magneto exceeds limits",
                "Low voltage light on in flight, ammeter shows discharge",
                "Hot start difficulty, engine floods when warm",
              ].map((s) => (
                <button
                  key={s}
                  data-testid="sample-prompt"
                  onClick={() => setInput(s)}
                  className="font-mono text-xs text-left border border-border bg-secondary/40 px-3 py-2.5 hover:border-accent/60 hover:bg-secondary transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <div key={m.id} data-testid={`message-${m.role}`}>
            {m.role === "user" ? (
              <div className="flex justify-end">
                <div className="max-w-[80%] bg-secondary border border-border px-4 py-3 text-sm">{m.content}</div>
              </div>
            ) : (
              <div className="border-l-4 border-l-primary bg-card border border-border pl-4 pr-4 py-4">
                {m.content === STOP_MESSAGE ? (
                  <div className="flex items-start gap-3" data-testid="stop-message">
                    <AlertTriangle className="h-5 w-5 text-accent shrink-0 mt-0.5" />
                    <p className="font-mono text-sm text-accent leading-relaxed">{STOP_MESSAGE}</p>
                  </div>
                ) : (
                  <Markdown text={m.content} />
                )}
                <CitationRow citations={m.citations} />
                <CorpusRow corpus={m.corpus} />
                <button
                  type="button"
                  onClick={() => reportMessage(m)}
                  className="mt-3 inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-destructive"
                  aria-label="Report AI response"
                >
                  <Flag className="h-3 w-3" /> Report response
                </button>
              </div>
            )}
          </div>
        ))}

        {streaming && (
          <div className="border-l-4 border-l-primary bg-card border border-border pl-4 pr-4 py-4" data-testid="streaming-message">
            {streamText ? (
              <Markdown text={streamText} />
            ) : (
              <p className="font-mono text-xs tracking-widest uppercase text-muted-foreground animate-pulse">
                Cross-referencing manuals & history…
              </p>
            )}
            {streamText && <span className="cursor-blink text-primary">▋</span>}
            {streamMeta && <CitationRow citations={streamMeta.citations} />}
          </div>
        )}
      </div>

      {/* composer */}
      <div className="border-t border-border p-4 shrink-0">
        <div className="flex items-end gap-2 border border-border bg-secondary/40 focus-within:ring-2 focus-within:ring-accent">
          <textarea
            data-testid="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            rows={1}
            placeholder="Describe the symptom…"
            disabled={!session}
            className="flex-1 bg-transparent px-4 py-3 outline-none text-sm resize-none max-h-40"
          />
          <button
            data-testid="chat-send"
            onClick={send}
            disabled={streaming || !input.trim() || !session}
            className="m-1.5 h-9 w-9 bg-accent text-white flex items-center justify-center hover:bg-accent/90 transition-colors disabled:opacity-40 shrink-0"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
        <p className="font-mono text-[10px] text-muted-foreground/60 mt-2 flex items-center gap-1.5">
          <FileText className="h-3 w-3" /> Final guidance cites approved manuals + ATA chapter-section-subject.
        </p>
      </div>
    </div>
  );
}
