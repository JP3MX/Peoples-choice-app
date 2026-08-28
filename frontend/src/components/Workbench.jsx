import React, { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import {
  Plane, Upload, FileText, History, BookOpen, Trash2, CheckCircle2,
  Circle, ExternalLink, Plus, ClipboardList, Image as ImageIcon, Camera, File as FileIcon,
} from "lucide-react";
import { api, API, getToken } from "@/lib/api";

const TABS = [
  { id: "aircraft", label: "Aircraft", icon: Plane },
  { id: "manuals", label: "Manuals", icon: FileText },
  { id: "media", label: "Media", icon: Camera },
  { id: "history", label: "History", icon: History },
  { id: "logbook", label: "Logbook", icon: BookOpen },
];

const DOC_TYPES = ["AMM", "Service Manual", "ICA", "Wiring Diagram", "TCDS", "AD", "Mfr Troubleshooting"];

async function openAuthenticatedFile(path) {
  const response = await fetch(`${API}${path}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!response.ok) throw new Error("Download failed");
  const url = URL.createObjectURL(await response.blob());
  window.open(url, "_blank", "noopener,noreferrer");
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

function Field({ label, value, onChange, placeholder, mono = true, testid }) {
  return (
    <div>
      <label className="font-mono text-[10px] tracking-[0.2em] uppercase text-muted-foreground">{label}</label>
      <input
        data-testid={testid}
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={`mt-1 w-full bg-secondary border border-border px-3 py-2 outline-none focus:ring-2 focus:ring-accent text-sm ${mono ? "font-mono" : ""}`}
      />
    </div>
  );
}

function AircraftTab({ aircraft, onSaved }) {
  const [form, setForm] = useState(aircraft || {});
  useEffect(() => setForm(aircraft || {}), [aircraft]);
  if (!aircraft) return <Empty text="Select or create an aircraft from the left rail." />;

  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));
  const required = ["make", "model", "year", "serial_number", "configuration"];
  const allFilled = required.every((k) => (form[k] || "").trim());

  const save = async (confirm) => {
    const payload = { ...form, confirmed: confirm ? true : form.confirmed };
    if (confirm && !allFilled) {
      toast.error("Fill make, model, year, serial number and configuration before confirming.");
      return;
    }
    const { data } = await api.put(`/aircraft/${aircraft.id}`, payload);
    onSaved(data);
    toast.success(confirm ? "Applicability confirmed" : "Aircraft saved");
  };

  return (
    <div className="p-5 space-y-4" data-testid="aircraft-tab">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Tail #" value={form.tail_number} onChange={set("tail_number")} placeholder="N172SK" testid="ac-tail" />
        <Field label="Year Mfr" value={form.year} onChange={set("year")} placeholder="1978" testid="ac-year" />
        <Field label="Make" value={form.make} onChange={set("make")} placeholder="Cessna" testid="ac-make" />
        <Field label="Model" value={form.model} onChange={set("model")} placeholder="172N" testid="ac-model" />
      </div>
      <Field label="Serial Number" value={form.serial_number} onChange={set("serial_number")} placeholder="17271000" testid="ac-serial" />
      <div>
        <label className="font-mono text-[10px] tracking-[0.2em] uppercase text-muted-foreground">Configuration</label>
        <textarea
          data-testid="ac-config"
          value={form.configuration || ""}
          onChange={(e) => set("configuration")(e.target.value)}
          rows={2}
          placeholder="Lycoming O-320-H2AD, fixed gear, 4-seat trainer"
          className="mt-1 w-full bg-secondary border border-border px-3 py-2 outline-none focus:ring-2 focus:ring-accent text-sm"
        />
      </div>

      <div className={`flex items-center gap-2 border px-3 py-2 ${form.confirmed ? "border-primary/50 bg-primary/10" : "border-accent/50 bg-accent/10"}`}>
        {form.confirmed ? <CheckCircle2 className="h-4 w-4 text-primary" /> : <Circle className="h-4 w-4 text-accent" />}
        <span className={`font-mono text-[11px] tracking-widest uppercase ${form.confirmed ? "text-primary" : "text-accent"}`}>
          {form.confirmed ? "Applicability Confirmed" : "Not Confirmed — Preliminary Only"}
        </span>
      </div>

      <div className="flex gap-2">
        <button data-testid="ac-save" onClick={() => save(false)} className="flex-1 border border-border py-2.5 font-mono text-xs tracking-widest uppercase hover:bg-secondary transition-colors">
          Save
        </button>
        <button data-testid="ac-confirm" onClick={() => save(true)} className="flex-1 bg-primary text-white py-2.5 font-mono text-xs tracking-widest uppercase hover:bg-primary/90 transition-colors">
          Confirm Applicability
        </button>
      </div>
    </div>
  );
}

function ManualsTab({ aircraft }) {
  const [manuals, setManuals] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [meta, setMeta] = useState({ doc_type: "AMM", ata: "", status: "current" });

  const load = useCallback(() => {
    const q = aircraft ? `?aircraft_id=${aircraft.id}` : "";
    api.get(`/manuals${q}`).then((r) => setManuals(r.data));
  }, [aircraft]);
  useEffect(() => { load(); }, [load]);

  const upload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!aircraft) { toast.error("Select an aircraft first."); return; }
    setUploading(true);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("aircraft_id", aircraft.id);
    fd.append("doc_name", file.name);
    fd.append("doc_type", meta.doc_type);
    fd.append("ata", meta.ata);
    fd.append("status", meta.status);
    try {
      const res = await api.post("/manuals", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(`Uploaded · ${res.data.page_count} pages extracted`);
      load();
    } catch (err) {
      toast.error("Upload failed");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const del = async (id) => { await api.delete(`/manuals/${id}`); load(); };
  const open = (id) => openAuthenticatedFile(`/manuals/${id}/download`).catch(() => toast.error("Download failed"));

  return (
    <div className="p-5 space-y-4" data-testid="manuals-tab">
      {!aircraft && <Empty text="Select an aircraft to attach approved manuals." />}
      {aircraft && (
        <>
          <div className="border border-border bg-secondary/40 p-3 space-y-3">
            <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-muted-foreground">Upload Approved Source (PDF)</p>
            <div className="grid grid-cols-2 gap-2">
              <select data-testid="manual-type" value={meta.doc_type} onChange={(e) => setMeta({ ...meta, doc_type: e.target.value })} className="bg-secondary border border-border px-2 py-2 text-xs font-mono outline-none focus:ring-2 focus:ring-accent">
                {DOC_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <select data-testid="manual-status" value={meta.status} onChange={(e) => setMeta({ ...meta, status: e.target.value })} className="bg-secondary border border-border px-2 py-2 text-xs font-mono outline-none focus:ring-2 focus:ring-accent">
                <option value="current">Current (controlling)</option>
                <option value="superseded">Superseded (historical)</option>
              </select>
            </div>
            <input data-testid="manual-ata" value={meta.ata} onChange={(e) => setMeta({ ...meta, ata: e.target.value })} placeholder="ATA e.g. 74-00-00" className="w-full bg-secondary border border-border px-2 py-2 text-xs font-mono outline-none focus:ring-2 focus:ring-accent" />
            <label className="flex items-center justify-center gap-2 bg-primary text-white py-2.5 font-mono text-xs tracking-widest uppercase cursor-pointer hover:bg-primary/90 transition-colors">
              <Upload className="h-4 w-4" /> {uploading ? "Extracting…" : "Choose PDF"}
              <input data-testid="manual-file" type="file" accept="application/pdf,.pdf" onChange={upload} className="hidden" disabled={uploading} />
            </label>
          </div>

          <div className="space-y-2" data-testid="manuals-list">
            {manuals.length === 0 && <Empty text="No approved manuals uploaded yet." />}
            {manuals.map((m) => (
              <div key={m.id} className="border border-border p-3 hover:border-white/20 transition-colors">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{m.doc_name}</p>
                    <p className="font-mono text-[11px] text-muted-foreground mt-0.5">
                      {m.doc_type} · ATA {m.ata || "n/a"} · {m.page_count} pgs
                    </p>
                  </div>
                  <span className={`font-mono text-[9px] tracking-widest uppercase px-1.5 py-0.5 border shrink-0 ${m.status === "superseded" ? "border-accent/50 text-accent" : "border-primary/50 text-primary"}`}>
                    {m.status === "superseded" ? "Historical" : "Current"}
                  </span>
                </div>
                <div className="flex gap-3 mt-2">
                  <button onClick={() => open(m.id)} className="font-mono text-[11px] text-primary flex items-center gap-1 hover:underline">
                    <ExternalLink className="h-3 w-3" /> View
                  </button>
                  <button data-testid={`manual-delete-${m.id}`} onClick={() => del(m.id)} className="font-mono text-[11px] text-muted-foreground flex items-center gap-1 hover:text-destructive">
                    <Trash2 className="h-3 w-3" /> Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function HistoryTab() {
  const [records, setRecords] = useState([]);
  const [q, setQ] = useState("");
  useEffect(() => {
    api.get(`/corpus${q ? `?q=${encodeURIComponent(q)}` : ""}`).then((r) => setRecords(r.data));
  }, [q]);
  return (
    <div className="p-5 space-y-3" data-testid="history-tab">
      <input data-testid="history-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search symptoms, systems, ATA…" className="w-full bg-secondary border border-border px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent" />
      <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-muted-foreground">
        {records.length} reference cases · matching aid only, not maintenance authority
      </p>
      <div className="space-y-2">
        {records.map((r, i) => (
          <div key={i} className="border border-border p-3">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="font-mono text-[11px] text-foreground/80">{r.make} {r.model}</span>
              <span className="font-mono text-[10px] text-primary border border-primary/40 px-1.5">ATA {r.ata}</span>
            </div>
            <p className="text-sm mb-1">{r.symptom}</p>
            <p className="text-xs text-muted-foreground"><span className="text-accent font-mono">Likely:</span> {r.likely_cause}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function LogbookTab({ aircraft }) {
  const [entries, setEntries] = useState([]);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ date: new Date().toISOString().slice(0, 10), ata: "", description: "", action_taken: "", hours: "", mechanic: "" });

  const load = useCallback(() => {
    const q = aircraft ? `?aircraft_id=${aircraft.id}` : "";
    api.get(`/logbook${q}`).then((r) => setEntries(r.data));
  }, [aircraft]);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!form.description.trim()) { toast.error("Description required"); return; }
    await api.post("/logbook", { ...form, aircraft_id: aircraft?.id || null });
    setForm({ date: new Date().toISOString().slice(0, 10), ata: "", description: "", action_taken: "", hours: "", mechanic: "" });
    setAdding(false);
    load();
    toast.success("Logbook entry recorded");
  };
  const del = async (id) => { await api.delete(`/logbook/${id}`); load(); };

  return (
    <div className="p-5 space-y-3" data-testid="logbook-tab">
      <button data-testid="logbook-add-toggle" onClick={() => setAdding(!adding)} className="w-full border border-border py-2.5 font-mono text-xs tracking-widest uppercase hover:bg-secondary transition-colors flex items-center justify-center gap-2">
        <Plus className="h-4 w-4" /> {adding ? "Cancel" : "New Entry"}
      </button>
      {adding && (
        <div className="border border-border bg-secondary/40 p-3 space-y-2" data-testid="logbook-form">
          <div className="grid grid-cols-2 gap-2">
            <input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} className="bg-secondary border border-border px-2 py-2 text-xs font-mono outline-none focus:ring-2 focus:ring-accent" />
            <input value={form.ata} onChange={(e) => setForm({ ...form, ata: e.target.value })} placeholder="ATA" className="bg-secondary border border-border px-2 py-2 text-xs font-mono outline-none focus:ring-2 focus:ring-accent" />
          </div>
          <textarea data-testid="logbook-desc" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Discrepancy / squawk" rows={2} className="w-full bg-secondary border border-border px-2 py-2 text-sm outline-none focus:ring-2 focus:ring-accent" />
          <textarea value={form.action_taken} onChange={(e) => setForm({ ...form, action_taken: e.target.value })} placeholder="Corrective action taken" rows={2} className="w-full bg-secondary border border-border px-2 py-2 text-sm outline-none focus:ring-2 focus:ring-accent" />
          <div className="grid grid-cols-2 gap-2">
            <input value={form.hours} onChange={(e) => setForm({ ...form, hours: e.target.value })} placeholder="Tach/Hobbs" className="bg-secondary border border-border px-2 py-2 text-xs font-mono outline-none focus:ring-2 focus:ring-accent" />
            <input value={form.mechanic} onChange={(e) => setForm({ ...form, mechanic: e.target.value })} placeholder="Mechanic / cert #" className="bg-secondary border border-border px-2 py-2 text-xs font-mono outline-none focus:ring-2 focus:ring-accent" />
          </div>
          <button data-testid="logbook-save" onClick={save} className="w-full bg-primary text-white py-2 font-mono text-xs tracking-widest uppercase hover:bg-primary/90 transition-colors">Record Entry</button>
        </div>
      )}
      <div className="space-y-2" data-testid="logbook-list">
        {entries.length === 0 && <Empty text="No logbook entries yet." />}
        {entries.map((e) => (
          <div key={e.id} className="border border-border p-3">
            <div className="flex items-center justify-between mb-1">
              <span className="font-mono text-[11px] text-muted-foreground">{e.date} {e.ata && `· ATA ${e.ata}`}</span>
              <button onClick={() => del(e.id)} className="text-muted-foreground hover:text-destructive"><Trash2 className="h-3.5 w-3.5" /></button>
            </div>
            <p className="text-sm">{e.description}</p>
            {e.action_taken && <p className="text-xs text-muted-foreground mt-1"><span className="text-primary font-mono">Action:</span> {e.action_taken}</p>}
            {(e.hours || e.mechanic) && <p className="font-mono text-[10px] text-muted-foreground/70 mt-1">{e.hours} {e.mechanic && `· ${e.mechanic}`}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}

function MediaThumb({ item }) {
  const [url, setUrl] = useState(null);
  useEffect(() => {
    let revoke;
    if (item.kind === "image") {
      fetch(`${API}/media/${item.id}/download`, { headers: { Authorization: `Bearer ${getToken()}` } })
        .then((r) => {
          if (!r.ok) throw new Error("download failed");
          return r.blob();
        })
        .then((b) => {
          revoke = URL.createObjectURL(b);
          setUrl(revoke);
        })
        .catch(() => setUrl("error"));
    }
    return () => revoke && URL.revokeObjectURL(revoke);
  }, [item.id, item.kind]);

  if (item.kind === "image" && url === "error")
    return (
      <div className="w-full h-28 bg-secondary flex items-center justify-center">
        <ImageIcon className="h-8 w-8 text-destructive/60" />
      </div>
    );
  if (item.kind === "image" && url)
    return <img src={url} alt={item.caption || item.original_filename} className="w-full h-28 object-cover" />;
  if (item.kind === "image")
    return <div className="w-full h-28 bg-secondary animate-pulse" />;
  return (
    <div className="w-full h-28 bg-secondary flex items-center justify-center">
      <FileIcon className="h-8 w-8 text-muted-foreground" />
    </div>
  );
}

function MediaTab({ aircraft }) {
  const [items, setItems] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [caption, setCaption] = useState("");

  const load = useCallback(() => {
    const q = aircraft ? `?aircraft_id=${aircraft.id}` : "";
    api.get(`/media${q}`).then((r) => setItems(r.data));
  }, [aircraft]);
  useEffect(() => { load(); }, [load]);

  const upload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!aircraft) { toast.error("Select an aircraft first."); return; }
    setUploading(true);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("aircraft_id", aircraft.id);
    fd.append("caption", caption);
    try {
      await api.post("/media", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Uploaded to storage");
      setCaption("");
      load();
    } catch {
      toast.error("Upload failed");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const del = async (id) => { await api.delete(`/media/${id}`); load(); };
  const open = (id) => openAuthenticatedFile(`/media/${id}/download`).catch(() => toast.error("Download failed"));

  return (
    <div className="p-5 space-y-4" data-testid="media-tab">
      {!aircraft && <Empty text="Select an aircraft to attach photos & files." />}
      {aircraft && (
        <>
          <div className="border border-border bg-secondary/40 p-3 space-y-3">
            <p className="font-mono text-[10px] tracking-[0.2em] uppercase text-muted-foreground">Attach Photo / File</p>
            <input
              data-testid="media-caption"
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              placeholder="Caption (e.g. corroded ground strap, fwd bulkhead)"
              className="w-full bg-secondary border border-border px-2 py-2 text-xs outline-none focus:ring-2 focus:ring-accent"
            />
            <label className="flex items-center justify-center gap-2 bg-primary text-white py-2.5 font-mono text-xs tracking-widest uppercase cursor-pointer hover:bg-primary/90 transition-colors">
              <Upload className="h-4 w-4" /> {uploading ? "Uploading…" : "Choose File"}
              <input
                data-testid="media-file"
                type="file"
                accept="image/*,application/pdf,.txt,.csv,.doc,.docx"
                onChange={upload}
                className="hidden"
                disabled={uploading}
              />
            </label>
          </div>

          {items.length === 0 && <Empty text="No photos or files attached yet." />}
          <div className="grid grid-cols-2 gap-2" data-testid="media-grid">
            {items.map((m) => (
              <div key={m.id} className="border border-border group relative">
                <button onClick={() => open(m.id)} className="block w-full" title="Open">
                  <MediaThumb item={m} />
                </button>
                <div className="p-2">
                  <p className="text-[11px] truncate">{m.caption || m.original_filename}</p>
                  <p className="font-mono text-[9px] text-muted-foreground uppercase mt-0.5 flex items-center gap-1">
                    {m.kind === "image" ? <ImageIcon className="h-3 w-3" /> : <FileIcon className="h-3 w-3" />}
                    {(m.size / 1024).toFixed(0)} KB
                  </p>
                </div>
                <button
                  data-testid={`media-delete-${m.id}`}
                  onClick={() => del(m.id)}
                  className="absolute top-1 right-1 h-6 w-6 bg-background/80 border border-border flex items-center justify-center text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-destructive transition-opacity"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function Empty({ text }) {
  return (
    <div className="text-center py-10 text-muted-foreground">
      <ClipboardList className="h-8 w-8 mx-auto mb-2 opacity-40" />
      <p className="text-sm">{text}</p>
    </div>
  );
}

export default function Workbench({ aircraft, onAircraftSaved }) {
  const [tab, setTab] = useState("aircraft");
  return (
    <div className="flex flex-col h-full bg-card border-l border-border">
      <div className="flex border-b border-border shrink-0">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              data-testid={`wb-tab-${t.id}`}
              onClick={() => setTab(t.id)}
              className={`flex-1 flex flex-col items-center gap-1 py-3 font-mono text-[10px] tracking-widest uppercase transition-colors ${
                tab === t.id ? "text-accent border-b-2 border-accent bg-accent/5" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Icon className="h-4 w-4" />
              {t.label}
            </button>
          );
        })}
      </div>
      <div className="flex-1 overflow-y-auto">
        {tab === "aircraft" && <AircraftTab aircraft={aircraft} onSaved={onAircraftSaved} />}
        {tab === "manuals" && <ManualsTab aircraft={aircraft} />}
        {tab === "media" && <MediaTab aircraft={aircraft} />}
        {tab === "history" && <HistoryTab />}
        {tab === "logbook" && <LogbookTab aircraft={aircraft} />}
      </div>
    </div>
  );
}
