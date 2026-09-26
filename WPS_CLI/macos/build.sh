#!/bin/bash
# 构建 WPS Backup.app：测试 → 编译 → 组装 bundle → 签名 →（可选）安装到 ~/Applications
#   ./build.sh            构建到 macos/build/
#   ./build.sh --install  构建并安装、启动
# 签名身份：CODESIGN_IDENTITY（默认自动选 "Apple Development"，没有则 ad-hoc "-"）
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
ENGINE_ROOT="$(cd .. && pwd)"
BUILD="$ROOT/build"
APP="$BUILD/WPS Backup.app"
VERSION="1.0.0"
BUILD_NO="$(date +%Y%m%d%H%M)"
TARGET="arm64-apple-macos13"

# Xcode 许可未接受时 xcrun/swift 会报错；回退到 Command Line Tools
if ! xcrun --find swiftc >/dev/null 2>&1 || ! xcrun swiftc --version >/dev/null 2>&1; then
    export DEVELOPER_DIR=/Library/Developer/CommandLineTools
fi
echo "▶ toolchain: ${DEVELOPER_DIR:-$(xcode-select -p)}"
swiftc_() { xcrun swiftc "$@"; }

rm -rf "$BUILD"
mkdir -p "$BUILD/tmp"
CORE=(Sources/WPSBackupCore/*.swift)

echo "▶ Core 单元测试"
swiftc_ -target "$TARGET" -parse-as-library "${CORE[@]}" Tests/Shim/XCTestShim.swift \
    Tests/WPSBackupCoreTests/*.swift -o "$BUILD/tmp/coretests"
"$BUILD/tmp/coretests" | tail -1

echo "▶ 编译 runner / App"
swiftc_ -O -target "$TARGET" "${CORE[@]}" Sources/wps-backup-runner/main.swift -o "$BUILD/tmp/wps-backup-runner"
swiftc_ -O -target "$TARGET" -parse-as-library "${CORE[@]}" Sources/WPSBackup/*.swift -o "$BUILD/tmp/WPSBackup"

echo "▶ 组装 bundle"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BUILD/tmp/WPSBackup" "$BUILD/tmp/wps-backup-runner" "$APP/Contents/MacOS/"
sed -e "s|@ENGINE_ROOT@|$ENGINE_ROOT|" -e "s|@VERSION@|$VERSION|" -e "s|@BUILD@|$BUILD_NO|" \
    Resources/Info.plist > "$APP/Contents/Info.plist"
plutil -lint "$APP/Contents/Info.plist" >/dev/null

IDENTITY="${CODESIGN_IDENTITY:-}"
if [ -z "$IDENTITY" ]; then
    IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null | awk -F'"' '/Apple Development/{print $2; exit}')"
    IDENTITY="${IDENTITY:--}"
fi
echo "▶ 签名: $IDENTITY"
codesign --force --sign "$IDENTITY" --identifier cc.all4world.wpsbackup.runner "$APP/Contents/MacOS/wps-backup-runner"
codesign --force --sign "$IDENTITY" "$APP"
codesign --verify --strict "$APP"
rm -rf "$BUILD/tmp"
echo "✅ $APP"

if [ "${1:-}" = "--install" ]; then
    DEST="$HOME/Applications/WPS Backup.app"
    pkill -x WPSBackup 2>/dev/null || true
    mkdir -p "$HOME/Applications"
    rm -rf "$DEST"
    cp -R "$APP" "$DEST"
    echo "✅ 已安装到 $DEST"
    open "$DEST"
fi
