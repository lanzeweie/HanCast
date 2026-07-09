"""Nuitka 构建脚本 - 将 Python Sidecar 编译为 standalone 目录结构"""

import os
import sys
import platform
import subprocess
import shutil


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


def copy_icon(src_tauri_dir):
    """复制 HanCast-air.png 图标到 src-tauri/icons/ 目录"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(current_dir)
    png_dir = os.path.join(os.path.dirname(project_dir), "png")
    icon_src = os.path.join(png_dir, "HanCast-air.png")
    icons_dir = os.path.join(src_tauri_dir, "icons")

    if os.path.exists(icon_src):
        os.makedirs(icons_dir, exist_ok=True)
        icon_dst = os.path.join(icons_dir, "icon.png")
        shutil.copy2(icon_src, icon_dst)
        print(f"Copied icon: {icon_src} -> {icon_dst}")

        icon_128_2x_dst = os.path.join(icons_dir, "128x128@2x.png")
        shutil.copy2(icon_src, icon_128_2x_dst)
        print(f"Copied icon: {icon_src} -> {icon_128_2x_dst}")
    else:
        print(f"Warning: Icon not found at {icon_src}")


def build(force=False):
    """
    构建 Sidecar 到 src-tauri/hancast-sidecar/ 子目录

    输出结构:
        src-tauri/hancast-sidecar/
        ├── hancast-sidecar-{triple}.exe   ← 入口（externalBin）
        ├── *.dll / *.pyd / *.so           ← 依赖
        ├── hancast_sidecar/
        │   └── xml/                        ← 运行时数据
        ├── certifi/
        ├── lxml/
        └── charset_normalizer/
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(current_dir)
    src_tauri_dir = os.path.join(os.path.dirname(project_dir), "src-tauri")

    # 输出到子目录（整洁结构）
    output_dir = os.path.join(src_tauri_dir, "hancast-sidecar")
    target_triple = get_target_triple()

    output_name = f"hancast-sidecar-{target_triple}"
    entry_point = os.path.join(project_dir, "hancast_sidecar", "main.py")
    xml_dir = os.path.join(project_dir, "hancast_sidecar", "xml")

    ext = ".exe" if sys.platform == "win32" else ""
    output_exe = os.path.join(output_dir, f"{output_name}{ext}")

    # 已存在则跳过（--force 强制重建）
    if not force and os.path.exists(output_exe):
        size_mb = sum(
            os.path.getsize(os.path.join(dp, f))
            for dp, _, filenames in os.walk(output_dir)
            for f in filenames
        ) / (1024 * 1024)
        print(f"Sidecar already exists: {output_dir} ({size_mb:.1f} MB)")
        print("Use --force to rebuild")
        return

    # 清理旧的构建产物
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Nuitka 输出到临时目录
    nuitka_build_dir = os.path.join(project_dir, "build")
    nuitka_dist_dir = os.path.join(nuitka_build_dir, "main.dist")

    # 查找图标文件（只支持 ICO 格式）
    icon_path = None
    src_tauri_icons = os.path.join(src_tauri_dir, "icons")
    ico_path = os.path.join(src_tauri_icons, "icon.ico")

    if os.path.exists(ico_path):
        icon_path = ico_path

    args = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        f"--output-filename={output_name}",
        f"--output-dir={nuitka_build_dir}",
        f"--include-data-dir={xml_dir}=hancast_sidecar/xml",
        "--include-package=hancast_sidecar",
        "--include-package=lxml",
        "--include-package=netifaces",
        "--nofollow-import-to=tkinter,unittest,test,distutils,setuptools,pip,_pytest,pytest",
        "--enable-plugin=anti-bloat",
        "--no-progress",
        "--assume-yes-for-downloads",
    ]

    # 添加图标参数（仅支持 ICO 格式）
    if icon_path and sys.platform == "win32":
        args.append(f"--windows-icon-from-ico={icon_path}")
        print(f"Using icon: {icon_path}")

    args.append(entry_point)

    print(f"Building sidecar: {output_name}")
    print(f"Entry point: {entry_point}")
    print(f"Output dir:  {output_dir}")
    print(f"Target:      {target_triple}")
    print()

    result = subprocess.run(args, cwd=project_dir)
    if result.returncode != 0:
        print(f"\nBuild failed with exit code {result.returncode}")
        sys.exit(1)

    # 将 Nuitka 输出移动到子目录
    if os.path.exists(nuitka_dist_dir):
        for item in os.listdir(nuitka_dist_dir):
            src = os.path.join(nuitka_dist_dir, item)
            dst = os.path.join(output_dir, item)
            shutil.move(src, dst)

        # 清理 Nuitka 临时构建目录
        shutil.rmtree(nuitka_build_dir, ignore_errors=True)

        # 删除 types/ 目录（避免与 Python 内置模块冲突）
        types_dir = os.path.join(output_dir, "types")
        if os.path.isdir(types_dir):
            shutil.rmtree(types_dir)
            print("Removed types/ directory (conflicts with built-in types module)")
    else:
        print(f"\nWarning: Nuitka output not found at {nuitka_dist_dir}")
        sys.exit(1)

    # 统计输出
    total_size = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, _, filenames in os.walk(output_dir)
        for f in filenames
    ) / (1024 * 1024)
    file_count = sum(
        1 for _, _, filenames in os.walk(output_dir) for _ in filenames
    )

    print(f"\nBuild completed: {output_dir}")
    print(f"Total size: {total_size:.1f} MB ({file_count} files)")

    # 复制图标
    copy_icon(src_tauri_dir)


if __name__ == "__main__":
    force = "--force" in sys.argv
    build(force=force)
