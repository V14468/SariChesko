"""Regenerate the SariChesko icon assets.

    python scripts/generate_icon.py

Writes packaging/assets/sarichesko.ico (used by the Windows PyInstaller build)
and packaging/assets/sarichesko.png (256 px, used by the Linux .desktop entry).
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QGuiApplication  # noqa: E402

from sarichesko.ui.icon import build_ico, render_icon_image  # noqa: E402


def main():
    app = QGuiApplication([])  # noqa: F841
    out = ROOT / "packaging" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    (out / "sarichesko.ico").write_bytes(build_ico())
    render_icon_image(256).save(str(out / "sarichesko.png"), "PNG")
    print(f"Wrote {out / 'sarichesko.ico'} and {out / 'sarichesko.png'}")


if __name__ == "__main__":
    main()