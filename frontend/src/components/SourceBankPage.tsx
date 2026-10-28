import React, { useEffect, useState, useRef } from "react";
import {
  fetchSourceBank,
  updateSourceBankConfig,
  uploadAsset,
  SourceBankResponse,
  AssetMetadata,
  SourceBankDefaults,
} from "../api/sourceBank";
import {
  fetchProjects,
  createProject,
  activateProject,
  updateProject,
  deleteProject,
  ProjectModel,
  ProjectListResponse,
} from "../api/projects";

const getUrl = (path: string) =>
  import.meta.env.DEV
    ? `/api${path}`
    : `${(import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "")}${path}`;

const ROLES = [
  { id: "intro", title: "Intro", desc: "Jingle d'ouverture" },
  { id: "outro", title: "Outro", desc: "Jingle de fin" },
  { id: "fond", title: "Fond musical", desc: "Musique de fond (sert aussi aux transitions)" },
];

export default function SourceBankPage() {
  const [data, setData] = useState<SourceBankResponse | null>(null);
  const [projectsData, setProjectsData] = useState<ProjectListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);

  const showToast = (msg: string, type: "success" | "error" = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const loadData = async () => {
    try {
      const [bankRes, projRes] = await Promise.all([
        fetchSourceBank(),
        fetchProjects(),
      ]);
      setData(bankRes);
      setProjectsData(projRes);
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

  const handleProjectActivated = async (projectId: string) => {
    try {
      await activateProject(projectId);
      showToast("Projet chargé avec succès !");
      loadData();
    } catch (err: any) {
      showToast(`Erreur: ${err.message}`, "error");
    }
  };

  const handleProjectCreated = async (name: string, description: string, copyBank: boolean) => {
    try {
      const newProj = await createProject({
        name,
        description,
        copy_current_bank: copyBank,
      });
      showToast(`Projet "${newProj.name}" créé et activé !`);
      loadData();
    } catch (err: any) {
      showToast(`Erreur: ${err.message}`, "error");
    }
  };

  const handleSaveToProject = async (projectId: string) => {
    try {
      await updateProject(projectId, { save_current_bank: true });
      showToast("Modifications enregistrées dans le projet !");
      loadData();
    } catch (err: any) {
      showToast(`Erreur: ${err.message}`, "error");
    }
  };

  const handleDeleteProject = async (projectId: string) => {
    try {
      await deleteProject(projectId);
      showToast("Projet supprimé.");
      loadData();
    } catch (err: any) {
      showToast(`Erreur: ${err.message}`, "error");
    }
  };

  if (loading)
    return <div className="p-8 text-center text-muted">Chargement de la banque source...</div>;
  if (error) return <div className="p-8 text-center text-error">Erreur: {error}</div>;
  if (!data) return null;

  const activeProject =
    projectsData?.projects.find((p) => p.id === projectsData.active_project_id) ||
    projectsData?.projects[0];

  return (
    <div className="max-w-6xl mx-auto p-4 space-y-8 animate-fadeSlideDown">
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border pb-6">
        <div>
          <h1 className="text-3xl font-bold text-transparent bg-clip-text bg-gradient-to-br from-white to-accent">
            Banque Source & Projets
          </h1>
          <p className="text-muted mt-1">
            Gérez vos préréglages de mixage et vos bibliothèques d'assets audio sous forme de projets réutilisables.
          </p>
        </div>
      </header>

      {/* Projects Manager Bar */}
      {projectsData && (
        <ProjectManagerBar
          projectsData={projectsData}
          activeProject={activeProject}
          onActivate={handleProjectActivated}
          onCreate={handleProjectCreated}
          onSaveCurrent={handleSaveToProject}
          onDelete={handleDeleteProject}
        />
      )}

      {/* Assets Grid */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-text flex items-center gap-2">
            <span>🎵</span> Assets audio du projet actif
          </h2>
          {activeProject && (
            <span className="text-xs text-muted">
              Appliqués au projet : <strong className="text-text">{activeProject.name}</strong>
            </span>
          )}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
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
      </div>

      {/* Configuration Sliders & Audio Engine Settings */}
      <ConfigPanel
        defaults={data.defaults}
        activeProject={activeProject}
        onSaved={() => {
          showToast("Paramètres sauvegardés!");
          loadData();
        }}
      />

      {/* Toast Notification */}
      {toast && (
        <div
          className={`fixed bottom-4 right-4 px-6 py-3 rounded-md shadow-lg font-medium animate-fadeSlideUp z-50 ${
            toast.type === "success"
              ? "bg-ok/20 text-ok border border-ok/30"
              : "bg-error/20 text-error border border-error/30"
          }`}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}

// ── PROJECT MANAGER BAR ────────────────────────────────────────────────────

function ProjectManagerBar({
  projectsData,
  activeProject,
  onActivate,
  onCreate,
  onSaveCurrent,
  onDelete,
}: {
  projectsData: ProjectListResponse;
  activeProject?: ProjectModel;
  onActivate: (id: string) => void;
  onCreate: (name: string, description: string, copyBank: boolean) => void;
  onSaveCurrent: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newProjName, setNewProjName] = useState("");
  const [newProjDesc, setNewProjDesc] = useState("");
  const [copyCurrentBank, setCopyCurrentBank] = useState(true);

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjName.trim()) return;
    onCreate(newProjName.trim(), newProjDesc.trim(), copyCurrentBank);
    setNewProjName("");
    setNewProjDesc("");
    setShowCreateModal(false);
  };

  return (
    <div className="fc-card bg-surface2/60 border border-accent/20 rounded-xl p-5 shadow-sm space-y-4">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        {/* Active Project Info */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-accent/20 text-accent flex items-center justify-center text-xl">
            📁
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-accent/20 text-accent uppercase tracking-wider">
                Projet Actif
              </span>
              <h2 className="text-lg font-bold text-text">
                {activeProject?.name || "Projet par défaut"}
              </h2>
            </div>
            {activeProject?.description && (
              <p className="text-xs text-muted mt-0.5">{activeProject.description}</p>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Switch Project Select */}
          <div className="flex items-center gap-2">
            <label className="text-xs text-muted hidden sm:inline">Changer :</label>
            <select
              value={projectsData.active_project_id}
              onChange={(e) => onActivate(e.target.value)}
              className="bg-surface border border-border rounded-md px-3 py-1.5 text-sm text-text focus:border-accent focus:ring-1 focus:ring-accent outline-none cursor-pointer"
            >
              {projectsData.projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} {p.id === projectsData.active_project_id ? "✓" : ""}
                </option>
              ))}
            </select>
          </div>

          {/* Save modifications into current project */}
          {activeProject && (
            <button
              onClick={() => onSaveCurrent(activeProject.id)}
              title="Enregistrer la configuration et les sons actuels dans ce projet"
              className="px-3 py-1.5 text-xs font-medium bg-surface text-text hover:bg-surface border border-border hover:border-accent rounded-md transition-colors flex items-center gap-1.5"
            >
              <span>💾</span> Sauvegarder
            </button>
          )}

          {/* Create New Project Button */}
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-3 py-1.5 text-xs font-semibold bg-accent hover:bg-accent/90 text-white rounded-md transition-colors flex items-center gap-1.5 shadow-sm shadow-accent/20"
          >
            <span>➕</span> Nouveau Projet
          </button>

          {/* Delete Project Button */}
          {activeProject && projectsData.projects.length > 1 && (
            <button
              onClick={() => {
                if (
                  window.confirm(
                    `Confirmez-vous la suppression du projet "${activeProject.name}" ?`
                  )
                ) {
                  onDelete(activeProject.id);
                }
              }}
              title="Supprimer ce projet"
              className="px-2.5 py-1.5 text-xs text-error/80 hover:text-error hover:bg-error/10 border border-error/20 rounded-md transition-colors"
            >
              🗑️
            </button>
          )}
        </div>
      </div>

      {/* Modal: New Project */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fadeIn">
          <div className="fc-card w-full max-w-md bg-surface border border-border rounded-xl p-6 shadow-2xl animate-fadeSlideDown">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold text-text flex items-center gap-2">
                <span>📁</span> Créer un nouveau projet
              </h3>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-muted hover:text-text text-xl leading-none"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateSubmit} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-text block mb-1">
                  Nom du projet <span className="text-accent">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="Ex : Journal Matin, Flash 18h, Sport..."
                  value={newProjName}
                  onChange={(e) => setNewProjName(e.target.value)}
                  className="w-full bg-surface2 border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent outline-none"
                  autoFocus
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-text block mb-1">
                  Description (optionnelle)
                </label>
                <input
                  type="text"
                  placeholder="Ex : Jingles dynamiques avec ducking -24dB"
                  value={newProjDesc}
                  onChange={(e) => setNewProjDesc(e.target.value)}
                  className="w-full bg-surface2 border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent outline-none"
                />
              </div>

              <div className="pt-2">
                <label className="flex items-center gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={copyCurrentBank}
                    onChange={(e) => setCopyCurrentBank(e.target.checked)}
                    className="w-4 h-4 accent-accent rounded"
                  />
                  <span className="text-xs text-text">
                    Copier les sons et réglages actuels de la banque dans ce projet
                  </span>
                </label>
                <p className="text-[11px] text-muted mt-1 pl-6">
                  Si décoché, le projet démarrera avec les paramètres d'usine.
                </p>
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-border mt-6">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 text-sm font-medium text-muted hover:text-text hover:bg-surface2 rounded-md transition-colors"
                >
                  Annuler
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 text-sm font-semibold bg-accent hover:bg-accent/90 text-white rounded-md transition-colors shadow-sm"
                >
                  Créer et Activer
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

// ── ASSET CARD ─────────────────────────────────────────────────────────────

function AssetCard({
  title,
  desc,
  meta,
  onUpload,
}: {
  title: string;
  desc: string;
  meta?: AssetMetadata;
  onUpload: (file: File) => void;
}) {
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
      className={`fc-card relative overflow-hidden transition-colors ${
        dragActive ? "border-accent bg-accent/5" : ""
      }`}
      onDragEnter={handleDrag}
      onDragLeave={handleDrag}
      onDragOver={handleDrag}
      onDrop={handleDrop}
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
          <audio
            controls
            src={getUrl(`/${meta.path}`)}
            className="w-full h-10 outline-none rounded-md"
          />
          <div className="flex justify-between text-xs text-muted bg-surface2 p-2 rounded-md border border-border">
            <span>Durée: {meta.duration_s}s</span>
            <span>Taille: {((meta.size_bytes || 0) / 1024 / 1024).toFixed(2)} MB</span>
          </div>
          {meta.duration_warning && (
            <div className="text-xs text-error bg-error/10 p-2 rounded border border-error/20">
              ⚠️ {meta.duration_warning}
            </div>
          )}
        </div>
      )}

      <div className="mt-4 pt-4 border-t border-border flex justify-between items-center">
        <span className="text-xs text-muted">
          {dragActive ? "Lâchez le fichier ici" : "Glissez un .mp3, .wav, .m4a ou .mp4"}
        </span>
        <button
          onClick={() => inputRef.current?.click()}
          className="px-3 py-1.5 text-sm bg-accent/20 text-accent hover:bg-accent hover:text-white transition-colors rounded-md font-medium"
        >
          {meta?.exists ? "Remplacer" : "Uploader"}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".mp3,.wav,.m4a,.ma4,.mp4,audio/*,video/mp4"
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.[0]) onUpload(e.target.files[0]);
          }}
        />
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

function ConfigPanel({
  defaults,
  activeProject,
  onSaved,
}: {
  defaults: SourceBankDefaults;
  activeProject?: ProjectModel;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    duck_db: defaults.duck_db,
    transition_high_db: defaults.transition_high_db,
    transition_total_ms: defaults.transition_total_ms,
    transition_fade_in_ms: defaults.transition_fade_in_ms,
    transition_fade_out_ms: defaults.transition_fade_out_ms,
    silence_thresh_db_relative: defaults.silence_thresh_db_relative,
    min_silence_len_ms: defaults.min_silence_len_ms,
    segment_trim_pad_ms: defaults.segment_trim_pad_ms,
    normalize_voice: defaults.normalize_voice ?? true,
    target_peak_dbfs: defaults.target_peak_dbfs ?? -1.0,
  });

  // Re-sync form state when project or defaults change
  useEffect(() => {
    setForm({
      duck_db: defaults.duck_db,
      transition_high_db: defaults.transition_high_db,
      transition_total_ms: defaults.transition_total_ms,
      transition_fade_in_ms: defaults.transition_fade_in_ms,
      transition_fade_out_ms: defaults.transition_fade_out_ms,
      silence_thresh_db_relative: defaults.silence_thresh_db_relative,
      min_silence_len_ms: defaults.min_silence_len_ms,
      segment_trim_pad_ms: defaults.segment_trim_pad_ms,
      normalize_voice: defaults.normalize_voice ?? true,
      target_peak_dbfs: defaults.target_peak_dbfs ?? -1.0,
    });
  }, [defaults]);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type, checked } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : parseFloat(value),
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await updateSourceBankConfig(form);
      // Also update project if one is active
      if (activeProject) {
        await updateProject(activeProject.id, { config: form });
      }
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
          <h2 className="text-xl font-bold text-text">Paramètres de mixage</h2>
          <p className="text-sm text-muted">
            Ajustez le niveau sonore, les transitions et les filtres audio appliqués au bulletin.
          </p>
        </div>
        <button
          type="submit"
          disabled={saving}
          className="px-4 py-2 bg-accent hover:bg-accent/80 text-white font-medium rounded-md transition-colors disabled:opacity-50"
        >
          {saving ? "Sauvegarde..." : "Sauvegarder les paramètres"}
        </button>
      </div>

      {error && (
        <div className="mb-4 text-sm text-error bg-error/10 p-3 rounded border border-error/20">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Normalization feature */}
        <div className="space-y-1 md:col-span-2 lg:col-span-3 bg-surface p-4 rounded-lg border border-accent/30 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="normalize_voice"
                name="normalize_voice"
                checked={form.normalize_voice}
                onChange={handleChange}
                className="w-4 h-4 accent-accent rounded cursor-pointer"
              />
              <label
                htmlFor="normalize_voice"
                className="text-sm font-semibold text-text cursor-pointer"
              >
                🎙️ Normalisation audio & amélioration vocale studio (Style Broadcast)
              </label>
            </div>
            <p className="text-xs text-muted pl-6">
              Amplifie automatiquement la voix, supprime les bruits sourds (85 Hz) et égalise la clarté pour une présence nette au-dessus de la musique.
            </p>
          </div>
          {form.normalize_voice && (
            <div className="flex items-center gap-3 pl-6 md:pl-0">
              <label className="text-xs font-medium text-text whitespace-nowrap">
                Niveau crête cible (dBFS) :
              </label>
              <input
                type="number"
                name="target_peak_dbfs"
                value={form.target_peak_dbfs}
                onChange={handleChange}
                min={-12}
                max={0}
                step={0.5}
                className="w-20 bg-surface2 border border-border rounded px-2 py-1 text-sm text-text"
              />
            </div>
          )}
        </div>

        <ConfigField
          label="Ducking Fond (dB)"
          name="duck_db"
          value={form.duck_db}
          onChange={handleChange}
          min={-60}
          max={0}
          step={1}
          hint="Niveau de musique sous la voix (-18 à -26 dB)"
        />
        <ConfigField
          label="Pic Transition (dB)"
          name="transition_high_db"
          value={form.transition_high_db}
          onChange={handleChange}
          min={-60}
          max={0}
          step={1}
          hint="Volume du fond pendant la transition (-3 dB)"
        />
        <ConfigField
          label="Durée Transition (ms)"
          name="transition_total_ms"
          value={form.transition_total_ms}
          onChange={handleChange}
          min={500}
          max={10000}
          step={100}
          hint="Durée totale insérée (3000 ms)"
        />
        <ConfigField
          label="Fade In Transition (ms)"
          name="transition_fade_in_ms"
          value={form.transition_fade_in_ms}
          onChange={handleChange}
          min={0}
          max={5000}
          step={100}
          hint="Temps de montée (1000 ms)"
        />
        <ConfigField
          label="Fade Out Transition (ms)"
          name="transition_fade_out_ms"
          value={form.transition_fade_out_ms}
          onChange={handleChange}
          min={0}
          max={5000}
          step={100}
          hint="Temps de descente (1000 ms)"
        />
        <ConfigField
          label="Seuil Silence (dB relatif)"
          name="silence_thresh_db_relative"
          value={form.silence_thresh_db_relative}
          onChange={handleChange}
          min={-60}
          max={-1}
          step={1}
          hint="Relatif à la voix moyenne (-16 dB)"
        />
        <ConfigField
          label="Durée Silence Min (ms)"
          name="min_silence_len_ms"
          value={form.min_silence_len_ms}
          onChange={handleChange}
          min={50}
          max={10000}
          step={50}
          hint="Détection des pauses vocales (400 ms)"
        />
        <ConfigField
          label="Marge Coupe (ms)"
          name="segment_trim_pad_ms"
          value={form.segment_trim_pad_ms}
          onChange={handleChange}
          min={0}
          max={1000}
          step={10}
          hint="Marge conservée aux bords (0 ms)"
        />
      </div>
    </form>
  );
}

function ConfigField({ label, name, value, onChange, min, max, step, hint }: any) {
  return (
    <div className="space-y-1">
      <label className="text-sm font-medium text-text block">{label}</label>
      <input
        type="number"
        name={name}
        value={value}
        onChange={onChange}
        min={min}
        max={max}
        step={step}
        className="w-full bg-surface2 border border-border rounded-md px-3 py-2 text-text text-sm focus:border-accent focus:ring-1 focus:ring-accent outline-none"
      />
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  );
}
