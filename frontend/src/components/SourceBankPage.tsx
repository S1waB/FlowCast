import React, { useEffect, useState, useRef } from "react";
import {
  fetchSourceBank,
  updateSourceBankConfig,
  uploadAsset,
  SourceBankResponse,
  AssetMetadata,
  SourceBankDefaults,
} from "../api/sourceBank";

const getUrl = (path: string) => import.meta.env.DEV ? `/api${path}` : `${(import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "")}${path}`;


const ROLES = [
  { id: "intro", title: "Intro", desc: "Jingle d'ouverture" },
  { id: "outro", title: "Outro", desc: "Jingle de fin" },
  { id: "fond", title: "Fond musical", desc: "Musique de fond (loop/duck)" },
  { id: "transition", title: "Transition", desc: "Virgule inter-clips" },
];

export default function SourceBankPage() {
  const [data, setData] = useState<SourceBankResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);

  const showToast = (msg: string, type: "success" | "error" = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const loadData = async () => {
    try {
      const res = await fetchSourceBank();
      setData(res);
      setError(null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleUpload = async (role: string, file: File) => {
    try {
      await uploadAsset(role, file);
      showToast(`${role} mis à jour avec succès!`);
      loadData();
    } catch (err: any) {
      showToast(`Erreur d'upload: ${err.message}`, "error");
    }
  };

  if (loading) return <div className="p-8 text-center text-muted">Chargement de la banque source...</div>;
  if (error) return <div className="p-8 text-center text-error">Erreur: {error}</div>;
  if (!data) return null;

  return (
    <div className="max-w-6xl mx-auto p-4 space-y-8 animate-fadeSlideDown">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-transparent bg-clip-text bg-gradient-to-br from-white to-accent">Banque Source</h1>
        <p className="text-muted mt-2">Gérez les assets audio (intro, outro, fond, transition) et les paramètres de mixage.</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {ROLES.map((roleInfo) => (
          <AssetCard
            key={roleInfo.id}
            title={roleInfo.title}
            desc={roleInfo.desc}
            meta={data.roles[roleInfo.id]}
            onUpload={(file) => handleUpload(roleInfo.id, file)}
          />
        ))}
      </div>

      <ConfigPanel defaults={data.defaults} onSaved={() => {
        showToast("Paramètres sauvegardés!");
        loadData();
      }} />

      {toast && (
        <div className={`fixed bottom-4 right-4 px-6 py-3 rounded-md shadow-lg font-medium animate-fadeSlideUp z-50 ${
          toast.type === "success" ? "bg-ok/20 text-ok border border-ok/30" : "bg-error/20 text-error border border-error/30"
        }`}>
          {toast.msg}
        </div>
      )}
    </div>
  );
}

// ── ASSET CARD ─────────────────────────────────────────────────────────────

function AssetCard({ title, desc, meta, onUpload }: { title: string, desc: string, meta?: AssetMetadata, onUpload: (file: File) => void }) {
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") setDragActive(true);
    else if (e.type === "dragleave") setDragActive(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      onUpload(e.dataTransfer.files[0]);
    }
  };

  return (
    <div 
      className={`fc-card relative overflow-hidden transition-colors ${dragActive ? 'border-accent bg-accent/5' : ''}`}
      onDragEnter={handleDrag} onDragLeave={handleDrag} onDragOver={handleDrag} onDrop={handleDrop}
    >
      <div className="flex justify-between items-start mb-4">
        <div>
          <h2 className="text-lg font-semibold text-text">{title}</h2>
          <p className="text-sm text-muted">{desc}</p>
        </div>
        {meta?.exists ? (
          <span className="fc-badge fc-badge--ok text-xs">Existant</span>
        ) : (
          <span className="fc-badge fc-badge--error text-xs">Manquant</span>
        )}
      </div>

      {meta?.exists && (
        <div className="space-y-4">
          <audio controls src={getUrl(`/${meta.path}`)} className="w-full h-10 outline-none rounded-md" />
          <div className="flex justify-between text-xs text-muted bg-surface2 p-2 rounded-md border border-border">
            <span>Durée: {meta.duration_s}s</span>
            <span>Taille: {(meta.size_bytes! / 1024 / 1024).toFixed(2)} MB</span>
          </div>
          {meta.duration_warning && (
            <div className="text-xs text-error bg-error/10 p-2 rounded border border-error/20">
              ⚠️ {meta.duration_warning}
            </div>
          )}
        </div>
      )}

      <div className="mt-4 pt-4 border-t border-border flex justify-between items-center">
        <span className="text-xs text-muted">{dragActive ? "Lâchez le fichier ici" : "Glissez un .mp3 / .wav ici"}</span>
        <button 
          onClick={() => inputRef.current?.click()}
          className="px-3 py-1.5 text-sm bg-accent/20 text-accent hover:bg-accent hover:text-white transition-colors rounded-md font-medium"
        >
          {meta?.exists ? "Remplacer" : "Uploader"}
        </button>
        <input ref={inputRef} type="file" accept=".mp3,.wav" className="hidden" onChange={(e) => {
          if (e.target.files?.[0]) onUpload(e.target.files[0]);
        }} />
      </div>
      
      {dragActive && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-bg/80 backdrop-blur-sm border-2 border-dashed border-accent rounded-lg pointer-events-none">
          <span className="text-accent font-bold text-lg">Déposer le fichier audio</span>
        </div>
      )}
    </div>
  );
}

// ── CONFIG PANEL ───────────────────────────────────────────────────────────

function ConfigPanel({ defaults, onSaved }: { defaults: SourceBankDefaults, onSaved: () => void }) {
  const [form, setForm] = useState({
    duck_db: defaults.duck_db,
    transition_max_ms: defaults.transition_max_ms,
    fade_in_ms: defaults.transition_fade_in_ms,
    fade_out_ms: defaults.transition_fade_out_ms,
    silence_thresh_db: defaults.silence_thresh_db_relative,
    min_silence_len_ms: defaults.min_silence_len_ms,
    min_gap_safety_ms: defaults.min_gap_safety_ms,
  });

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setForm(prev => ({ ...prev, [name]: parseFloat(value) }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await updateSourceBankConfig(form);
      onSaved();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="fc-card max-w-none">
      <div className="flex justify-between items-center mb-6 border-b border-border pb-4">
        <div>
          <h2 className="text-xl font-bold text-text">Paramètres de mixage par défaut</h2>
          <p className="text-sm text-muted">Ces valeurs s'appliquent aux futurs bulletins générés.</p>
        </div>
        <button type="submit" disabled={saving} className="px-4 py-2 bg-accent hover:bg-accent/80 text-white font-medium rounded-md transition-colors disabled:opacity-50">
          {saving ? "Sauvegarde..." : "Sauvegarder"}
        </button>
      </div>

      {error && <div className="mb-4 text-sm text-error bg-error/10 p-3 rounded border border-error/20">{error}</div>}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <ConfigField label="Ducking Fond (dB)" name="duck_db" value={form.duck_db} onChange={handleChange} min={-60} max={0} step={1} hint="Niveau du fond musical (-16 recommandé)" />
        
        <div className="space-y-1">
          <label className="text-sm font-medium text-text block">Durée Transition Max (ms)</label>
          <input 
            type="number" name="transition_max_ms" value={form.transition_max_ms} onChange={handleChange} min={500} max={30000} step={100}
            className="w-full bg-surface2 border border-border rounded-md px-3 py-2 text-text text-sm focus:border-accent focus:ring-1 focus:ring-accent outline-none"
          />
          {form.transition_max_ms > 5000 && (
            <p className="text-xs text-error mt-1">⚠️ Plus de 5000ms peut causer des chevauchements indésirables.</p>
          )}
        </div>

        <ConfigField label="Fade In Transition (ms)" name="fade_in_ms" value={form.fade_in_ms} onChange={handleChange} min={0} max={5000} step={100} hint="Durée du fondu entrant" />
        <ConfigField label="Fade Out Transition (ms)" name="fade_out_ms" value={form.fade_out_ms} onChange={handleChange} min={0} max={5000} step={100} hint="Durée du fondu sortant" />
        
        <ConfigField label="Seuil Silence (dB relatif)" name="silence_thresh_db" value={form.silence_thresh_db} onChange={handleChange} min={-60} max={-1} step={1} hint="Relatif au volume moyen vocal (-16)" />
        <ConfigField label="Durée Silence Min (ms)" name="min_silence_len_ms" value={form.min_silence_len_ms} onChange={handleChange} min={50} max={10000} step={50} hint="Temps min pour détecter une pause (400)" />
        <ConfigField label="Marge Sécurité (ms)" name="min_gap_safety_ms" value={form.min_gap_safety_ms} onChange={handleChange} min={0} max={1000} step={10} hint="Marge de sécurité avant/après la voix (100)" />
      </div>
    </form>
  );
}

function ConfigField({ label, name, value, onChange, min, max, step, hint }: any) {
  return (
    <div className="space-y-1">
      <label className="text-sm font-medium text-text block">{label}</label>
      <input 
        type="number" name={name} value={value} onChange={onChange} min={min} max={max} step={step}
        className="w-full bg-surface2 border border-border rounded-md px-3 py-2 text-text text-sm focus:border-accent focus:ring-1 focus:ring-accent outline-none"
      />
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  );
}
