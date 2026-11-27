from pathlib import Path
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent


def configure_font(app: QApplication) -> str:
    # Optional user-supplied font; never required for launching the application.
    font_dir = ROOT / 'assets' / 'fonts'
    families = []
    for path in sorted(font_dir.glob('*.ttf')):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))
    installed = set(QFontDatabase.families()) | set(families)
    family = next((name for name in ('Vazirmatn', 'Vazir', 'Segoe UI', 'Tahoma', 'Noto Sans Arabic') if name in installed), app.font().family())
    font = QFont(family, 10)
    app.setFont(font)
    return family


STYLE = '''
QMainWindow, QWidget#root { background: #edf1f6; color: #18283b; }
QFrame#sidebar { background: #14263c; border: none; }
QFrame#brand { background: #1c344e; border: 1px solid #2c4864; border-radius: 12px; }
QLabel#brandTitle { color: #ffffff; font-size: 17px; font-weight: 700; }
QLabel#brandSub { color: #aabdd0; font-size: 11px; }
QLabel#sectionTitle { color: #aabdd0; font-size: 12px; font-weight: 600; }
QLabel#sidebarHint { color: #aabdd0; font-size: 11px; }
QLabel#empty { color: #d9e7f4; padding: 12px; }
QLineEdit#search { color: #f6f9ff; background: #203851; border: 1px solid #39536b; border-radius: 9px; padding: 10px; selection-background-color: #187c80; }
QLineEdit#search:focus { border: 1px solid #55d2c4; }
QTreeWidget#catalog { background: transparent; color: #e5edf7; border: none; outline: none; padding: 2px; }
QTreeWidget#catalog::item { min-height: 37px; padding: 3px 4px; border-radius: 7px; }
QTreeWidget#catalog::item:hover { background: #253e58; }
QTreeWidget#catalog::item:selected { background: #176c70; color: #ffffff; }
QTreeWidget#catalog::branch { background: transparent; }
QFrame#topbar { background: #ffffff; border: 1px solid #dce4ed; border-radius: 12px; }
QLabel#pageTitle { font-size: 15px; font-weight: 700; color: #18283b; }
QLabel#pageSubtitle { font-size: 11px; color: #52657a; }
QPushButton#menuButton, QPushButton#homeButton { background: #f1f5f9; color: #203851; border: 1px solid #dce4ed; border-radius: 8px; padding: 9px 13px; }
QPushButton#menuButton:hover, QPushButton#homeButton:hover { background: #e0f1ef; border-color: #8bbfba; }
QPushButton#menuButton:focus, QPushButton#homeButton:focus { border: 1px solid #137b77; }
QFrame#browserCard { background: #ffffff; border: 1px solid #dce4ed; border-radius: 12px; }
QFrame#statusCard { background: #ffffff; border: 1px solid #dce4ed; border-radius: 8px; }
QLabel#status { color: #41566b; font-size: 11px; }
QLabel#address { color: #52657a; font-size: 11px; }
QProgressBar { border: none; background: #edf1f6; border-radius: 2px; max-height: 4px; }
QProgressBar::chunk { background: #14968c; border-radius: 2px; }
QScrollBar:vertical { width: 9px; background: transparent; margin: 0; }
QScrollBar::handle:vertical { min-height: 30px; background: #567087; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { color: #18283b; background: #ffffff; border: 1px solid #cbd5e1; padding: 5px; }
'''

STYLE += '''
QPushButton#manageButton { background: #176c70; color: white; border: 1px solid #238d87; border-radius: 9px; padding: 11px 6px; font-weight: 600; }
QPushButton#manageButton:hover { background: #208782; }
QDialog { background: #f8fafc; color: #18283b; }
QDialog QLineEdit, QDialog QComboBox { background: white; color: #18283b; border: 1px solid #cbd5e1; border-radius: 7px; padding: 7px; }
QDialog QPushButton { background: #e6f1f0; color: #164e50; border: 1px solid #b5d5d2; border-radius: 7px; padding: 8px 12px; }
QDialog QPushButton:hover { background: #cde8e4; }
QLabel#managerHeading { font-weight: 700; font-size: 16px; color: #14263c; padding: 8px 0; }
QTableWidget { background: white; alternate-background-color: #f1f5f9; color: #18283b; gridline-color: #e2e8f0; selection-background-color: #176c70; selection-color: white; }
QHeaderView::section { background: #e2e8f0; color: #18283b; padding: 8px; border: none; font-weight: 600; }
'''
