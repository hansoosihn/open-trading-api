#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
간단한 PyInstaller 빌드 (최소 옵션)
"""

import subprocess
import sys
from pathlib import Path

def build_simple_exe():
    """간단한 exe 빌드"""
    project_root = Path(__file__).resolve().parent.parent
    app_file = project_root / "home_trading_system" / "dashboard_app.py"
    output_dir = project_root / "dist"
    
    # 더 간단한 PyInstaller 커맨드
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=AutoStockDashboard",
        "--onefile",
        "--windowed",
        "--collect-all", "PyQt5",
        f"--distpath={output_dir}",
        "-y",
        str(app_file)
    ]
    
    print("AutoStock 대시보드 EXE 생성 중...")
    print(f"출력: {output_dir / 'AutoStockDashboard.exe'}\n")
    
    result = subprocess.run(cmd, cwd=str(project_root))
    
    if result.returncode == 0:
        exe_path = output_dir / "AutoStockDashboard.exe"
        print("\n" + "="*60)
        print("✅ 성공!")
        print("="*60)
        print(f"실행 파일: {exe_path}")
        print(f"\n다음 명령으로 실행: {exe_path}")
    else:
        print(f"❌ 빌드 실패")
        sys.exit(1)

if __name__ == "__main__":
    build_simple_exe()
