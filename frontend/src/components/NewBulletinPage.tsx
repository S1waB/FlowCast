import React, { useState, useEffect, useRef } from "react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import WaveSurfer from "wavesurfer.js";
import { createBulletin, getBulletinStatus, getDownloadUrl, BulletinStatusResponse } from "../api/bulletins";

// ── TYPES ──────────────────────────────────────────────────────────────────

interface Clip {
  id: string;
  file: File;
  url: string;
}

// ── MAIN PAGE COMPONENT ────────────────────────────────────────────────────

export default function NewBulletinPage() {
  const [clips, setClips] = useState<Clip[]>([]);
  const [dragActive, setDragActive] = useState(false);

  // Job state
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<BulletinStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Sensors for dnd-kit
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

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
    // Initial fetch
    poll();

    return () => clearInterval(intervalId);
  }, [jobId]);

  // ── Drag & Drop Handlers (Files) ──

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

  const addFiles = (files: FileList | File[]) => {
    const newClips: Clip[] = Array.from(files)
      .filter((file) => file.name.toLowerCase().endsWith(".mp3") || file.name.toLowerCase().endsWith(".wav"))
      .map((file) => ({
        id: crypto.randomUUID(),
        file,
        url: URL.createObjectURL(file),
      }));
    setClips((prev) => [...prev, ...newClips]);
  };

  const handleDropFiles = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      addFiles(e.dataTransfer.files);
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      addFiles(e.target.files);
    }
  };

  const removeClip = (id: string) => {
    setClips((prev) => {
      const clip = prev.find((c) => c.id === id);
      if (clip) URL.revokeObjectURL(clip.url);
      return prev.filter((c) => c.id !== id);
    });
  };

  // ── Dnd-kit Handlers (Reorder) ──

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      setClips((items) => {
        const oldIndex = items.findIndex((i) => i.id === active.id);
        const newIndex = items.findIndex((i) => i.id === over.id);
        return arrayMove(items, oldIndex, newIndex);
      });
    }
  };

  // ── Generation ──

  const handleGenerate = async () => {
    if (clips.length === 0) return;
    setError(null);
    setJobId(null);
    setJobStatus(null);
    
    try {
      const files = clips.map((c) => c.file);
      const res = await createBulletin(files);
      setJobId(res.job_id);
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-4 space-y-8 animate-fadeSlideDown">
      <header className="mb-6">
        <h1 className="text-3xl font-bold text-transparent bg-clip-text bg-gradient-to-br from-white to-accent">Nouveau Bulletin</h1>
        <p className="text-muted mt-2">Uploadez vos clips vocaux, réordonnez-les et lancez la génération automatique.</p>
      </header>

      {/* Main Dropzone */}
      {!jobId && (
        <>
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDropFiles}
            className={`border-2 border-dashed rounded-lg p-12 text-center transition-colors ${
              dragActive ? "border-accent bg-accent/5" : "border-border bg-surface2"
            }`}
          >
            <div className="text-4xl mb-4">📥</div>
            <h3 className="text-lg font-semibold text-text mb-2">Glissez vos fichiers vocaux ici</h3>
            <p className="text-sm text-muted mb-4">Formats acceptés : .mp3, .wav (max 500 MB / fichier)</p>
            <label className="cursor-pointer px-4 py-2 bg-surface text-text font-medium rounded-md border border-border hover:bg-surface2 transition-colors">
              Ou parcourez vos fichiers
              <input type="file" multiple accept=".mp3,.wav" className="hidden" onChange={handleFileInput} />
            </label>
          </div>

          {/* Reorderable List */}
          {clips.length > 0 && (
            <div className="fc-card space-y-4">
              <h2 className="text-xl font-bold text-text flex items-center justify-between">
                <span>Clips sélectionnés ({clips.length})</span>
                <button
                  onClick={handleGenerate}
                  className="px-4 py-2 bg-accent hover:bg-accent/80 text-white font-medium rounded-md transition-colors shadow-lg shadow-accent/20"
                >
                  ✨ Générer le bulletin
                </button>
              </h2>
              
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                <SortableContext items={clips.map((c) => c.id)} strategy={verticalListSortingStrategy}>
                  <div className="space-y-2">
                    {clips.map((clip, index) => (
                      <SortableClipItem key={clip.id} clip={clip} index={index} onRemove={() => removeClip(clip.id)} />
                    ))}
                  </div>
                </SortableContext>
              </DndContext>
            </div>
          )}
        </>
      )}

      {/* Error state */}
      {error && (
        <div className="fc-card bg-error/10 border-error/20">
          <h2 className="text-error font-bold mb-2">Erreur</h2>
          <p className="text-sm text-error/80">{error}</p>
          <button onClick={() => { setError(null); setJobId(null); }} className="mt-4 px-4 py-2 bg-surface text-text rounded-md border border-border">Réessayer</button>
        </div>
      )}

      {/* Job Status & Result */}
      {jobId && !error && (
        <JobProgressView jobStatus={jobStatus} jobId={jobId} onReset={() => {
          setJobId(null);
          setJobStatus(null);
          setClips([]);
        }} />
      )}

    </div>
  );
}

