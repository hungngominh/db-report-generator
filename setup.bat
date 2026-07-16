@echo off
chcp 65001 >nul 2>&1
set PYTHONIOENCODING=utf-8

echo ============================================
echo   DB Report Generator - Setup
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Python chua duoc cai dat!
    echo Tai Python tai: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python da cai dat

:: Install dependencies
echo.
echo Dang cai dat Python packages...
pip install psycopg2-binary requests >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong the cai dat packages. Thu chay: pip install psycopg2-binary requests
    pause
    exit /b 1
)
echo [OK] psycopg2-binary va requests da cai dat

:: Get target workspace
echo.
set /p WORKSPACE="Nhap duong dan workspace (VD: E:\Skills): "
if "%WORKSPACE%"=="" (
    echo [LOI] Ban chua nhap duong dan!
    pause
    exit /b 1
)

:: Copy files
echo.
echo Dang copy files vao %WORKSPACE%...

:: Create directories
if not exist "%WORKSPACE%\.claude\skills\db-report-generator\references" mkdir "%WORKSPACE%\.claude\skills\db-report-generator\references"
if not exist "%WORKSPACE%\.agents\skills\db-report-generator\references" mkdir "%WORKSPACE%\.agents\skills\db-report-generator\references"
if not exist "%WORKSPACE%\.scripts" mkdir "%WORKSPACE%\.scripts"

:: Copy claude skills
xcopy /s /y /q "%~dp0.claude\skills\db-report-generator\*" "%WORKSPACE%\.claude\skills\db-report-generator\" >nul
echo [OK] Claude skill files

:: Copy agent skills
xcopy /s /y /q "%~dp0.agents\skills\db-report-generator\*" "%WORKSPACE%\.agents\skills\db-report-generator\" >nul
echo [OK] Agent skill instructions (bao gom KB tai references\kb\)

:: Copy scripts
xcopy /s /y /q "%~dp0.scripts\*" "%WORKSPACE%\.scripts\" >nul
echo [OK] Helper scripts

echo.
echo ============================================
echo   CAI DAT HOAN TAT!
echo ============================================
echo.
echo Buoc tiep theo:
echo   1. Tao file .env trong thu muc du an
echo      (Xem mau tai: %~dp0sample-project\.env.sample)
echo.
echo   2. Chay bao cao:
echo      cd %WORKSPACE%\.claude\skills\db-report-generator
echo      set PYTHONIOENCODING=utf-8
echo      python analyzer.py [duong-dan-toi-.env]
echo.
echo   3. Hoac dung Claude Code:
echo      /db-report-generator
echo.
pause
