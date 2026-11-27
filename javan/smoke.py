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
    """Register an actual invoice and verify it from an independent process."""
    from .accounting import prepare_accounting
    from .browser import BrowserSessions, BrowserView
    from .bridge import attach_accounting_bridge
    from .ledger_snapshot import LedgerSnapshot
    from PySide6.QtCore import QCoreApplication, QEvent
    app = QApplication(['JavanLinks accounting probe'])
    folder = Path(folder).resolve()
    page_path = prepare_accounting(folder)
    sessions = BrowserSessions(folder, lambda request: request.cancel())
    view = BrowserView(sessions, page_path.parent)
    view.page().accounting_path = page_path.resolve()
    attach_accounting_bridge(view, folder / 'accounting-data')
    view.resize(1100, 720)
    view.show()
    submitted = False
    poll = QTimer()
    poll.setInterval(250)

    def inspect(result):
        nonlocal submitted
        if result == 'readonly':
            app.exit(6)
            return
        if result != 'ready':
            return
        if mode == 'write' and not submitted:
            submitted = True
            view.page().runJavaScript("""
(() => {
  document.querySelector('#btn-add-custom-item').click();
  const price = document.querySelector('[data-inv-edit="price"]');
  price.value = '12345';
  price.dispatchEvent(new Event('input', {bubbles: true}));
  const customer = document.querySelector('#inv-customer');
  customer.value = 'CI-persistence-probe';
  customer.dispatchEvent(new Event('input', {bubbles: true}));
  document.querySelector('#btn-save-invoice').click();
})()
""")
            return
        try:
            data = LedgerSnapshot(folder / 'accounting-data').load()['data']
            if not data or not data['services'] or len(data['invoices']) != 1:
                return
            invoice = data['invoices'][0]
            if invoice.get('customerName') != 'CI-persistence-probe' or invoice.get('finalToman') != 12345:
                app.exit(8)
                return
        except Exception:
            app.exit(9)
            return
        poll.stop()
        app.exit(0)

    poll.timeout.connect(lambda: view.page().runJavaScript("document.documentElement.dataset.ledgerReady || ''", inspect))
    view.loadFinished.connect(lambda ok: poll.start() if ok else app.exit(5))
    QTimer.singleShot(60000, lambda: app.exit(7))
    view.open_local(str(page_path))
    code = app.exec()
    poll.stop()
    view.close()
    view.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return code
