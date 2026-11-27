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



def run_accounting_probe(mode, folder):
    """Two independent EXE processes verify stable file:// LocalStorage."""
    from .accounting import prepare_accounting
    from .browser import BrowserSessions, BrowserView
    app = QApplication(['JavanLinks accounting probe'])
    folder = Path(folder).resolve()
    page_path = prepare_accounting(folder)
    sessions = BrowserSessions(folder, lambda request: request.cancel())
    view = BrowserView(sessions, page_path.parent)
    view.resize(1100, 720)
    view.show()
    done = False
    key = 'javan_build_persistence_probe'
    write_script = """
(() => {
  try {
    const services = JSON.parse(localStorage.getItem('javan_acc_services_v2') || '[]');
    if (!Array.isArray(services) || !services.length) return false;
    localStorage.setItem('javan_build_persistence_probe', 'javan-ok-v050');
    return localStorage.getItem('javan_build_persistence_probe') === 'javan-ok-v050';
  } catch (_) { return false; }
})()
"""
    read_script = """
(() => {
  try {
    const services = JSON.parse(localStorage.getItem('javan_acc_services_v2') || '[]');
    return localStorage.getItem('javan_build_persistence_probe') === 'javan-ok-v050' &&
      Array.isArray(services) && services.length > 0 &&
      !!document.querySelector('#header-history-count');
  } catch (_) { return false; }
})()
"""
    def finish(ok):
        nonlocal done
        if done:
            return
        done = True
        if ok:
            # Allow the Chromium storage writer to settle before graceful exit.
            QTimer.singleShot(1500, lambda: app.exit(0))
        else:
            app.exit(6)

    def loaded(ok):
        if not ok:
            finish(False)
            return
        view.page().runJavaScript(write_script if mode == 'write' else read_script, finish)

    view.loadFinished.connect(loaded)
    QTimer.singleShot(60000, lambda: app.exit(7))
    view.open_local(str(page_path))
    code = app.exec()
    view.close()
    # Explicitly dispose the page while its profile still exists.
    view.deleteLater()
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return code
