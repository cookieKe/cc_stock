"""一键启动开发环境：后端 FastAPI + 前端 Vite

Usage:
    python start_dev.py          # 启动
    Ctrl+C                       # 停止所有

服务地址:
    后端 API  → http://localhost:8080
    API 文档  → http://localhost:8080/docs
    前端页面  → http://localhost:3000
"""

import subprocess
import signal
import sys
import time
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND = os.path.join(ROOT, "frontend")
IS_WIN = sys.platform == "win32"

_NPM = "npm.cmd" if IS_WIN else "npm"

backend_cmd = [
    sys.executable, "-m", "uvicorn", "backend.main:app",
    "--host", "0.0.0.0", "--port", "8080", "--reload",
]

frontend_cmd = [_NPM, "run", "dev"]

procs = []
_stopping = False


def cleanup():
    global _stopping
    if _stopping:
        return
    _stopping = True
    print("\nShutting down...")
    for p in procs:
        if p.poll() is None:
            if IS_WIN:
                p.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
    print("All services stopped.")


def _signal_handler(signum, frame):
    cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT, _signal_handler)
if hasattr(signal, "SIGBREAK"):
    signal.signal(signal.SIGBREAK, _signal_handler)

try:
    print("=" * 50)
    print("  A-Stock Recommendation System")
    print("=" * 50)

    flags = {}
    if IS_WIN:
        flags["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    procs.append(subprocess.Popen(
        backend_cmd, cwd=ROOT, **flags,
    ))
    print("[backend]  Starting FastAPI on http://localhost:8080 ...")

    procs.append(subprocess.Popen(
        frontend_cmd, cwd=FRONTEND, **flags,
    ))
    print("[frontend] Starting Vite on http://localhost:3000 ...")

    time.sleep(3)

    for p in procs:
        if p.poll() is not None:
            print(f"\nERROR: A service failed to start (exit code {p.returncode}).")
            cleanup()
            sys.exit(1)

    print()
    print("  Backend   → http://localhost:8080")
    print("  API Docs  → http://localhost:8080/docs")
    print("  Frontend  → http://localhost:3000")
    print()
    print("  Press Ctrl+C to stop all services.")
    print()

    for p in procs:
        p.wait()

except KeyboardInterrupt:
    cleanup()
