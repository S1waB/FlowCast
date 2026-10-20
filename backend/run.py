import uvicorn
import webbrowser
import threading
import time
import os
import sys

def open_browser():
    time.sleep(2) # Give the server a moment to start
    webbrowser.open("http://127.0.0.1:8000")

if __name__ == "__main__":
    # Needed for PyInstaller multiprocessing if used
    try:
        from multiprocessing import freeze_support
        freeze_support()
    except Exception:
        pass

    # Ensure current directory is the directory of the executable
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))

    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="info")