// ── SORTABLE CLIP ITEM ─────────────────────────────────────────────────────

function SortableClipItem({ clip, index, onRemove }: { clip: Clip; index: number; onRemove: () => void }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: clip.id });
  const [duration, setDuration] = useState<string>("...");

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const formatSize = (bytes: number) => (bytes / 1024 / 1024).toFixed(2) + " MB";

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="flex items-center gap-4 p-3 bg-surface border border-border rounded-lg shadow-sm group hover:border-accent/50 transition-colors"
    >
      {/* Drag handle */}
      <button {...attributes} {...listeners} className="cursor-grab p-2 text-muted hover:text-text active:cursor-grabbing">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="9" cy="12" r="1"/><circle cx="9" cy="5" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="19" r="1"/></svg>
      </button>

      <div className="flex-shrink-0 w-8 text-center text-muted font-mono font-medium text-sm">
        #{index + 1}
      </div>

      <div className="flex-grow min-w-0 flex flex-col justify-center">
        <span className="font-medium text-text truncate block">{clip.file.name}</span>
        <div className="flex gap-3 text-xs text-muted mt-1">
          <span>{formatSize(clip.file.size)}</span>
          <span>{duration}</span>
        </div>
      </div>

      <div className="w-32 h-10 flex-shrink-0 bg-bg rounded overflow-hidden">
        <MiniWaveform url={clip.url} onDuration={(sec) => {
          const m = Math.floor(sec / 60);
          const s = Math.floor(sec % 60).toString().padStart(2, "0");
          setDuration(`${m}:${s}`);
        }} />
      </div>

      <button onClick={onRemove} className="p-2 text-muted hover:text-error transition-colors rounded-full hover:bg-error/10 ml-2" title="Supprimer">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
      </button>
    </div>
  );
}

// ── MINI WAVEFORM ──────────────────────────────────────────────────────────

function MiniWaveform({ url, onDuration }: { url: string; onDuration: (duration: number) => void }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const wavesurfer = useRef<WaveSurfer | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    wavesurfer.current = WaveSurfer.create({
      container: containerRef.current,
      waveColor: 'rgba(255, 255, 255, 0.2)',
      progressColor: 'rgba(255, 255, 255, 0.5)',
      height: 40,
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      interact: false,
    });

    wavesurfer.current.load(url);

    wavesurfer.current.on('ready', () => {
      onDuration(wavesurfer.current?.getDuration() || 0);
    });

    return () => {
      wavesurfer.current?.destroy();
    };
  }, [url, onDuration]);

  return <div ref={containerRef} className="w-full h-full" />;
}

// ── JOB PROGRESS VIEW ──────────────────────────────────────────────────────

function JobProgressView({ jobStatus, jobId, onReset }: { jobStatus: BulletinStatusResponse | null, jobId: string, onReset: () => void }) {
  const status = jobStatus?.status || "pending";
  const isDone = status === "done";
  
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
              <p className="text-xs text-muted mb-1">Transitions insérées</p>
              <p className="text-xl font-bold text-text">{jobStatus.transitions_count}</p>
            </div>
          </div>

          <div className="p-4 bg-surface rounded-lg border border-border shadow-sm">
            <audio controls src={getDownloadUrl(jobId)} className="w-full outline-none" />
          </div>

          <div className="flex gap-4 justify-center">
            <a 
              href={getDownloadUrl(jobId)} 
              download={`bulletin_${jobId}.mp3`}
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
