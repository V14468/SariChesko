import struct

import pytest

from sarichesko.ui.icon import ICON_SIZES, ICO_SIZES, build_ico, create_app_icon, render_icon_image


@pytest.fixture(scope="module", autouse=True)
def _qt_app():
    # QPixmap (used by create_app_icon) requires a Qt application object.
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


@pytest.mark.parametrize("size", ICON_SIZES)
def test_icon_is_rendered_natively_at_every_size(size):
    img = render_icon_image(size)
    assert (img.width(), img.height()) == (size, size)
    assert img.pixelColor(size // 2, size // 2).alpha() == 255   # centre node is solid
    assert img.pixelColor(0, 0).alpha() == 0                     # corners stay transparent


def test_qicon_offers_all_sizes():
    icon = create_app_icon()
    available = {s.width() for s in icon.availableSizes()}
    assert set(ICON_SIZES) <= available


def test_ico_container_is_well_formed():
    data = build_ico()
    reserved, kind, count = struct.unpack_from("<HHH", data, 0)
    assert (reserved, kind, count) == (0, 1, len(ICO_SIZES))
    for i in range(count):
        w, h, _c, _r, planes, bpp, length, offset = struct.unpack_from("<BBBBHHII", data, 6 + 16 * i)
        assert (planes, bpp) == (1, 32)
        assert w == h == (ICO_SIZES[i] if ICO_SIZES[i] < 256 else 0)   # 0 encodes 256
        assert data[offset:offset + 8] == b"\x89PNG\r\n\x1a\n"          # PNG-compressed entry
        assert offset + length <= len(data)


