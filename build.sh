#!/usr/bin/env bash
# Build single-file GUI executable (PyInstaller + PySide6).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -d venv ]]; then
  # shellcheck source=/dev/null
  source venv/bin/activate
fi

python3 -m pip install -q -U pip
python3 -m pip install -q -r requirements.txt pyinstaller

OUT_NAME="0xPhantomPortal"
rm -rf build dist "${OUT_NAME}.spec"

mkdir -p build

# Rasterize icon.svg → PNG for PyInstaller --icon (SVG not supported as exe icon)
python3 << 'PY'
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QImage, QPainter

root = Path.cwd()
svg = root / "icon.svg"
if not svg.is_file():
    sys.exit("icon.svg not found in project root")

app = QApplication(sys.argv)
r = QSvgRenderer(str(svg))
if not r.isValid():
    sys.exit("icon.svg could not be loaded")

img = QImage(256, 256, QImage.Format_ARGB32)
img.fill(0)
p = QPainter(img)
r.render(p)
p.end()
out = root / "build" / "app_icon.png"
if not img.save(str(out)):
    sys.exit("failed to write build/app_icon.png")
print("Wrote", out)
PY

# --strip: drop debug symbols from bundled .so on Linux (smaller on disk).
STRIP_FLAG=()
if [[ "$(uname -s)" == Linux ]] && command -v strip >/dev/null 2>&1; then
  STRIP_FLAG=(--strip)
fi

# Add bundled resources
DATA_ARGS=(--add-data "icon.svg:.")
if [[ -d "$ROOT/font" ]]; then
  DATA_ARGS+=(--add-data "font:font")
fi

# Optional UPX
UPX_ARGS=()
if command -v upx >/dev/null 2>&1; then
  UPX_ARGS+=(--upx-dir "$(dirname "$(command -v upx)")")
fi

python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --windowed \
  --name "${OUT_NAME}" \
  --icon "build/app_icon.png" \
  "${DATA_ARGS[@]}" \
  --hidden-import PySide6.QtSvg \
  --optimize 2 \
  "${STRIP_FLAG[@]}" \
  "${UPX_ARGS[@]}" \
  ssh_tunnel_manager.py

DIST_BIN="${ROOT}/dist/${OUT_NAME}"
if command -v upx >/dev/null 2>&1 && [[ -f "$DIST_BIN" ]]; then
  upx --best --lzma "$DIST_BIN" || echo "UPX pass failed (non-fatal)"
fi

echo ""
echo "Done: ${DIST_BIN}"
ls -lh "${DIST_BIN}"