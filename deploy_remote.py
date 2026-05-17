#!/usr/bin/env python3
"""部署到阿里云服务器 - podman + DaoCloud镜像"""

import os
import sys
import time
import zipfile
import tempfile
from pathlib import Path

import paramiko
from scp import SCPClient

ROOT = Path(__file__).resolve().parent

SERVER = "8.130.149.29"
USER = "root"
PASSWORD = "Neuzk1990513"
REMOTE_PATH = "/opt/cc_stock"

MIRROR = "docker.m.daocloud.io"

IMAGES = [
    f"{MIRROR}/library/postgres:16-alpine",
    f"{MIRROR}/library/python:3.12-slim",
    f"{MIRROR}/library/nginx:alpine",
]

EXCLUDES = {
    "node_modules", ".git", "__pycache__", ".pytest_cache",
    ".env.dev", "stock.db", "test_stock.db",
    "log", "venv", ".venv", "env", "frontend/node_modules",
}


def run(ssh, cmd, timeout=300):
    """Run a command on remote, print output."""
    print(f"  > {cmd[:130]}{'...' if len(cmd) > 130 else ''}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode()
    err = stderr.read().decode()
    for line in out.strip().split('\n')[-20:]:
        if line.strip():
            print(f"    {line}")
    for line in err.strip().split('\n')[-5:]:
        if line.strip():
            print(f"    [ERR] {line}")
    return out, err


def package_project() -> Path:
    print("[3/7] 打包项目文件...")
    include_dirs = ["backend", "frontend/dist"]
    include_files = ["Dockerfile.backend", ".env.prod", "requirements.txt"]

    archive_path = Path(tempfile.gettempdir()) / "cc_stock_deploy.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in include_dirs:
            src_dir = ROOT / d
            if not src_dir.exists():
                continue
            for f in src_dir.rglob("*"):
                if f.is_dir():
                    continue
                parts = set(f.relative_to(src_dir).parts)
                if parts & EXCLUDES:
                    continue
                if f.suffix in (".pyc",) or f.name.startswith("."):
                    continue
                arcname = str(f.relative_to(ROOT))
                zf.write(f, arcname)
        for fname in include_files:
            fpath = ROOT / fname
            if fpath.exists():
                zf.write(fpath, fname)

    size_mb = archive_path.stat().st_size / (1024 * 1024)
    print(f"  打包完成: {size_mb:.1f} MB")
    return archive_path


def deploy():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print(f"[1/7] 连接 {USER}@{SERVER}...")
        ssh.connect(SERVER, username=USER, password=PASSWORD, look_for_keys=False, timeout=15)
        print("  OK")

        # Step 2: Pull images from DaoCloud mirror (slowest step, do first)
        print("[2/7] 拉取容器镜像 (通过 DaoCloud)...")
        for image in IMAGES:
            docker_name = image.replace(f"{MIRROR}/library/", "docker.io/library/")
            print(f"  拉取 {image} ...")
            out, err = run(ssh, f"podman pull {image} 2>&1", timeout=300)
            # Tag to standard Docker Hub name
            run(ssh, f"podman tag {image} {docker_name}")

        # Step 3: Clean up old stuff
        print("[3/7] 清理旧容器...")
        run(ssh, "podman pod rm -f cc-stock 2>/dev/null; "
                 "podman rm -f cc-postgres cc-backend cc-frontend 2>/dev/null; true")

        # Step 4: Package and upload
        if not (ROOT / "frontend" / "dist").exists():
            print("错误: frontend/dist 不存在")
            sys.exit(1)

        archive = package_project()
        remote_zip = f"{REMOTE_PATH}/deploy.zip"

        print(f"[4/7] 上传项目 ({archive.stat().st_size / 1024 / 1024:.1f} MB)...")
        run(ssh, f"mkdir -p {REMOTE_PATH}")
        with SCPClient(ssh.get_transport()) as scp:
            scp.put(str(archive), remote_zip)
        print("  上传完成")

        # Step 5: Extract
        print("[5/7] 解压...")
        run(ssh, f"cd {REMOTE_PATH} && unzip -o deploy.zip && rm deploy.zip")

        # nginx config for podman (localhost because pod shares network)
        run(ssh, f"""cat > {REMOTE_PATH}/nginx_pod.conf << 'EOF'
server {{
    listen 80;
    server_name _;

    location /api/ {{
        proxy_pass http://localhost:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }}

    location / {{
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }}
}}
EOF""")

        # Step 6: Start services
        print("[6/7] 启动服务...")

        print("  创建 Pod...")
        run(ssh, "podman pod create --name cc-stock -p 80:80 -p 8000:8000")

        # PostgreSQL
        print("  启动 PostgreSQL...")
        run(ssh, "podman run -d --pod cc-stock --name cc-postgres "
            "-e POSTGRES_USER=stock "
            "-e POSTGRES_PASSWORD=stock_pwd_2024 "
            "-e POSTGRES_DB=stock_db "
            "-v cc_stock_pgdata:/var/lib/postgresql/data "
            "docker.io/library/postgres:16-alpine")
        print("  等待 PostgreSQL 就绪...")
        time.sleep(5)

        # Backend build
        print("  构建后端镜像...")
        run(ssh, f"cd {REMOTE_PATH} && podman build -t cc-backend -f Dockerfile.backend . 2>&1", timeout=600)

        print("  启动后端...")
        run(ssh, "podman run -d --pod cc-stock --name cc-backend "
            "-e DATABASE_URL=postgresql://stock:stock_pwd_2024@localhost:5432/stock_db "
            "-v cc_stock_data:/app/data "
            "cc-backend")
        time.sleep(3)

        # Frontend (pre-built dist, no build needed on server)
        print("  启动前端 (预构建)...")
        run(ssh, "podman run -d --pod cc-stock --name cc-frontend "
            f"-v {REMOTE_PATH}/frontend/dist:/usr/share/nginx/html:ro "
            f"-v {REMOTE_PATH}/nginx_pod.conf:/etc/nginx/conf.d/default.conf:ro "
            "docker.io/library/nginx:alpine")

        # Step 7: Verify
        print("[7/7] 验证...")
        time.sleep(3)
        run(ssh, "echo '=== Pod ===' && podman pod ps")
        run(ssh, "echo '=== Containers ===' && podman ps --filter pod=cc-stock --format 'table {{.Names}} {{.Status}} {{.Ports}}'")
        run(ssh, "echo '=== Backend Health ===' && curl -s http://localhost:8000/api/health 2>&1 || echo 'NOT READY'")
        run(ssh, "echo '=== Frontend ===' && curl -s -o /dev/null -w 'HTTP %{http_code}' http://localhost:80/ 2>&1")

        archive.unlink(missing_ok=True)

        print("\n" + "=" * 52)
        print(f"  ✓ 部署完成!")
        print(f"  前端: http://{SERVER}")
        print(f"  API:  http://{SERVER}:8000/api/health")
        print(f"  文档: http://{SERVER}:8000/api/docs")
        print("=" * 52)

    finally:
        ssh.close()


if __name__ == "__main__":
    deploy()
