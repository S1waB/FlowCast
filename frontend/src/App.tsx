import { useEffect, useState } from "react";
import { fetchHealth, type HealthResponse } from "./api/health";
import SourceBankPage from "./components/SourceBankPage";
import NewBulletinPage from "./components/NewBulletinPage";
import "./App.css";

type Status = "idle" | "loading" | "ok" | "error";
type Tab = "home" | "sourceBank" | "newBulletin";

export default function App() {
  const [tab, setTab] = useState<Tab>("newBulletin");
  
  return (
    <div className="min-h-screen bg-bg text-text font-sans">
      <nav className="bg-surface border-b border-border p-4 sticky top-0 z-40">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl" aria-hidden="true">🎙️</span>
            <span className="font-bold text-lg tracking-tight">FlowCast</span>
          </div>
          <div className="flex gap-4">
            <button 
              onClick={() => setTab("home")} 
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${tab === "home" ? "bg-accent text-white" : "text-muted hover:text-text hover:bg-surface2"}`}
            >
              Accueil
            </button>
            <button 
              onClick={() => setTab("sourceBank")} 
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${tab === "sourceBank" ? "bg-accent text-white" : "text-muted hover:text-text hover:bg-surface2"}`}
            >
              Banque Source
            </button>
            <button 
              onClick={() => setTab("newBulletin")} 
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${tab === "newBulletin" ? "bg-accent text-white" : "text-muted hover:text-text hover:bg-surface2"}`}
            >
              Nouveau Bulletin
            </button>
          </div>
        </div>
      </nav>

      <main className="p-4">
        {tab === "home" && <HomePage />}
        {tab === "sourceBank" && <SourceBankPage />}
        {tab === "newBulletin" && <NewBulletinPage />}
      </main>
    </div>
  );
}

function HomePage() {
  const [status, setStatus] = useState<Status>("idle");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setStatus("loading");
    fetchHealth()
      .then((data) => {
        setHealth(data);
        setStatus("ok");
      })
      .catch((err: Error) => {
        setError(err.message);
        setStatus("error");
      });
  }, []);

  return (
    <div className="flex flex-col items-center justify-center py-12 gap-8 animate-fadeSlideDown">
      <header className="text-center space-y-3">
        <h1 className="text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-br from-white to-accent">FlowCast API</h1>
        <p className="text-muted">Mixage automatique de bulletins audio</p>
      </header>

      <section className="fc-card w-full max-w-md">
        <h2 className="fc-card__heading">État du service</h2>

        {status === "loading" && (
          <div className="fc-badge fc-badge--loading" role="status">
            <span className="fc-spinner" aria-hidden="true" />
            Connexion en cours…
          </div>
        )}

        {status === "ok" && health && (
          <div className="fc-badge fc-badge--ok" role="status">
            <span className="fc-dot" aria-hidden="true" />
            {health.service} v{health.version} — {health.status}
          </div>
        )}

        {status === "error" && (
          <div className="fc-badge fc-badge--error" role="alert">
            ⚠️ {error}
          </div>
        )}

        {health && (
          <dl className="fc-meta mt-4">
            <dt>Service</dt>
            <dd>{health.service}</dd>
            <dt>Version</dt>
            <dd>{health.version}</dd>
            <dt>Horodatage</dt>
            <dd>{new Date(health.timestamp).toLocaleString("fr-FR")}</dd>
          </dl>
        )}
      </section>
    </div>
  );
}

