"""Writes assets/icon.svg, icon.png and icon.ico from the logo in webcam_client.py."""
import sys
from pathlib import Path
from PySide6 import QtGui, QtWidgets
sys.path.insert(0, str(Path(__file__).parent))
import webcam_client as W

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
out = Path(__file__).parent / "assets"
out.mkdir(exist_ok=True)
(out / "icon.svg").write_text(W.LOGO_SVG)
W.svg_pixmap(W.LOGO_SVG, 256, 1.0).save(str(out / "icon.png"))
W.svg_pixmap(W.LOGO_SVG, 256, 1.0).toImage().save(str(out / "icon.ico"))
print("ok", sorted(p.name for p in out.iterdir()))
