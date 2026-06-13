@echo off
REM Script to build Claude-Halo executable on Windows

echo Starting build process for Windows...

REM Check if uv is installed
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: uv could not be found. Please install it first.
    echo You can install it via: pip install uv
    exit /b 1
)

echo Setting up virtual environment...
if not exist ".venv" (
    call uv venv
    if %errorlevel% neq 0 exit /b %errorlevel%
)

call .venv\Scripts\activate

echo Installing project dependencies and PyInstaller...
call uv pip install -e .
call uv pip install pyinstaller pillow

echo Converting PNG logo to ICO...
if exist "img\ClaudeHalo.png" (
    call python -c "from PIL import Image; Image.open('img/ClaudeHalo.png').resize((256, 256)).save('img/ClaudeHalo.ico', sizes=[(256,256), (128,128), (64,64), (48,48), (32,32), (16,16)])"
) else (
    echo Warning: img\ClaudeHalo.png not found. Executable will not have a custom icon.
)

echo Building executable with PyInstaller...
REM --onefile creates a single standalone executable
REM --name defines the output binary name
REM --collect-all ensures that specific libraries with dynamic imports/assets are properly bundled
REM --icon specifies the executable icon
set ICON_ARG=
if exist "img\ClaudeHalo.ico" set ICON_ARG=--icon "img\ClaudeHalo.ico"

call pyinstaller --name "claude-halo" ^
    --onefile ^
    %ICON_ARG% ^
    --collect-all textual ^
    --collect-all faster_whisper ^
    --collect-all ctranslate2 ^
    halo\__main__.py

echo =========================================
echo Build complete! The executable is located at:
echo dist\claude-halo.exe
echo =========================================
