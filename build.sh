#!/bin/bash
# Script to build Claude-Halo binary on macOS and Linux

# Exit on error
set -e

echo "Starting build process for macOS/Linux..."

# Check if uv is installed
if ! command -v uv &> /dev/null
then
    echo "Error: uv could not be found. Please install it first."
    echo "You can install it via: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "Setting up virtual environment..."
if [ ! -d ".venv" ]; then
    uv venv
fi
source .venv/bin/activate

echo "Installing project dependencies and PyInstaller..."
uv pip install -e .
uv pip install pyinstaller pillow

echo "Converting PNG logo..."
ICON_ARG=""
if [ -f "img/ClaudeHalo.png" ]; then
    if [ "$(uname)" == "Darwin" ]; then
        python -c "from PIL import Image; Image.open('img/ClaudeHalo.png').resize((256, 256)).save('img/ClaudeHalo.icns')"
        ICON_ARG="--icon img/ClaudeHalo.icns"
    else
        python -c "from PIL import Image; Image.open('img/ClaudeHalo.png').resize((256, 256)).save('img/ClaudeHalo.ico', sizes=[(256,256), (128,128), (64,64), (48,48), (32,32), (16,16)])"
        ICON_ARG="--icon img/ClaudeHalo.ico"
    fi
else
    echo "Warning: img/ClaudeHalo.png not found. Executable will not have a custom icon."
fi

echo "Building executable with PyInstaller..."
# --onefile creates a single standalone executable
# --name defines the output binary name
# --collect-all ensures that specific libraries with dynamic imports/assets are properly bundled
# --icon specifies the executable icon
pyinstaller --name "claude-halo" \
    --onefile \
    $ICON_ARG \
    --collect-all textual \
    --collect-all faster_whisper \
    --collect-all ctranslate2 \
    halo/__main__.py

echo "========================================="
echo "Build complete! The binary is located at:"
echo "dist/claude-halo"
echo "========================================="
