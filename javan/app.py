import sys
from pathlib import Path
from PySide6.QtCore import Qt, QStandardPaths, QLockFile
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from .theme import STYLE, configure_font
from .window import MainWindow
from .manager import warn
from .storage import CatalogStore
from . import __version__


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName('Javan Links')
    app.setApplicationDisplayName('لینک‌های کاربردی کافینت جوان')
    app.setApplicationVersion(__version__)
    app.setOrganizationName('Javan')
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    icon = Path(__file__).resolve().parent.parent / 'assets' / 'javan.ico'
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    configure_font(app)
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    folder = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        warn(None, 'خطا در ایجاد پوشه داده‌ها: ' + str(exc))
        return 1
    lock = QLockFile(str(folder / 'catalog.lock'))
    if not lock.tryLock(0):
        warn(None, 'برنامه در حال اجراست یا پوشه داده‌ها قابل نوشتن نیست.')
        return 1
    try:
        store = CatalogStore(folder / 'catalog.json')
    except (OSError, ValueError, RecursionError) as exc:
        warn(None, 'فایل داده باز نشد و بازنویسی نشده است. فایل catalog.json را بررسی یا از نسخه پشتیبان بازیابی کنید.\n' + str(folder) + '\n' + str(exc))
        return 1
    window = MainWindow(store)
    window.showMaximized()
    code = app.exec()
    window.dispose_views()
    lock.unlock()
    return code
