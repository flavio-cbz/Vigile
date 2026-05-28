#!/usr/bin/env python3
"""
Vigile — Dev Launcher
Lance le backend (uvicorn) et/ou le frontend (Vite) en parallèle.
Cross-platform: Mac, Windows, Linux.

Usage:
    python scripts/vigile.py            # Backend + Frontend
    python scripts/vigile.py --backend  # Backend seulement
    python scripts/vigile.py --frontend # Frontend seulement
"""
import subprocess
import sys
import os
import signal
import time
import argparse

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(PROJECT_DIR, "frontend")
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = "8000"
FRONTEND_PORT = "5173"

processes: list[subprocess.Popen] = []


def cleanup(signum=None, frame=None) -> None:
    print("\n🛑 Arrêt des serveurs...")
    for p in processes:
        try:
            p.terminate()
        except Exception:
            pass
    for p in processes:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                p.kill()
            except Exception:
                pass
    print("✓ Serveurs arrêtés.")
    sys.exit(0)


signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)


def start_backend() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = PROJECT_DIR
    return subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "master.main:app",
            "--host", BACKEND_HOST,
            "--port", BACKEND_PORT,
            "--reload",
        ],
        cwd=PROJECT_DIR,
        env=env,
    )


def start_frontend() -> subprocess.Popen:
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    return subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=FRONTEND_DIR,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vigile — Dev Launcher (backend + frontend)",
    )
    parser.add_argument(
        "--backend", action="store_true",
        help="Lancer seulement le backend",
    )
    parser.add_argument(
        "--frontend", action="store_true",
        help="Lancer seulement le frontend",
    )
    args = parser.parse_args()

    run_backend = args.backend or not args.frontend
    run_frontend = args.frontend or not args.backend

    print("🚀 Vigile — Dev Mode\n")

    if run_backend:
        print(f"⚙️   Backend  → http://{BACKEND_HOST}:{BACKEND_PORT}")
        processes.append(start_backend())

    if run_frontend:
        print(f"🎨  Frontend → http://{BACKEND_HOST}:{FRONTEND_PORT}")
        processes.append(start_frontend())

    if run_backend:
        print(f"📡 API Docs  → http://{BACKEND_HOST}:{BACKEND_PORT}/api/docs")
    print("⌨️   Ctrl+C pour tout arrêter\n")

    try:
        while True:
            time.sleep(1)
            for p in processes:
                if p.poll() is not None:
                    print(f"⚠️  Un processus s'est arrêté inopinément.")
                    cleanup()
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
