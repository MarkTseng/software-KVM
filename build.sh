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
    rm -rf build/ dist/
    pyinstaller --name "SoftwareKVM" \
        --onedir \
        --windowed \
        --osx-bundle-identifier "com.softwarekvm.app" \
        --add-data "src:src" \
        --hidden-import=PyQt6 \
        --hidden-import=serial \
        --hidden-import=cv2 \
        --hidden-import=numpy \
        --hidden-import=pynput \
        --collect-all PyQt6 \
        --osx-entitlements-file "entitlements.plist" \
        src/main.py
    
    # Add camera permission to Info.plist
    if [ -d "dist/SoftwareKVM.app" ]; then
        /usr/libexec/PlistBuddy -c "Add :NSCameraUsageDescription string 'SoftwareKVM needs camera access to capture video from the remote PC.'" dist/SoftwareKVM.app/Contents/Info.plist 2>/dev/null || true
    fi
elif [ "$PLATFORM" = "linux" ]; then
    rm -rf build/ dist/
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
    rm -rf build/ dist/
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

echo "Build complete! Output in dist/"

# Fix permissions for macOS
if [ "$PLATFORM" = "mac" ] && [ -d "dist/SoftwareKVM.app" ]; then
    xattr -cr dist/SoftwareKVM.app 2>/dev/null || true
    
    # Re-sign the app with entitlements
    codesign --entitlements entitlements.plist --force --deep --sign - dist/SoftwareKVM.app 2>/dev/null || true
    
    echo "App signed with camera entitlements."
fi

# Reset TCC permissions (run separately)
if [ "$1" = "reset-tcc" ]; then
    tccutil reset Camera 2>/dev/null || true
    echo "TCC permissions reset. Please run the app and grant camera permission."
fi
