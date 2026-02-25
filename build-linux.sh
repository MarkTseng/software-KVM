#!/bin/bash

# Build script for Software KVM on Linux
# Creates AppImage for Linux distribution
# 
# Usage:
#   ./build-linux.sh        - Build AppImage
#   ./build-linux.sh clean  - Clean build artifacts

set -e

APP_NAME="SoftwareKVM"

if [ "$1" = "clean" ]; then
    echo "Cleaning build artifacts..."
    rm -rf build/
    rm -rf dist/
    rm -f *.spec
    rm -f *.AppImage
    rm -rf "$APP_NAME.AppDir"
    echo "Clean complete!"
    exit 0
fi

echo "Building Software KVM AppImage for Linux..."

pip install pyinstaller -q

# Build with PyInstaller
rm -rf build/ dist/
pyinstaller --name "$APP_NAME" \
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

# Create AppDir structure
mkdir -p "$APP_NAME.AppDir"
cp -r dist/"$APP_NAME" "$APP_NAME.AppDir/$APP_NAME"

# Create AppRun - use standard AppImage approach
cat > "$APP_NAME.AppDir/AppRun" << 'EOF'
#!/bin/bash
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export APPDIR="${APPDIR:-$THIS_DIR}"
exec "$APPDIR/$APP_NAME" "$@"
EOF
chmod +x "$APP_NAME.AppDir/AppRun"

# Create desktop file
cat > "$APP_NAME.AppDir/$APP_NAME.desktop" << EOF
[Desktop Entry]
Name=SoftwareKVM
Exec=$APP_NAME
Icon=$APP_NAME
Type=Application
Categories=Utility;
EOF

# Copy icon if exists
if [ -f "kvm-icon.png" ]; then
    cp kvm-icon.png "$APP_NAME.AppDir/$APP_NAME.png"
fi

# Download appimagetool if not exists
if [ ! -f "appimagetool" ]; then
    echo "Downloading appimagetool..."
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" -O appimagetool
    chmod +x appimagetool
fi

# Create AppImage
echo "Creating AppImage..."
ARCH=x86_64 ./appimagetool "$APP_NAME.AppDir" "$APP_NAME.AppImage"

echo "Build complete!"
echo "Output: $APP_NAME.AppImage"

# Cleanup AppDir
rm -rf "$APP_NAME.AppDir"
