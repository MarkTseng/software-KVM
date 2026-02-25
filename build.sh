#!/bin/bash

# Build script for Software KVM
# Usage: 
#   ./build.sh [mac|linux|windows]  - Build for specific platform
#   ./build.sh dmg                    - Create DMG from built app (uses icon)
#   ./build.sh clean                  - Clean build artifacts

ICON_FILE="kvm-icon.icns"

# Generate icon if source PNG exists and icns doesn't
if [ -f "kvm-icon.png" ] && [ ! -f "$ICON_FILE" ]; then
    echo "Generating icon..."
    mkdir -p icon.iconset
    for size in 16 32 64 128 256 512 1024; do
        cp kvm-icon.png "icon.iconset/icon_${size}x${size}.png"
        if [ $size -le 512 ]; then
            cp kvm-icon.png "icon.iconset/icon_${size}x${size}@2x.png"
        fi
    done
    iconutil -c icns icon.iconset -o "$ICON_FILE"
    rm -rf icon.iconset
fi

if [ "$1" = "clean" ]; then
    echo "Cleaning build artifacts..."
    rm -rf build/
    rm -rf dist/
    rm -f *.spec
    rm -f SoftwareKVM.dmg
    rm -rf icon.iconset/
    rm -f kvm-icon.icns
    echo "Clean complete!"
    exit 0
fi

if [ "$1" = "dmg" ]; then
    if [ ! -d "dist/SoftwareKVM.app" ]; then
        echo "Error: dist/SoftwareKVM.app not found. Run './build.sh mac' first."
        exit 1
    fi
    echo "Creating DMG..."
    hdiutil create -volname "SoftwareKVM" -srcfolder dist/SoftwareKVM.app -ov -format UDZO SoftwareKVM.dmg
    echo "DMG created: SoftwareKVM.dmg"
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
echo "Run './build.sh dmg' to create DMG."

# Fix permissions for macOS
if [ "$PLATFORM" = "mac" ] && [ -d "dist/SoftwareKVM.app" ]; then
    xattr -cr dist/SoftwareKVM.app 2>/dev/null || true
    
    # Set app icon
    if [ -f "$ICON_FILE" ]; then
        cp "$ICON_FILE" "dist/SoftwareKVM.app/Contents/Resources/SoftwareKVM.icns"
        /usr/libexec/PlistBuddy -c "Set :CFBundleIconFile SoftwareKVM.icns" dist/SoftwareKVM.app/Contents/Info.plist
    fi
    
    # Re-sign the app with entitlements
    codesign --entitlements entitlements.plist --force --deep --sign - dist/SoftwareKVM.app 2>/dev/null || true
    
    echo "App signed with camera entitlements."
fi

# Reset TCC permissions (run separately)
if [ "$1" = "reset-tcc" ]; then
    tccutil reset Camera 2>/dev/null || true
    echo "TCC permissions reset. Please run the app and grant camera permission."
fi
