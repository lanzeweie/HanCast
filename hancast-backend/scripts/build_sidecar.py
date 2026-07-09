"""Nuitka 构建脚本 - 将 Python Sidecar 编译为 standalone 目录结构"""

import os
import sys
import platform
import subprocess
import shutil
import glob


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
    """
    构建 Sidecar 为 standalone 目录结构（扁平化到 src-tauri/）

    输出到 src-tauri/ 目录，供 Tauri externalBin + resources 使用。

    输出结构:
        src-tauri/
        ├── hancast-sidecar-{triple}.exe   ← 入口（externalBin）
        ├── *.dll / *.pyd / *.so           ← 依赖（resources glob）
        ├── hancast_sidecar/
        │   └── xml/                        ← 运行时数据
        ├── certifi/
        ├── lxml/
        └── charset_normalizer/

    Tauri 配置:
        externalBin: ["hancast-sidecar"]
        resources: ["*.dll", "*.pyd", "*.so", "hancast_sidecar/**/*", ...]
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(current_dir)
    # 直接输出到 src-tauri/（扁平化，与 tauri.conf.json 同级）
    src_tauri_dir = os.path.join(os.path.dirname(project_dir), "src-tauri")
    output_dir = src_tauri_dir
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
        print(f"Sidecar directory already exists: {output_dir} ({size_mb:.1f} MB)")
        print("Use --force to rebuild")
        return

    # 清理旧的 Nuitka 输出（仅删除本项目相关的文件，不删整个 src-tauri/）
    _nuitka_patterns = [
        f"hancast-sidecar-{target_triple}{ext}",
        "python312.dll", "vcruntime140.dll", "vcruntime140_1.dll",
        "libcrypto-3-x64.dll", "libffi-8.dll", "libssl-3-x64.dll",
        "81d243bd2c585b0f4821__mypyc.pyd",
        "hancast_sidecar", "certifi", "lxml", "charset_normalizer",
    ]
    for name in _nuitka_patterns:
        p = os.path.join(output_dir, name)
        if os.path.exists(p):
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
    # 清理所有 .dll 和 .pyd（Nuitka 输出的依赖）
    for f in os.listdir(output_dir):
        if f.endswith((".dll", ".pyd")):
            os.remove(os.path.join(output_dir, f))

    # Nuitka 输出到临时目录
    # 注意：Nuitka 的 --output-filename 只影响文件名，目录名根据入口文件名生成
    # 入口是 main.py，所以输出目录是 main.dist
    nuitka_build_dir = os.path.join(project_dir, "build")
    nuitka_dist_dir = os.path.join(nuitka_build_dir, "main.dist")
    nuitka_dist_data_dir = os.path.join(nuitka_build_dir, "main.dist", "hancast_sidecar")

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
        "--user-package-configuration-file=types.nuitka-package.config.yml",
        "--no-progress",
        "--assume-yes-for-downloads",
        entry_point,
    ]

    print(f"Building sidecar with Nuitka (standalone): {output_name}")
    print(f"Entry point: {entry_point}")
    print(f"Output dir:  {output_dir}")
    print(f"Target:      {target_triple}")
    print()

    result = subprocess.run(args, cwd=project_dir)
    if result.returncode != 0:
        print(f"\nBuild failed with exit code {result.returncode}")
        sys.exit(1)

    # Nuitka standalone 输出到 main.dist 目录
    # 将内容平铺到 src-tauri/（不创建子目录）
    if os.path.exists(nuitka_dist_dir):
        for item in os.listdir(nuitka_dist_dir):
            src = os.path.join(nuitka_dist_dir, item)
            dst = os.path.join(output_dir, item)
            # 目标已存在则先删除
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)
            shutil.move(src, dst)
        # 清理 Nuitka 临时构建目录
        shutil.rmtree(nuitka_build_dir, ignore_errors=True)

        # 删除 Nuitka 打包的 types/ 目录，避免覆盖 Python 内置 types 模块
        # 内置 types 包含 MappingProxyType 等，Nuitka 打包的版本不完整会导致 ImportError
        types_dir = os.path.join(output_dir, "types")
        if os.path.isdir(types_dir):
            shutil.rmtree(types_dir)
            print("Removed types/ directory (conflicts with built-in types module)")
    else:
        print(f"\nWarning: Nuitka output not found at {nuitka_dist_dir}")
        if os.path.exists(nuitka_build_dir):
            print(f"Files in build dir: {os.listdir(nuitka_build_dir)}")
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
    print(f"\nTauri config needed:")
    print(f'  externalBin: ["{output_name}"]')
    print(f'  resources: ["*.dll", "*.pyd", "*.so"]')


if __name__ == "__main__":
    force = "--force" in sys.argv
    build(force=force)
