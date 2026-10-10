"""SariChesko application icon.

The icon is drawn in code on a 256x256 design grid and rendered *natively* at
every size the OS may ask for (taskbar, title bar, Alt-Tab, installer, high-DPI
scaling). The previous version drew a single 64x64 bitmap and let the OS
stretch it to 16/32/48/256 px, which is what made it look soft and blurry.

Small sizes use a simplified mark (thicker outline, bigger centre dot, no
spokes) because fine detail turns to mush below ~40 px.
"""
import math
import struct

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)

# Sizes Qt/Windows pick from. 20/40 cover 125% display scaling for 16/32 px slots.
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
# Sizes embedded in the .ico used for the Windows executable.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

_CYAN = (0, 240, 255)
_GRID = 256.0


def _hexagon(cx: float, cy: float, r: float) -> QPainterPath:
    path = QPainterPath()
    for i in range(6):
        a = math.radians(60 * i - 30)
        pt = QPointF(cx + r * math.cos(a), cy + r * math.sin(a))
        if i == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    path.closeSubpath()
    return path


def render_icon_image(size: int) -> QImage:
    """Render the icon at exactly `size` x `size` pixels (ARGB, transparent corners)."""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    scale = size / _GRID
    p.scale(scale, scale)

    cx = cy = _GRID / 2
    cyan = QColor(*_CYAN)
    small = size <= 32       # simplified mark
    detailed = size >= 48    # spokes + outer nodes

    # Dark rounded tile: gives the mark a defined edge on light AND dark taskbars.
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(6, 6, _GRID - 12, _GRID - 12), 56, 56)
    grad = QLinearGradient(0, 0, 0, _GRID)
    grad.setColorAt(0.0, QColor(12, 28, 38))
    grad.setColorAt(1.0, QColor(4, 9, 14))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawPath(tile)
    if detailed:
        p.setPen(QPen(QColor(0, 240, 255, 70), 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(tile)

    # Hexagon: keep the stroke at least ~1.6 device pixels wide at tiny sizes.
    stroke = max(9.0, 1.7 / scale)
    hex_r = 100.0
    p.setPen(QPen(cyan, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                  Qt.PenJoinStyle.RoundJoin))
    p.setBrush(QColor(0, 240, 255, 46))
    p.drawPath(_hexagon(cx, cy, hex_r))

    # Centre node
    dot_r = 34.0 if small else 22.0
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(cyan)
    p.drawEllipse(QPointF(cx, cy), dot_r, dot_r)

    # Spokes and outer nodes (only where they stay legible)
    if detailed:
        inner_r = 58.0
        spoke_pen = QPen(QColor(0, 240, 255, 150), 5.0, Qt.PenStyle.SolidLine,
                         Qt.PenCapStyle.RoundCap)
        for i in range(6):
            a = math.radians(60 * i - 30)
            ix, iy = cx + inner_r * math.cos(a), cy + inner_r * math.sin(a)
            p.setPen(spoke_pen)
            p.drawLine(QPointF(cx, cy), QPointF(ix, iy))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(cyan)
            p.drawEllipse(QPointF(ix, iy), 9.0, 9.0)

    p.end()
    return img


def create_app_icon() -> QIcon:
    """Multi-resolution QIcon (needs a QGuiApplication to exist)."""
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(QPixmap.fromImage(render_icon_image(size)))
    return icon


def _png_bytes(image: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    buf.close()
    return bytes(ba.data())


def build_ico(sizes=ICO_SIZES) -> bytes:
    """Build a multi-size Windows .ico (PNG-compressed entries, valid on Vista+)."""
    pngs = [(s, _png_bytes(render_icon_image(s))) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries, blobs = b"", b""
    for size, data in pngs:
        dim = 0 if size >= 256 else size  # 0 means 256 in the ICO format
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    return header + entries + blobs