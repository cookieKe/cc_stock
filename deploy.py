#!/usr/bin/env python3
"""A股股票推荐系统 - 一键部署脚本 (跨平台)

Usage:
    python deploy.py --server 1.2.3.4
    python deploy.py --server 1.2.3.4 --user root --path /opt/cc_stock
    python deploy.py --server 1.2.3.4 --dry-run
"""

import argparse
import subprocess
import zipfile
import tempfile
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

EXCLUDES = {
    "node_modules", ".git", "__pycache__", ".pytest_cache",
    "*.pyc", ".env.dev", "stock.db", "test_stock.db",
    "log", "venv", ".venv", "env",
}


def build_frontend():
    """Build frontend static files."""
    frontend_dir = ROOT / "frontend"
    print("[1/5] 构建前端...")
    subprocess.run(
        ["npm", "install", "--silent"],
        cwd=frontend_dir, check=True,
        shell=(sys.platform == "win32"),
    )
    subprocess.run(
        ["npm", "run", "build"],
        cwd=frontend_dir, check=True,
        shell=(sys.platform == "win32"),
    )
    print("  前端构建完成")


def package_project() -> Path:
    """Package necessary files into a zip archive."""
    print("[2/5] 打包项目文件...")

    include_dirs = ["backend", "frontend/dist"]
    include_files = [
        "Dockerfile.backend", "Dockerfile.frontend",
        "docker-compose.yml", "nginx.conf",
        ".env.prod", "requirements.txt",
    ]

    archive_path = Path(tempfile.gettempdir()) / "cc_stock_deploy.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add directory contents
        for d in include_dirs:
            src_dir = ROOT / d
            if not src_dir.exists():
                continue
            for f in src_dir.rglob("*"):
                if f.is_dir():
                    continue
                # Skip excluded patterns
                parts = set(f.relative_to(src_dir).parts)
                if parts & EXCLUDES:
                    continue
                if f.suffix == ".pyc" or f.name.startswith("."):
                    continue
                arcname = str(f.relative_to(ROOT))
                zf.write(f, arcname)

        # Add individual files
        for fname in include_files:
            fpath = ROOT / fname
            if fpath.exists():
                zf.write(fpath, fname)

    size_mb = archive_path.stat().st_size / (1024 * 1024)
    print(f"  打包完成: {archive_path} ({size_mb:.1f} MB)")
    return archive_path


def deploy(server: str, user: str, remote_path: str, dry_run: bool):
    """Upload and deploy to remote server."""
    archive = package_project()
    remote_zip = f"{remote_path}/deploy.zip"

    # Step 3: Upload
    print(f"[3/5] 上传到 {user}@{server}...")
    if not dry_run:
        subprocess.run(
            ["ssh", f"{user}@{server}", f"mkdir -p {remote_path}"],
            check=True,
        )
        subprocess.run(
            ["scp", str(archive), f"{user}@{server}:{remote_zip}"],
            check=True,
        )
    else:
        print(f"  [DRY-RUN] scp {archive} {user}@{server}:{remote_zip}")
    print("  上传完成")

    # Step 4: Extract on server
    print("[4/5] 服务器解压...")
    extract_cmd = (
        f"cd {remote_path} && "
        f"unzip -o deploy.zip && "
        f"rm deploy.zip"
    )
    if not dry_run:
        subprocess.run(
            ["ssh", f"{user}@{server}", extract_cmd],
            check=True,
        )
    else:
        print(f"  [DRY-RUN] ssh {user}@{server} '{extract_cmd}'")
    print("  解压完成")

    # Step 5: Docker compose
    print("[5/5] Docker构建并启动...")
    docker_cmd = (
        f"cd {remote_path} && "
        f"docker compose down && "
        f"docker compose up -d --build"
    )
    if not dry_run:
        subprocess.run(
            ["ssh", f"{user}@{server}", docker_cmd],
            check=True,
        )
    else:
        print(f"  [DRY-RUN] ssh {user}@{server} '{docker_cmd}'")
    print("  部署完成!")

    # Cleanup
    archive.unlink(missing_ok=True)

    print("=" * 52)
    print(f"  访问地址: http://{server}")
    print(f"  API文档:  http://{server}/api/docs")
    print("=" * 52)


def main():
    parser = argparse.ArgumentParser(
        description="A股股票推荐系统 - 一键部署到云服务器"
    )
    parser.add_argument(
        "--server", "-s", required=True,
        help="云服务器 IP 或域名",
    )
    parser.add_argument(
        "--user", "-u", default="root",
        help="SSH 用户名 (默认: root)",
    )
    parser.add_argument(
        "--path", "-p", default="/opt/cc_stock",
        help="服务器上的部署路径 (默认: /opt/cc_stock)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅显示将执行的操作，不实际上传和部署",
    )
    parser.add_argument(
        "--skip-build", action="store_true",
        help="跳过前端构建（使用已有的 dist 目录）",
    )
    args = parser.parse_args()

    if not args.skip_build:
        build_frontend()

    deploy(
        server=args.server,
        user=args.user,
        remote_path=args.path,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
