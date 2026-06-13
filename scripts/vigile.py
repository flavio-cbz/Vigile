#!/usr/bin/env python3
"""
Vigile — Dev Launcher
Lance le backend (uvicorn) et/ou le frontend (Vite) en parallèle.
Cross-platform: Mac, Windows, Linux.

Usage:
    python scripts/vigile.py            # Backend + Frontend
    python scripts/vigile.py --backend  # Backend seulement
    python scripts/vigile.py --frontend # Frontend seulement
    python scripts/vigile.py --host 0.0.0.0 --port 8080 --frontend-port 3000
"""
import subprocess
import sys
import os
import signal
import time
import argparse
import socket
import shutil
import urllib.request
import json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(PROJECT_DIR, "frontend")
BACKEND_DEPENDENCY = "fastapi"

processes: list[subprocess.Popen] = []


def load_env() -> None:
    """Manually load .env variables into os.environ to keep zero-dependency core."""
    env_path = os.path.join(PROJECT_DIR, ".env")
    if os.path.exists(env_path):
        print("📝 Chargement des variables d'environnement depuis le fichier .env...")
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key not in os.environ:
                        os.environ[key] = val


def ensure_data_dir() -> None:
    """Ensure that the data directory exists so SQLite does not crash on startup."""
    data_dir = os.path.join(PROJECT_DIR, "data")
    if not os.path.exists(data_dir):
        print("📁 Création du dossier ./data pour la base de données...")
        os.makedirs(data_dir, exist_ok=True)


