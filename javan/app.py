import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from .theme import STYLE, configure_font
from .window import MainWindow


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName('Javan Links')
    app.setApplicationDisplayName('لینک‌های کاربردی کافینت جوان')
    app.setApplicationVersion('0.1.0')
    app.setOrganizationName('Javan')
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    configure_font(app)
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.showMaximized()
    return app.exec()
