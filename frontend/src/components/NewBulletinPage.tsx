import React, { useState, useEffect, useRef } from "react";
import WaveSurfer from "wavesurfer.js";
import { createBulletin, getBulletinStatus, getDownloadUrl, BulletinStatusResponse } from "../api/bulletins";
import { fetchProjects, activateProject, ProjectModel } from "../api/projects";

export default function NewBulletinPage() {
  const [file, setFile] = useState<{ raw: File, url: string } | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [projects, setProjects] = useState<ProjectModel[]>([]);
  const [activeProjId, setActiveProjId] = useState<string>("default");

  useEffect(() => {
    fetchProjects().then(res => {
      setProjects(res.projects);
      setActiveProjId(res.active_project_id);
    }).catch(() => {});
  }, []);

  // Job state
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<BulletinStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Poll for job status
  useEffect(() => {
    if (!jobId) return;

    let intervalId: any;
    const poll = async () => {
      try {
        const res = await getBulletinStatus(jobId);
        setJobStatus(res);
        if (res.status === "done" || res.status === "error") {
          clearInterval(intervalId);
        }
      } catch (err: any) {
        setError(err.message);
        clearInterval(intervalId);
      }
    };

    intervalId = setInterval(poll, 2000);
    poll();

    return () => clearInterval(intervalId);
  }, [jobId]);

  // ── Drag & Drop Handlers ──

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
  };

  const addFile = (rawFile: File) => {
    const validExts = [".mp3", ".wav", ".m4a", ".ma4", ".mp4"];
    const fileName = rawFile.name.toLowerCase();
    const isValid = validExts.some(ext => fileName.endsWith(ext));
    if (!isValid) {
      setError("Format non supporté. Formats acceptés : .mp3, .wav, .m4a, .mp4");
      return;
    }
    if (file) URL.revokeObjectURL(file.url);
    setFile({
      raw: rawFile,
      url: URL.createObjectURL(rawFile)
    });
  };

  const handleDropFiles = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      addFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      addFile(e.target.files[0]);
    }
  };

  // ── Generation ──

  const handleGenerate = async () => {
    if (!file) return;
    setError(null);
    setJobId(null);
    setJobStatus(null);
    
    try {
      const activeProject = projects.find(p => p.id === activeProjId);
      const res = await createBulletin(file.raw, activeProject?.name);
      setJobId(res.job_id);
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-4 space-y-8 animate-fadeSlideDown">
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-3xl font-bold text-transparent bg-clip-text bg-gradient-to-br from-white to-accent">Nouveau Bulletin</h1>
          <p className="text-muted mt-1">Uploadez votre enregistrement brut, l'IA détectera les silences et mixera le bulletin automatiquement.</p>
        </div>
        {projects.length > 0 && (
          <div className="flex items-center gap-2 bg-surface2 px-3 py-1.5 rounded-lg border border-border">
            <span className="text-xs text-muted">Projet actif :</span>
            <select
              value={activeProjId}
              onChange={async (e) => {
                const newId = e.target.value;
                setActiveProjId(newId);
                await activateProject(newId);
              }}
              className="bg-surface text-text text-xs font-semibold rounded px-2 py-1 border border-border focus:border-accent outline-none cursor-pointer"
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </header>

      {/* Main Dropzone */}
      {!jobId && !file && (
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDropFiles}
          className={`border-2 border-dashed rounded-lg p-12 text-center transition-colors ${
            dragActive ? "border-accent bg-accent/5" : "border-border bg-surface2"
          }`}
        >
          <div className="text-4xl mb-4">🎤</div>
          <h3 className="text-lg font-semibold text-text mb-2">Glissez votre fichier vocal brut ici</h3>
          <p className="text-sm text-muted mb-4">1 seul fichier contenant tous les clips avec des pauses (Formats : .mp3, .wav, .m4a, .mp4)</p>
          <label className="cursor-pointer px-4 py-2 bg-surface text-text font-medium rounded-md border border-border hover:bg-surface2 transition-colors">
            Ou parcourez vos fichiers
            <input type="file" accept=".mp3,.wav,.m4a,.ma4,.mp4,audio/*,video/mp4" className="hidden" onChange={handleFileInput} />
          </label>
        </div>
      )}

      {/* File preview */}
      {!jobId && file && (
        <div className="fc-card space-y-4">
          <div className="flex justify-between items-center">
            <h2 className="text-xl font-bold text-text">Enregistrement brut</h2>
            <button
              onClick={() => {
                URL.revokeObjectURL(file.url);
                setFile(null);
              }}
              className="text-sm text-error hover:underline"
            >
              Changer de fichier
            </button>
          </div>
          
          <div className="bg-surface p-4 rounded-lg border border-border shadow-sm flex flex-col gap-4">
            <div className="flex justify-between items-center text-sm">
              <span className="font-medium text-text truncate block">{file.raw.name}</span>
              <span className="text-muted flex-shrink-0">{(file.raw.size / 1024 / 1024).toFixed(2)} MB</span>
            </div>
            <div className="w-full h-24 bg-bg rounded overflow-hidden">
              <MiniWaveform url={file.url} />
            </div>
          </div>
          
          <button
            onClick={handleGenerate}
            className="w-full py-3 mt-4 bg-accent hover:bg-accent/80 text-white font-bold rounded-md transition-colors shadow-lg shadow-accent/20"
          >
            ✨ Générer le bulletin mixé
          </button>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="fc-card bg-error/10 border-error/20">
          <h2 className="text-error font-bold mb-2">Erreur</h2>
          <p className="text-sm text-error/80">{error}</p>
          <button onClick={() => setError(null)} className="mt-4 px-4 py-2 bg-surface text-text rounded-md border border-border">Réessayer</button>
        </div>
      )}

      {/* Job Status & Result */}
      {jobId && !error && (
        <JobProgressView jobStatus={jobStatus} jobId={jobId} onReset={() => {
          setJobId(null);
          setJobStatus(null);
          if (file) URL.revokeObjectURL(file.url);
          setFile(null);
        }} />
      )}

    </div>
  );
}

// ── MINI WAVEFORM ──────────────────────────────────────────────────────────

function MiniWaveform({ url }: { url: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const wavesurfer = useRef<WaveSurfer | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    wavesurfer.current = WaveSurfer.create({
      container: containerRef.current,
      waveColor: 'rgba(255, 255, 255, 0.2)',
      progressColor: 'rgba(255, 255, 255, 0.5)',
      height: 96,
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      interact: true,
      cursorColor: 'white'
    });

    wavesurfer.current.load(url);

    return () => {
      wavesurfer.current?.destroy();
    };
  }, [url]);

  return <div ref={containerRef} className="w-full h-full" />;
}