def is_port_in_use(host: str, port: int) -> bool:
    """Check if a local port is already bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def kill_process_on_port(port: int) -> bool:
    """Attempts to find and kill the process using a specific local port. Returns True if freed."""
    pid = None
    if sys.platform == "win32":
        try:
            output = subprocess.check_output(["netstat", "-ano"], text=True)
            for line in output.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        break
        except Exception:
            pass
    else:
        try:
            pid = subprocess.check_output(["lsof", "-t", f"-i:{port}"], text=True).strip()
        except Exception:
            try:
                pid_out = subprocess.check_output(["fuser", f"{port}/tcp"], text=True, stderr=subprocess.DEVNULL)
                pid = pid_out.strip()
            except Exception:
                pass

    if not pid:
        return False

    pids = [p.strip() for p in pid.split() if p.strip()]
    print(f"🔍 Port {port} occupé par les PID(s) : {', '.join(pids)}. Tentative d'arrêt...")
    try:
        if sys.platform == "win32":
            for p in pids:
                subprocess.run(["taskkill", "/F", "/T", "/PID", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        else:
            for p in pids:
                os.kill(int(p), signal.SIGKILL)
        
        # Give OS a moment to release socket
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"⚠️ Impossible de forcer l'arrêt du/des processus {', '.join(pids)} : {e}")
        return False


def is_our_backend_running(host: str, port: str) -> bool:
    """Checks if the active service on the port is our Vigile Master Node."""
    url = f"http://{host}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=1.0) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                return data.get("status") == "ok" and "version" in data
    except Exception:
        pass
    return False


def candidate_python_executables() -> list[str]:
    """Return Python executables likely to belong to the project environment."""
    candidates: list[str] = [sys.executable]

    for relative_path in (
        ".venv/bin/python",
        "venv/bin/python",
        ".venv/Scripts/python.exe",
        "venv/Scripts/python.exe",
    ):
        candidate_path = os.path.join(PROJECT_DIR, relative_path)
        if os.path.exists(candidate_path):
            candidates.append(candidate_path)

    for binary_name in ("python3", "python"):
        binary_path = shutil.which(binary_name)
        if binary_path:
            candidates.append(binary_path)

    unique_candidates: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique_candidates.append(candidate)
    return unique_candidates


def python_can_import_backend_dependencies(python_executable: str) -> bool:
    """Check whether the interpreter is >= 3.10 and can import the backend stack."""
    try:
        # Enforce Python >= 3.10 due to PEP 604 type unions (e.g. str | None)
        version_check = subprocess.run(
            [python_executable, "-c", "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"],
            capture_output=True,
            check=False,
        )
        if version_check.returncode != 0:
            return False

        completed = subprocess.run(
            [python_executable, "-c", f"import {BACKEND_DEPENDENCY}"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.returncode == 0
    except Exception:
        return False


def ensure_virtual_env() -> str:
    """Checks if a virtual environment exists. If not, creates one and installs requirements."""
    relative_venv_paths = (
        (".venv/Scripts/python.exe" if sys.platform == "win32" else ".venv/bin/python"),
        ("venv/Scripts/python.exe" if sys.platform == "win32" else "venv/bin/python"),
    )
    
    venv_python = None
    for rel in relative_venv_paths:
        path = os.path.join(PROJECT_DIR, rel)
        if os.path.exists(path):
            venv_python = path
            break
            
    if not venv_python:
        print("📁 Environnement virtuel `.venv` non trouvé. Création en cours...")
        try:
            subprocess.run([sys.executable, "-m", "venv", os.path.join(PROJECT_DIR, ".venv")], check=True)
            print("✓ Environnement virtuel créé.")
            for rel in relative_venv_paths:
                path = os.path.join(PROJECT_DIR, rel)
                if os.path.exists(path):
                    venv_python = path
                    break
        except Exception as e:
            print(f"⚠️ Impossible de créer automatiquement l'environnement virtuel : {e}")
            print("Utilisation de l'interpréteur Python actuel.")
            venv_python = sys.executable

    # Verify dependency state in resolved venv
    if venv_python and not python_can_import_backend_dependencies(venv_python):
        print("📦 FastAPI ou d'autres dépendances backend manquantes dans l'environnement virtuel.")
        print("Installation des dépendances depuis requirements.txt...")
        try:
            subprocess.run([venv_python, "-m", "pip", "install", "-r", os.path.join(PROJECT_DIR, "requirements.txt")], check=True)
            print("✓ Dépendances backend installées.")
        except Exception as e:
            print(f"❌ Erreur lors de l'installation des dépendances : {e}")
            
    return venv_python or sys.executable


def resolve_backend_python() -> str:
    """Pick the first Python executable that can run the FastAPI backend, or create/install one."""
    for candidate in candidate_python_executables():
        if python_can_import_backend_dependencies(candidate):
            return candidate

    return ensure_virtual_env()


def ensure_frontend_dependencies() -> None:
    """Checks if node_modules and the vite executable exists in frontend folder, otherwise installs packages."""
    node_modules_dir = os.path.join(FRONTEND_DIR, "node_modules")
    vite_bin = os.path.join(node_modules_dir, ".bin", "vite.cmd" if sys.platform == "win32" else "vite")
    if not os.path.exists(node_modules_dir) or not os.path.exists(vite_bin):
        print("📦 Dépendances frontend (Vite) manquantes ou incomplètes. Installation/réparation en cours...")
        npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
        if not shutil.which(npm_cmd):
            print("❌ Erreur: 'npm' n'est pas installé ou n'est pas disponible dans votre variable PATH.")
            print("Veuillez installer Node.js (qui inclut npm) et réessayer.")
            sys.exit(1)
        try:
            subprocess.run([npm_cmd, "install"], cwd=FRONTEND_DIR, check=True)
            print("✓ Dépendances frontend installées.")
        except Exception as e:
            print(f"❌ Erreur lors de l'installation des dépendances frontend : {e}")
            sys.exit(1)


def cleanup(signum=None, frame=None) -> None:
    print("\n🛑 Arrêt des serveurs...")
    for p in processes:
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                p.terminate()
        except Exception:
            pass
    for p in processes:
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                if sys.platform != "win32":
                    p.kill()
            except Exception:
                pass
    print("✓ Serveurs arrêtés.")
    sys.exit(0)


signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)


def start_backend(host: str, port: str, python_executable: str) -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = PROJECT_DIR
    env["PYTHONIOENCODING"] = "utf-8"
    
    # Propagate host and port to backend config via environment overrides
    env["HOST"] = host
    env["PORT"] = port
    
    return subprocess.Popen(
        [
            python_executable, "-m", "uvicorn", "master.main:app",
            "--host", host,
            "--port", port,
            "--reload",
        ],
        cwd=PROJECT_DIR,
        env=env,
    )


def start_frontend(host: str, port: str, backend_host: str, backend_port: str) -> subprocess.Popen:
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    env = os.environ.copy()
    env["VITE_BACKEND_HOST"] = backend_host
    env["VITE_BACKEND_PORT"] = backend_port
    
    return subprocess.Popen(
        [npm_cmd, "run", "dev", "--", "--port", port, "--host", host],
        cwd=FRONTEND_DIR,
        env=env,
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
    parser.add_argument(
        "--host", type=str, default="127.0.0.1",
        help="Hôte de liaison (défaut: 127.0.0.1)",
    )
    parser.add_argument(
        "--port", type=str, default="8000",
        help="Port du backend (défaut: 8000)",
    )
    parser.add_argument(
        "--frontend-port", type=str, default="5173",
        help="Port du frontend (défaut: 5173)",
    )
    args = parser.parse_args()

    run_backend = args.backend or not args.frontend
    run_frontend = args.frontend or not args.backend

    print("🚀 Vigile — Dev Mode\n")
    
    # Load environment variables
    load_env()
    
    # Ensure database folder exists
    ensure_data_dir()

    # Resolve python binary
    backend_python = None
    if run_backend:
        backend_python = resolve_backend_python()

    # Ensure frontend node modules if needed
    if run_frontend:
        ensure_frontend_dependencies()

    # Port collisions verification & resolution
    if run_backend and is_port_in_use(args.host, int(args.port)):
        if is_our_backend_running(args.host, args.port):
            print(f"📡 Backend Vigile déjà actif sur http://{args.host}:{args.port}.")
            print("Lancement du frontend uniquement...")
            run_backend = False
        else:
            # Try to kill conflicting process
            if not kill_process_on_port(int(args.port)):
                print(f"❌ Erreur: Le port backend {args.port} est déjà utilisé sur {args.host}.")
                print("Libérez le port ou utilisez `--port <port>` pour spécifier un autre port.")
                sys.exit(1)

    if run_frontend and is_port_in_use(args.host, int(args.frontend_port)):
        if not kill_process_on_port(int(args.frontend_port)):
            print(f"❌ Erreur: Le port frontend {args.frontend_port} est déjà utilisé sur {args.host}.")
            print("Libérez le port ou utilisez `--frontend-port <port>` pour spécifier un autre port.")
            sys.exit(1)

    # Start processes
    if run_backend:
        print(f"⚙️   Backend  → http://{args.host}:{args.port}")
        processes.append(start_backend(args.host, args.port, backend_python or sys.executable))

    if run_frontend:
        print(f"🎨  Frontend → http://{args.host}:{args.frontend_port}")
        processes.append(start_frontend(args.host, args.frontend_port, args.host, args.port))

    if run_backend or is_our_backend_running(args.host, args.port):
        print(f"📡 API Docs  → http://{args.host}:{args.port}/api/docs")
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
