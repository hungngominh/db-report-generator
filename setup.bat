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
pip install -r "%~dp0.agents\skills\db-report-generator\requirements.txt" >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong the cai dat packages. Thu chay: pip install -r .agents\skills\db-report-generator\requirements.txt
    pause
    exit /b 1
)
echo [OK] psycopg2-binary, pglast, jsonschema da cai dat

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
if not exist "%WORKSPACE%\.agents\skills\db-report-generator\references" mkdir "%WORKSPACE%\.agents\skills\db-report-generator\references"

:: Copy agent skill (SKILL.md, CLAUDE.md, MIGRATION.md, scripts/, references/, assets/templates/)
xcopy /s /y /q "%~dp0.agents\skills\db-report-generator\*" "%WORKSPACE%\.agents\skills\db-report-generator\" >nul
echo [OK] Agent skill (scripts + references + assets/templates, bao gom KB tai references\kb\)

:: Setup Claude Code skill discovery junction (.claude/skills -> .agents/skills)
:: Can thiet de lenh /db-report-generator hoat dong trong Claude Code CLI
if not exist "%WORKSPACE%\.claude\skills" mkdir "%WORKSPACE%\.claude\skills"
if exist "%WORKSPACE%\.claude\skills\db-report-generator" rmdir "%WORKSPACE%\.claude\skills\db-report-generator" >nul 2>&1
mklink /J "%WORKSPACE%\.claude\skills\db-report-generator" "%WORKSPACE%\.agents\skills\db-report-generator" >nul
if errorlevel 1 (
    echo [CANH BAO] Khong the tao junction .claude\skills - lenh /db-report-generator co the khong nhan duoc skill nay
) else (
    echo [OK] Claude Code skill discovery junction da duoc tao
)

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
echo      cd %WORKSPACE%\.agents\skills\db-report-generator
echo      set PYTHONIOENCODING=utf-8
echo      python -m scripts.run_report [duong-dan-toi-.env] [thu-muc-ket-qua]
echo.
echo   3. Hoac dung Claude Code (tao ca Code/Combined/Solutions report):
echo      /db-report-generator
echo.
pause
