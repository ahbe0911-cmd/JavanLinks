"""Narrow QWebChannel API installed only on the built-in accounting page."""
import json
import sqlite3
from PySide6.QtCore import QObject, Slot
from PySide6.QtWebChannel import QWebChannel
from .ledger_snapshot import LedgerSnapshot, LedgerError


class AccountingBridge(QObject):
    def __init__(self, folder, page):
        super().__init__(page)
        self.ledger = LedgerSnapshot(folder)

    def _response(self, operation):
        try:
            return json.dumps({'ok': True, **operation()}, ensure_ascii=False, allow_nan=False)
        except (LedgerError, OSError, sqlite3.Error, ValueError, RecursionError) as exc:
            # Never log payloads or customer data.
            message = str(exc) if isinstance(exc, LedgerError) else 'خطای پایگاه یا دیسک؛ اطلاعات قبلی حفظ شده است.'
            return json.dumps({'ok': False, 'error': message}, ensure_ascii=False)

    @Slot(result=str)
    def load(self):
        return self._response(self.ledger.load)

    @Slot(str, result=str)
    def archiveLegacy(self, raw):
        return self._response(lambda: {'archive': self.ledger.archive_legacy(raw)})

    @Slot(int, str, str, result=str)
    def save(self, revision, raw, reason):
        return self._response(lambda: self.ledger.save(revision, raw, reason))


def attach_accounting_bridge(view, folder):
    page = view.page()
    bridge = AccountingBridge(folder, page)
    channel = QWebChannel(page)
    channel.registerObject('ledger', bridge)
    page.setWebChannel(channel)
    view.accounting_bridge = bridge
    view.accounting_channel = channel
