"""PyInstaller 打包脚本"""

import os
import sys
import PyInstaller.__main__

def build():
    """构建 Sidecar"""
    # 获取当前目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(current_dir)

    # 构建参数
    args = [
        os.path.join(project_dir, "macast_sidecar", "main.py"),
        "--name", "macast-sidecar",
        "--onefile",
        "--console",
        "--add-data", f"{os.path.join(project_dir, 'macast_sidecar', 'xml')}:macast_sidecar/xml",
        "--hidden-import", "lxml",
        "--hidden-import", "netifaces",
        "--hidden-import", "requests",
        "--distpath", os.path.join(project_dir, "dist"),
        "--workpath", os.path.join(project_dir, "build"),
        "--specpath", project_dir,
    ]

    # Windows 特殊处理
    if sys.platform == 'win32':
        args.append("--console")

    print(f"Building sidecar with args: {args}")
    PyInstaller.__main__.run(args)
    print("Build completed!")

if __name__ == "__main__":
    build()
