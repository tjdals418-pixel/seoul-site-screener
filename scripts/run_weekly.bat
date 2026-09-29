@echo off
chcp 65001 >nul
REM 주간 실행 — Windows 작업 스케줄러용.
REM venv 활성화 → 전체 파이프라인 → 주간 스냅샷 → 공개용 데이터 export, 로그는 data\logs.

setlocal

REM --- Paths -----------------------------------------------------------
set "PROJECT_DIR=%~dp0.."
set "VENV=%PROJECT_DIR%\.venv\Scripts\activate.bat"
set "LOG_DIR=%PROJECT_DIR%\data\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM --- Timestamp for log filename --------------------------------------
REM wmic은 최신 Windows 11에서 제거됨 → PowerShell로 타임스탬프
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"') do set "STAMP=%%I"
set "LOG=%LOG_DIR%\run_%STAMP%.log"

REM --- Run -------------------------------------------------------------
cd /d "%PROJECT_DIR%"
echo === %DATE% %TIME% === > "%LOG%"
call "%VENV%" >> "%LOG%" 2>&1
python -m naver_crawler run >> "%LOG%" 2>&1
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" goto done
python scripts\snapshot.py >> "%LOG%" 2>&1
if errorlevel 1 (set "EXITCODE=1" & goto done)
python scripts\export_public.py >> "%LOG%" 2>&1
if errorlevel 1 set "EXITCODE=1"

:done

echo === done (exit %EXITCODE%) %DATE% %TIME% === >> "%LOG%"
endlocal & exit /b %EXITCODE%
