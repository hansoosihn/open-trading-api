#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PyInstaller를 사용하여 AutoStock 대시보드를 exe로 패키징
"""

import subprocess
import sys
from pathlib import Path

def build_exe():
    """실행 파일 빌드"""
    # scripts 디렉토리 기준 상위로 올라가서 프로젝트 루트 찾기
    project_root = Path(__file__).resolve().parent.parent
    app_file = project_root / "home_trading_system" / "dashboard_app.py"
    output_dir = project_root / "dist"
    
    # PyInstaller 커맨드
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=AutoStockDashboard",
        "--onefile",  # 단일 exe 파일
        "--windowed",  # 콘솔 창 없음
        "--add-data", f"{project_root / 'examples_user'};examples_user",  # 데이터 파일 추가
        "--collect-all", "PyQt5",  # PyQt5 모두 포함
        "--hidden-import=kis_auth",
        "--hidden-import=examples_user",
        f"--distpath={output_dir}",
        f"--workpath={project_root / 'build'}",
        f"--specpath={project_root}",
        "-y",  # Overwrite existing output files
        str(app_file)
    ]
    
    print("=" * 60)
    print("AutoStock 대시보드 EXE 생성 중...")
    print("=" * 60)
    print(f"파일: {app_file}")
    print(f"출력: {output_dir / 'AutoStockDashboard.exe'}")
    print()
    
    try:
        result = subprocess.run(cmd, cwd=str(project_root))
        
        if result.returncode == 0:
            exe_path = output_dir / "AutoStockDashboard.exe"
            print()
            print("=" * 60)
            print("✅ 성공!")
            print("=" * 60)
            print(f"실행 파일 위치: {exe_path}")
            print(f"\n더블클릭하여 실행하세요: {exe_path}")
            print()
        else:
            print(f"❌ 빌드 실패 (코드: {result.returncode})")
            sys.exit(1)
    
    except Exception as e:
        print(f"❌ 오류: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build_exe()
