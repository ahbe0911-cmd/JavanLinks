"""Session-scoped download manager. Never opens downloaded files automatically."""
from pathlib import Path
from PySide6.QtCore import Qt, QStandardPaths, Signal, QTimer
from PySide6.QtWebEngineCore import QWebEngineDownloadRequest
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QAbstractItemView, QHeaderView)
from .browser_utils import safe_filename, risky_download
from .manager import warn, ask

D = QWebEngineDownloadRequest.DownloadState


class DownloadManager(QDialog):
    changed = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('مدیریت دانلودها')
        self.resize(820, 420)
        self.records = []
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(120)
        self.refresh_timer.timeout.connect(self.refresh)
        layout = QVBoxLayout(self)
        self.summary = QLabel('دانلودهای این نشست')
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['نام فایل', 'پیشرفت', 'وضعیت', 'مسیر ذخیره'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 190)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 145)
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        for title, action in [('توقف موقت', self.pause), ('ادامه', self.resume), ('لغو', self.cancel), ('پاک کردن پایان‌یافته‌ها', self.clear_finished), ('بستن', self.hide)]:
            b = QPushButton(title)
            b.clicked.connect(action)
            buttons.addWidget(b)
        layout.addLayout(buttons)

    def receive(self, request):
        if request.isSavePageDownload() or request.state() != D.DownloadRequested:
            request.cancel()
            return
        folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        suggested = str(Path(folder) / safe_filename(request.suggestedFileName()))
        name, _ = QFileDialog.getSaveFileName(self.parentWidget(), 'ذخیره فایل دانلودی', suggested, 'همه فایل‌ها (*)')
        if not name:
            request.cancel()
            return
        path = Path(name)
        if (risky_download(request.suggestedFileName()) or risky_download(path.name)) and not ask(self.parentWidget(), 'این نوع فایل ممکن است برنامه یا دستور اجرایی باشد. فقط از منبع مورد اعتماد دانلود کنید. ادامه؟'):
            request.cancel()
            return
        if any(not rec['finished'] and rec['path'] == path for rec in self.records):
            request.cancel()
            warn(self.parentWidget(), 'دانلود دیگری در همین مسیر در حال انجام است.')
            return
        rec = {'request': request, 'path': path, 'finished': False, 'progress': '۰٪', 'status': 'در انتظار'}
        self.records.append(rec)
        request.setDownloadDirectory(str(path.parent))
        request.setDownloadFileName(path.name)
        request.receivedBytesChanged.connect(lambda: self.update_record(rec))
        request.totalBytesChanged.connect(lambda: self.update_record(rec))
        request.stateChanged.connect(lambda *_: self.update_record(rec))
        request.isPausedChanged.connect(lambda: self.update_record(rec))
        request.isFinishedChanged.connect(lambda: self.update_record(rec))
        request.destroyed.connect(lambda *_: self.request_destroyed(rec))
        request.accept()
        self.update_record(rec)
        self.show()
        self.raise_()

    def update_record(self, rec):
        r = rec['request']
        if r is None:
            return
        total, received = r.totalBytes(), r.receivedBytes()
        rec['progress'] = f'{min(100, int(received * 100 / total))}٪' if total > 0 else f'{received / 1048576:.1f} MB'
        state = r.state()
        rec['status'] = {D.DownloadRequested: 'در انتظار', D.DownloadInProgress: 'متوقف موقت' if r.isPaused() else 'در حال دانلود',
                         D.DownloadCompleted: 'کامل شد', D.DownloadCancelled: 'لغو شد', D.DownloadInterrupted: 'ناموفق: ' + r.interruptReasonString()}.get(state, 'نامشخص')
        rec['finished'] = r.isFinished()
        if state == D.DownloadCompleted:
            rec['progress'] = '۱۰۰٪'
        if not self.refresh_timer.isActive():
            self.refresh_timer.start()

    def request_destroyed(self, rec):
        rec['request'] = None
        if not rec['finished']:
            rec['status'] = 'پایان یافت'
            rec['finished'] = True
        if rec in self.records and not self.refresh_timer.isActive():
            self.refresh_timer.start()

    def refresh(self):
        row = self.table.currentRow()
        self.table.setRowCount(len(self.records))
        for i, rec in enumerate(self.records):
            for j, value in enumerate((rec['path'].name, rec['progress'], rec['status'], str(rec['path']))):
                item = self.table.item(i, j)
                if item is None:
                    self.table.setItem(i, j, QTableWidgetItem(value))
                elif item.text() != value:
                    item.setText(value)
        if 0 <= row < len(self.records):
            self.table.selectRow(row)
        self.summary.setText(f'{len(self.records)} دانلود | {self.active_count()} فعال')
        self.changed.emit()

    def active_count(self):
        return sum(not rec['finished'] for rec in self.records)

    def selected(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.records):
            rec = self.records[row]
            if not rec['finished']:
                return rec['request']
        return None

    def pause(self):
        r = self.selected()
        if r is not None and r.state() == D.DownloadInProgress:
            r.pause()

    def resume(self):
        r = self.selected()
        if r is not None and r.isPaused():
            r.resume()

    def cancel(self):
        r = self.selected()
        if r is not None:
            r.cancel()

    def cancel_all(self):
        for rec in list(self.records):
            if not rec['finished'] and rec['request'] is not None:
                rec['request'].cancel()

    def clear_finished(self):
        self.records = [rec for rec in self.records if not rec['finished']]
        self.refresh()