// ── JOB PROGRESS VIEW ──────────────────────────────────────────────────────

function JobProgressView({ jobStatus, jobId, onReset }: { jobStatus: BulletinStatusResponse | null, jobId: string, onReset: () => void }) {
  const status = jobStatus?.status || "pending";
  const isDone = status === "done";

  const getDownloadFilename = () => {
    const d = jobStatus?.created_at ? new Date(jobStatus.created_at) : new Date();
    const pad = (n: number) => n.toString().padStart(2, "0");
    const time = `${pad(d.getHours())}-${pad(d.getMinutes())}-${pad(d.getSeconds())}`;
    const date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    const proj = (jobStatus?.project_name || "project")
      .replace(/[^\w\-]+/g, "_")
      .replace(/^_+|_+$/g, "") || "project";
    return `news_${proj}_${time}_${date}.mp3`;
  };
  
  const progressMap = {
    pending: { label: "En attente...", width: "10%" },
    processing: { label: "Assemblage et mixage en cours...", width: "60%" },
    done: { label: "Terminé", width: "100%" },
    error: { label: "Erreur", width: "100%" },
  };

  return (
    <div className="fc-card flex flex-col items-center justify-center py-12 text-center animate-fadeSlideUp">
      <div className="mb-6">
        {status === "pending" || status === "processing" ? (
          <div className="w-16 h-16 border-4 border-accent border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        ) : status === "done" ? (
          <div className="w-16 h-16 bg-ok/20 text-ok rounded-full flex items-center justify-center text-3xl mx-auto mb-4">🎉</div>
        ) : (
          <div className="w-16 h-16 bg-error/20 text-error rounded-full flex items-center justify-center text-3xl mx-auto mb-4">❌</div>
        )}
        <h2 className="text-2xl font-bold text-text">{progressMap[status].label}</h2>
        <p className="text-muted mt-2">ID du Job : <code className="bg-surface2 px-2 py-1 rounded text-xs">{jobId}</code></p>
      </div>

      <div className="w-full max-w-md bg-surface2 rounded-full h-2.5 mb-8 overflow-hidden">
        <div 
          className={`h-2.5 rounded-full transition-all duration-500 ${status === "error" ? "bg-error" : "bg-accent"}`} 
          style={{ width: progressMap[status].width }}
        ></div>
      </div>

      {isDone && jobStatus && (
        <div className="w-full max-w-lg space-y-6 animate-fadeSlideDown">
          <div className="grid grid-cols-2 gap-4 text-left">
            <div className="bg-surface2 p-4 rounded-lg border border-border">
              <p className="text-xs text-muted mb-1">Durée finale</p>
              <p className="text-xl font-bold text-text">
                {Math.floor((jobStatus.duration_s || 0) / 60)}:
                {Math.floor((jobStatus.duration_s || 0) % 60).toString().padStart(2, "0")}
              </p>
            </div>
            <div className="bg-surface2 p-4 rounded-lg border border-border">
              <p className="text-xs text-muted mb-1">Segments vocaux détectés</p>
              <p className="text-xl font-bold text-text">{jobStatus.segments_count}</p>
            </div>
          </div>

          <div className="p-4 bg-surface rounded-lg border border-border shadow-sm">
            <audio controls src={getDownloadUrl(jobId)} className="w-full outline-none" />
          </div>

          <div className="flex gap-4 justify-center">
            <a 
              href={getDownloadUrl(jobId)} 
              download={getDownloadFilename()}
              className="px-6 py-2.5 bg-accent hover:bg-accent/90 text-white font-medium rounded-md transition-colors shadow-lg shadow-accent/20 flex items-center gap-2"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
              Télécharger le MP3
            </a>
            <button 
              onClick={onReset}
              className="px-6 py-2.5 bg-surface text-text hover:bg-surface2 font-medium rounded-md transition-colors border border-border"
            >
              Nouveau bulletin
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
