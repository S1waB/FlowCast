"""
FlowCast – One-Click Application Launcher
Runs the backend server, ensures the frontend is ready, and opens the browser.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
STATIC_DIR = BACKEND_DIR / "static"
INDEX_HTML = STATIC_DIR / "index.html"
REQUIREMENTS_FILE = BACKEND_DIR / "requirements.txt"

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


def check_and_install_python_deps() -> None:
    """Ensure required Python packages are installed."""
    try:
        import fastapi
        import uvicorn
        import pydub
    except ImportError:
        print("📦 Installing required Python dependencies...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)
        ])
        print("✅ Python dependencies installed successfully.\n")


def check_and_build_frontend() -> None:
    """Ensure static frontend is built and copied into backend/static."""
    if not INDEX_HTML.exists():
        print("⚙️  Frontend static files not found. Building frontend...")
        try:
            # Check npm
            subprocess.run(["npm", "--version"], check=True, stdout=subprocess.DEVNULL, shell=True)
            # Run npm run build
            subprocess.run(["npm", "run", "build"], cwd=str(FRONTEND_DIR), check=True, shell=True)
            
            # Copy dist to backend/static
            dist_dir = FRONTEND_DIR / "dist"
            if dist_dir.exists():
                STATIC_DIR.mkdir(parents=True, exist_ok=True)
                for item in dist_dir.iterdir():
                    dest = STATIC_DIR / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dest)
                print("✅ Frontend built and copied to backend/static.\n")
        except Exception as e:
            print(f"⚠️  Could not auto-build frontend ({e}).")
            print("   If you have npm installed, run 'cd frontend && npm run build' manually.\n")


def open_browser() -> None:
    """Wait for server to start, then open default web browser."""
    time.sleep(1.5)
    print(f"\n🌐 Opening FlowCast in browser: {URL}\n")
    webbrowser.open(URL)


def main() -> None:
    print("=" * 60)
    print("           🚀 Starting FlowCast Application...           ")
    print("=" * 60)

    # 1. Check Python dependencies
    check_and_install_python_deps()

    # 2. Check Frontend build
    check_and_build_frontend()

    # 3. Switch working directory to backend so config and assets resolve correctly
    os.chdir(str(BACKEND_DIR))
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    # 4. Launch browser in a background thread
    threading.Thread(target=open_browser, daemon=True).start()

    # 5. Start Uvicorn server
    print(f"📡 Server running at {URL}")
    print("   Press CTRL + C to stop the server at any time.\n")

    import uvicorn
    try:
        uvicorn.run(
            "app.main:app",
            host=HOST,
            port=PORT,
            log_level="info",
            reload=False,
        )
    except KeyboardInterrupt:
        print("\n🛑 FlowCast server stopped. Goodbye!")


if __name__ == "__main__":
    main()
