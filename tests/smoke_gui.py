"""Manual/on-device GUI smoke test. Requires Qt WebEngine and a graphical session."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from javan.storage import CatalogStore
from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtWidgets import QApplication
from javan.theme import STYLE, configure_font
from javan.window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    configure_font(app)
    app.setStyleSheet(STYLE)
    temp = TemporaryDirectory()
    window = MainWindow(CatalogStore(Path(temp.name) / 'catalog.json'))
    window.show()
    result = {'success': False}

    def done(ok):
        if not ok:
            print('Home page failed to render')
            app.exit(1)
            return
        try:
            assert window.sidebar.tree.topLevelItemCount() == 4
            window.sidebar.search.setText('رهگیری')
            assert window.sidebar.tree.topLevelItemCount() == 1
            assert window.sidebar.tree.topLevelItem(0).childCount() == 1
            window.sidebar.search.setText('notfound123')
            assert window.sidebar.empty.isVisible()
            window.sidebar.search.clear()
            window.toggle_sidebar()
            assert window.sidebar.isHidden()
            window.toggle_sidebar()
            assert not window.sidebar.isHidden()
            assert window.sidebar.mapTo(window, QPoint(0, 0)).x() > window.browser.mapTo(window, QPoint(0, 0)).x()
            result['success'] = True
            print('GUI smoke passed: home, filter, empty state, collapse and RTL placement')
            app.exit(0)
        except AssertionError:
            print('GUI smoke assertion failed')
            app.exit(1)

    window.browser.loadFinished.connect(done)
    QTimer.singleShot(20000, lambda: app.exit(0 if result['success'] else 1))
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
