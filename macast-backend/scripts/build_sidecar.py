"""Nuitka 构建脚本 - 将 Python Sidecar 编译为独立可执行文件"""

import os
import sys
import platform
import subprocess


def get_target_triple():
    """获取当前平台的 Rust target triple（与 Tauri externalBin 约定一致）"""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        if machine == "arm64":
            return "aarch64-pc-windows-msvc"
        return "x86_64-pc-windows-msvc"
    elif system == "darwin":
        if machine == "arm64":
            return "aarch64-apple-darwin"
        return "x86_64-apple-darwin"
    elif system == "linux":
        if machine == "aarch64":
            return "aarch64-unknown-linux-gnu"
        return "x86_64-unknown-linux-gnu"
    else:
        raise RuntimeError(f"Unsupported platform: {system}")


def build(force=False):
    """构建 Sidecar 为独立可执行文件"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(current_dir)
    target_triple = get_target_triple()

    output_name = f"macast-sidecar-{target_triple}"
    dist_dir = os.path.join(project_dir, "dist")
    entry_point = os.path.join(project_dir, "macast_sidecar", "main.py")
    xml_dir = os.path.join(project_dir, "macast_sidecar", "xml")

    ext = ".exe" if sys.platform == "win32" else ""
    output_path = os.path.join(dist_dir, f"{output_name}{ext}")

    # 已存在则跳过（--force 强制重建）
    if not force and os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"Sidecar binary already exists: {output_path} ({size_mb:.1f} MB)")
        print("Use --force to rebuild")
        return

    os.makedirs(dist_dir, exist_ok=True)

    args = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",
        f"--output-filename={output_name}",
        f"--output-dir={dist_dir}",
        f"--include-data-dir={xml_dir}=macast_sidecar/xml",
        "--include-package=macast_sidecar",
        "--include-package=lxml",
        "--include-package=netifaces",
        "--nofollow-import-to=tkinter,unittest,test,distutils,setuptools,pip,_pytest,pytest",
        "--enable-plugin=anti-bloat",
        "--no-progress",
        "--assume-yes-for-downloads",
        entry_point,
    ]

    print(f"Building sidecar with Nuitka: {output_name}")
    print(f"Entry point: {entry_point}")
    print(f"Output dir:  {dist_dir}")
    print(f"Target:      {target_triple}")
    print()

    result = subprocess.run(args, cwd=project_dir)
    if result.returncode != 0:
        print(f"\nBuild failed with exit code {result.returncode}")
        sys.exit(1)

    if os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"\nBuild completed: {output_path} ({size_mb:.1f} MB)")
    else:
        print(f"\nWarning: Expected output not found at {output_path}")
        if os.path.exists(dist_dir):
            files = os.listdir(dist_dir)
            print(f"Files in {dist_dir}: {files}")


if __name__ == "__main__":
    force = "--force" in sys.argv
    build(force=force)
