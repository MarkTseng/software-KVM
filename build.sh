#!/bin/bash

# Build script for Software KVM
# Usage: 
#   ./build.sh [mac|linux|windows]  - Build for specific platform
#   ./build.sh clean                  - Clean build artifacts

if [ "$1" = "clean" ]; then
    echo "Cleaning build artifacts..."
    rm -rf build/
    rm -rf dist/
    rm -f *.spec
    echo "Clean complete!"
    exit 0
fi

PLATFORM=${1:-mac}

echo "Building Software KVM for $PLATFORM..."

pip install pyinstaller -q

if [ "$PLATFORM" = "mac" ]; then
    pyinstaller --name "SoftwareKVM" \
        --onedir \
        --windowed \
        --add-data "src:src" \
        --hidden-import=PyQt6 \
        --hidden-import=serial \
        --hidden-import=cv2 \
        --hidden-import=numpy \
        --hidden-import=pynput \
        --collect-all PyQt6 \
        src/main.py
elif [ "$PLATFORM" = "linux" ]; then
    pyinstaller --name "SoftwareKVM" \
        --onedir \
        --windowed \
        --add-data "src:src" \
        --hidden-import=PyQt6 \
        --hidden-import=serial \
        --hidden-import=cv2 \
        --hidden-import=numpy \
        --hidden-import=pynput \
        --collect-all PyQt6 \
        src/main.py
elif [ "$PLATFORM" = "windows" ]; then
    pyinstaller --name "SoftwareKVM" \
        --onedir \
        --windowed \
        --add-data "src;src" \
        --hidden-import=PyQt6 \
        --hidden-import=serial \
        --hidden-import=cv2 \
        --hidden-import=numpy \
        --hidden-import=pynput \
        --collect-all PyQt6 \
        src/main.py
fi

echo "Build complete! Output in dist/SoftwareKVM"
