#!/usr/bin/env python3
"""快速同步本地改动到云服务器 - 增量更新，秒级完成"""

import sys
import time
from pathlib import Path
import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parent
SERVER = "8.130.149.29"
USER = "root"
PASSWORD = "Neuzk1990513"
REMOTE = "/opt/cc_stock"


def run(ssh, cmd, timeout=300):
    print(f"  > {cmd[:120]}{'...' if len(cmd) > 120 else ''}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out.strip():
        for line in out.strip().split('\n')[-15:]:
            print(f"    {line}")
    if err.strip():
        for line in err.strip().split('\n')[-5:]:
            print(f"    [ERR] {line}")
    return out, err


def sync_backend():
    """Upload changed backend files, rebuild image, restart container"""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER, username=USER, password=PASSWORD, look_for_keys=False, timeout=15)

    try:
        with SCPClient(ssh.get_transport()) as scp:
            # Upload requirements.txt (rarely changed but cheap to always sync)
            if (ROOT / "requirements.txt").exists():
                scp.put(str(ROOT / "requirements.txt"), f"{REMOTE}/requirements.txt")

            # Upload entire backend directory
            for f in (ROOT / "backend").rglob("*"):
                if f.is_dir() or f.suffix == ".pyc" or f.name.startswith("."):
                    continue
                if "node_modules" in str(f) or "__pycache__" in str(f):
                    continue
                rel = str(f.relative_to(ROOT)).replace("\\", "/")
                try:
                    scp.put(str(f), f"{REMOTE}/{rel}")
                except Exception as e:
                    print(f"    Skip {rel}: {e}")

        print("  文件上传完成")

        # Rebuild image
        print("  重新构建镜像...")
        run(ssh, f"cd {REMOTE} && podman build -t cc-backend -f Dockerfile.backend . 2>&1", timeout=300)

        # Restart container
        print("  重启后端容器...")
        run(ssh, "podman rm -f cc-backend 2>/dev/null; true")
        run(ssh,
            "podman run -d --pod cc-stock --name cc-backend "
            "-e DATABASE_URL=postgresql://stock:stock_pwd_2024@localhost:5432/stock_db "
            "-v cc_stock_data:/app/data "
            "cc-backend")

        time.sleep(3)
        print("  --- Health check ---")
        run(ssh, "curl -s http://localhost:8000/api/health 2>&1")
        print("  后端同步完成")

    finally:
        ssh.close()


def sync_frontend():
    """Build and upload frontend dist (no container restart needed due to volume mount)"""
    print("[1/2] 构建前端...")
    import subprocess
    subprocess.run(["npm", "run", "build"], cwd=ROOT / "frontend",
                   check=True, shell=(sys.platform == "win32"))

    print("[2/2] 上传前端文件...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER, username=USER, password=PASSWORD, look_for_keys=False, timeout=15)

    try:
        with SCPClient(ssh.get_transport()) as scp:
            dist_dir = ROOT / "frontend" / "dist"
            for f in dist_dir.rglob("*"):
                if f.is_dir():
                    continue
                rel = str(f.relative_to(dist_dir)).replace("\\", "/")
                try:
                    scp.put(str(f), f"{REMOTE}/frontend/dist/{rel}")
                except Exception as e:
                    print(f"    Skip {rel}: {e}")

        # Verify
        run(ssh, "curl -s -o /dev/null -w 'HTTP %{http_code}' http://localhost:80/ 2>&1")
        print("  前端同步完成")

    finally:
        ssh.close()


def sync_all():
    """Full sync: frontend + backend"""
    sync_frontend()
    print()
    sync_backend()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python sync_remote.py [backend|frontend|all]")
        print()
        print("  backend   - 上传后端代码 + 重建镜像 + 重启容器 (~60s)")
        print("  frontend  - 构建前端 + 上传dist + 即时生效 (~15s)")
        print("  all       - 前后端一起更新")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "backend":
        sync_backend()
    elif cmd == "frontend":
        sync_frontend()
    elif cmd == "all":
        sync_all()
    else:
        print(f"Unknown: {cmd}")
        sys.exit(1)
