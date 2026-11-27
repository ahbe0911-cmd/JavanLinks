"""Frozen startup test with disposable data."""
from pathlib import Path
from tempfile import TemporaryDirectory
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication
from .theme import configure_font, STYLE
from .storage import CatalogStore
from .window import MainWindow


def run_smoke():
    app = QApplication(['JavanLinks smoke test'])
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    configure_font(app)
    app.setStyleSheet(STYLE)
    temp = TemporaryDirectory(ignore_cleanup_errors=True)
    window = MainWindow(CatalogStore(Path(temp.name) / 'catalog.json'))
    window.show()
    first = window.browser
    completed = False

    def result(html):
        nonlocal completed
        if completed:
            return
        completed = True
        try:
            if 'کافینت جوان' not in html:
                raise AssertionError('Home HTML not rendered')
            window.sidebar.search.setText('رهگیری')
            if window.sidebar.tree.topLevelItemCount() != 1:
                raise AssertionError('Search failed')
            window.sidebar.search.clear()
            second = window.new_home()
            if second is None or window.tabs.count() != 2:
                raise AssertionError('Tab failed')
            window.zoom(1)
            if round(second.zoomFactor() * 100) != 110 or round(first.zoomFactor() * 100) != 100:
                raise AssertionError('Independent zoom failed')
            window.close_tab(window.tabs.indexOf(second))
            if window.tabs.count() != 1:
                raise AssertionError('Close tab failed')
            app.exit(0)
        except Exception:
            app.exit(2)

    def loaded(ok):
        if not ok:
            app.exit(3)
        else:
            first.page().toHtml(result)

    first.loadFinished.connect(loaded)
    QTimer.singleShot(60000, lambda: app.exit(4))
    return app.exec()
