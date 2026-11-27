"""Narrow QWebChannel API installed only on the built-in accounting page."""
import json
import sqlite3
from PySide6.QtCore import QObject, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWidgets import QInputDialog, QLineEdit
from pathlib import Path
from .admin_pin import PinStore
from .debt_rules import sensitive_change
from .ledger_snapshot import LedgerSnapshot, LedgerError


class AccountingBridge(QObject):
    def __init__(self, folder, page):
        super().__init__(page)
        self.ledger = LedgerSnapshot(folder)
        self.pins = PinStore(Path(folder))
        self.view = page.parent()

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

    def authorize(self, old, new, reason):
        if not sensitive_change(old, new, reason):
            return True
        if not self.pins.exists():
            pin, ok = QInputDialog.getText(self.view, 'تعریف رمز مدیر', 'رمز جدید ۶ تا ۱۲ رقم انگلیسی:', QLineEdit.EchoMode.Password)
            if not ok or not self.pins.valid(pin):
                return False
            repeat, ok = QInputDialog.getText(self.view, 'تکرار رمز مدیر', 'رمز را دوباره وارد کنید:', QLineEdit.EchoMode.Password)
            if not ok or repeat != pin:
                return False
            self.pins.configure(pin)
            return True
        pin, ok = QInputDialog.getText(self.view, 'تأیید مدیر', 'رمز مدیر برای این عملیات حساس:', QLineEdit.EchoMode.Password)
        return ok and self.pins.verify(pin)

    @Slot(int, str, str, result=str)
    def save(self, revision, raw, reason):
        return self._response(lambda: self.ledger.save(revision, raw, reason, self.authorize))


def attach_accounting_bridge(view, folder):
    page = view.page()
    bridge = AccountingBridge(folder, page)
    channel = QWebChannel(page)
    channel.registerObject('ledger', bridge)
    page.setWebChannel(channel)
    view.accounting_bridge = bridge
    view.accounting_channel = channel
