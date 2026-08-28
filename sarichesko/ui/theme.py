# Pure Pitch Black AMOLED Aesthetic with Neon Cyan & High-Contrast Typography

OLED_BLACK_THEME = """
QMainWindow {
    background-color: #000000;
}
QWidget {
    background-color: #000000;
    color: #ffffff;
    font-family: "Segoe UI", "Inter", -apple-system, sans-serif;
    font-size: 13px;
}
QWidget:focus {
    outline: none;
}
QLabel {
    color: #ffffff;
    background: transparent;
    padding: 2px 0px;
}
QLabel#hero_title {
    font-size: 42px;
    font-weight: 800;
    color: #00f0ff;
    letter-spacing: 1.5px;
    padding-bottom: 4px;
}
QLabel#hero_subtitle {
    font-size: 15px;
    font-weight: 500;
    color: #94a3b8;
    line-height: 1.6;
}
QLabel#sidebar_logo {
    font-size: 22px;
    font-weight: 800;
    color: #00f0ff;
    letter-spacing: 1px;
    padding: 4px 0px;
}
QLabel#sidebar_tagline {
    font-size: 11px;
    font-weight: 600;
    color: #64748b;
    letter-spacing: 0.5px;
    padding-bottom: 8px;
}

/* Sidebar Container */
QFrame#sidebar {
    background-color: #000000;
    border-right: 1px solid #121420;
}

/* Navigation Buttons with High Visibility & Line Heights */
QPushButton#nav_button {
    text-align: left;
    padding: 12px 18px;
    border: none;
    outline: none;
    border-radius: 8px;
    margin: 3px 8px;
    font-size: 13px;
    font-weight: 600;
    color: #94a3b8;
    background-color: transparent;
}
QPushButton#nav_button:focus {
    outline: none;
}
QPushButton#nav_button:hover {
    background-color: #0a0d16;
    color: #00f0ff;
}
QPushButton#nav_button:checked {
    background-color: #0c1424;
    color: #00f0ff;
    font-weight: 700;
    border-left: 4px solid #00f0ff;
}

/* General Buttons */
QPushButton {
    background-color: #080a10;
    color: #ffffff;
    border: 1px solid #1a1d2e;
    outline: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: 600;
    min-height: 20px;
}
QPushButton:focus {
    outline: none;
}
QPushButton:hover {
    background-color: #0e1222;
    border-color: #00f0ff;
    color: #00f0ff;
}
QPushButton:pressed {
    background-color: #00f0ff;
    color: #000000;
}
QPushButton#primary_btn {
    background-color: #00f0ff;
    color: #000000;
    border: none;
    font-weight: 700;
}
QPushButton#primary_btn:hover {
    background-color: #33f3ff;
    color: #000000;
}

/* Glassmorphism / AMOLED Cards */
QFrame#card {
    background-color: #05060a;
    border: 1px solid #121524;
    border-radius: 12px;
    padding: 16px;
}
QFrame#card:hover {
    border-color: #00f0ff;
}
"""

COLOR_AMOLED = "#000000"
COLOR_CYAN = "#00f0ff"
COLOR_EMERALD = "#00e5a3"
COLOR_TEXT_PRIMARY = "#ffffff"
COLOR_TEXT_MUTED = "#94a3b8"