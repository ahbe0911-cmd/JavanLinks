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
    from hashlib import sha256
    from PySide6.QtCore import QCoreApplication, QEvent
    app = QApplication(['JavanLinks accounting probe'])
    folder = Path(folder).resolve()
    page_path = prepare_accounting(folder)
    if mode == 'seed':
        legacy_key = sha256(str(page_path.parent.resolve()).encode('utf-8')).hexdigest()[:32]
        (folder / 'local-profiles' / legacy_key / 'storage').mkdir(parents=True, exist_ok=True)
    sessions = BrowserSessions(folder, lambda request: request.cancel())
    view = BrowserView(sessions, page_path.parent)
    view.page().accounting_path = page_path.resolve()
    if mode != 'seed':
        attach_accounting_bridge(view, folder / 'accounting-data')
    view.resize(1100, 720)
    view.show()
    submitted = False
    poll = QTimer()
    poll.setInterval(250)

    def inspect(result):
        nonlocal submitted
        if not isinstance(result, dict):
            return
        ready, count = result.get('ready'), result.get('count')
        if ready == 'readonly':
            app.exit(6)
            return
        if ready != 'ready':
            return
        if mode == 'write' and not submitted:
            if count != 1:
                app.exit(10)
                return
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
            if count != 2 or not data or not data['services'] or len(data['invoices']) != 2:
                return
            by_name = {i.get('customerName'): i for i in data['invoices']}
            if by_name.get('CI-persistence-probe', {}).get('finalToman') != 12345 or by_name.get('CI-legacy-seed', {}).get('finalToman') != 500:
                app.exit(8)
                return
            if not list((folder / 'accounting-data' / 'backups').glob('legacy-*.json')):
                app.exit(11)
                return
        except Exception:
            app.exit(9)
            return
        poll.stop()
        app.exit(0)

    def seed_loaded(ok):
        if not ok:
            app.exit(5)
            return
        script = """
(() => {
  const invoice = {id:'legacy-ci-1',invoiceNumber:'1001',date:'1405/09/01',
    customerName:'CI-legacy-seed',customerPhone:'',paymentStatus:'پرداخت شده',
    items:[{name:'legacy service',price:500,qty:1}],discountType:'amount',
    discountValue:0,subtotal:500,discountAmount:0,finalToman:500,finalRial:5000};
  localStorage.setItem('javan_acc_invoices_v2', JSON.stringify([invoice]));
  localStorage.setItem('javan_acc_next_num_v2','1002');
  return localStorage.getItem('javan_acc_invoices_v2') !== null;
})()
"""
        def seeded(saved):
            if not saved:
                app.exit(12)
            else:
                QTimer.singleShot(2000, lambda: app.exit(0))
        view.page().runJavaScript(script, seeded)

    poll.timeout.connect(lambda: view.page().runJavaScript(
        "({ready:document.documentElement.dataset.ledgerReady || '',count:Number(document.querySelector('#header-history-count').textContent)})", inspect))
    if mode == 'seed':
        view.loadFinished.connect(seed_loaded)
    else:
        view.loadFinished.connect(lambda ok: poll.start() if ok else app.exit(5))
    QTimer.singleShot(60000, lambda: app.exit(7))
    view.open_local(str(page_path))
    code = app.exec()
    poll.stop()
    view.close()
    view.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return code
