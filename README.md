# FlowCast – Audio News Bulletin Auto-Mixer

Mixage automatique de bulletins d'actualité audio. Combine vos clips vocaux avec intro, outro, fond musical et transitions.

## Prérequis

- **Docker** et **Docker Desktop** (recommandé pour un usage simplifié en local).
- *Si lancement manuel (hors Docker) :* Python 3.11, Node.js, et **FFmpeg**. 
  ⚠️ **FFmpeg est strictement requis** pour que le moteur audio (`pydub` / `loudnorm`) fonctionne. (Il est automatiquement inclus dans le conteneur Docker du backend).

## Quick Start (Local Dev)

Lancez les services via Docker Compose. 
*(Note: Utilisez `docker compose` sans tiret sur les versions récentes de Docker)*.

```bash
# Build & start all services
docker compose up --build

# API: http://localhost:8000
# Web: http://localhost:5173
# Docs: http://localhost:8000/docs
```

## Remplacer les Assets (Source Bank)

Par défaut, l'application recherche `intro.mp3`, `outro.mp3`, `fond.mp3`, et `transition.mp3` dans le dossier `backend/source_bank/`.

**Pour les remplacer, deux options :**
1. **Via l'interface Web (Recommandé)** : Allez sur `http://localhost:5173` dans l'onglet **Banque Source** et glissez-déposez vos nouveaux fichiers audio.
2. **Via l'API** : Utilisez l'endpoint `POST /api/source-bank/{role}` avec un fichier multipart.

## Tester le moteur audio en local

Un script de test de bout-en-bout (E2E) est disponible pour vérifier le comportement des transitions courtes (rognage) et longues (centrage avec padding).

```bash
bash scripts/e2e_test.sh
```
*(Le script exportera un fichier mp3 de test dans `backend/output/e2e_test_result.mp3` que vous pourrez écouter).*

## Key Configuration (`backend/config/source_bank.json`)

Les paramètres peuvent être modifiés via l'UI ou l'API sans redémarrer le serveur.

| Parameter | Default | Description |
|---|---|---|
| `duck_db` | -16 dB | Ducking level for background music |
| `transition_max_ms` | 5000 ms | Max transition clip length |
| `transition_fade_in_ms` | 1000 ms | Transition fade-in duration |
| `transition_fade_out_ms` | 1000 ms | Transition fade-out duration |
| `silence_thresh_db_relative` | -16 dB | Silence threshold relative to clip mean dBFS |
| `min_silence_len_ms` | 400 ms | Min silence length to detect |
| `min_gap_safety_ms` | 100 ms | Safety margin before/after speech |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SOURCE_BANK_DIR` | `/app/source_bank` | Path to shared audio assets |
| `UPLOADS_DIR` | `/app/uploads` | Path to raw vocal clip uploads |
| `OUTPUT_DIR` | `/app/output` | Path to generated bulletins |
| `CONFIG_DIR` | `/app/config` | Path to config directory |

