"""Launch a separate native WebView2 workspace; the Qt GUI stays responsive."""
import json
import shutil
from threading import Thread
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from .browser_utils import web_address

ROOT = Path(__file__).resolve().parent.parent


class EdgeHost(QObject):
    status = Signal(str)
    event_received = Signal(str)

    def __init__(self, folder, parent=None):
        super().__init__(parent)
        self.exe = ROOT / 'assets' / 'edge-host' / 'JavanEdge.exe'
        self.folder = Path(folder) / 'edge-sessions'
        self.process = None
        self.session = None
        self.ready = False
        self.closing = False
        self.pending = []
        self.buffer = b''
        # The application holds the single-instance lock. Remove only old,
        # program-created session folders, never files outside this directory.
        if self.folder.is_dir():
            for p in self.folder.iterdir():
                if p.is_dir() and not p.is_symlink() and len(p.name) == 32 and all(c in '0123456789abcdef' for c in p.name):
                    Thread(target=shutil.rmtree, args=(p,), kwargs={'ignore_errors':True}, daemon=True).start()

    def available(self):
        return self.exe.is_file()

    def active(self):
        return self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning

    def open(self, link_id, url, title):
        url = web_address(url)
        if not self.available():
            self.status.emit('بسته مرورگر Edge نصب نیست؛ از موتور Qt استفاده کنید.')
            return False
        if self.closing:
            self.status.emit('نشست Edge در حال بسته شدن است؛ دوباره تلاش کنید.')
            return False
        if not self.active():
            self.session = self.folder / uuid4().hex
            self.session.mkdir(parents=True, exist_ok=False)
            self.ready = False
            self.buffer = b''
            self.pending = []
            self.process = QProcess(self)
            proc = self.process
            proc.setProgram(str(self.exe))
            proc.setArguments(['--profile', str(self.session)])
            proc.readyReadStandardOutput.connect(lambda: self.read(proc))
            proc.finished.connect(lambda *_: self.finished(proc))
            proc.errorOccurred.connect(lambda error: self.failed(proc, error))
            self.pending.append({'cmd':'open','id':link_id,'url':url,'title':title})
            proc.start()
            self.status.emit('در حال راه‌اندازی موتور Edge…')
            QTimer.singleShot(30000, lambda: self.start_timeout(proc))
            return True
        self.pending.append({'cmd':'open','id':link_id,'url':url,'title':title})
        self.flush()
        return True

    def start_timeout(self, proc):
        if self.process is proc and not self.ready and not self.closing:
            self.status.emit('راه‌اندازی WebView2 طولانی شد؛ موتور Qt همچنان قابل استفاده است.')
            self.close_session()

    def flush(self):
        if not self.ready or not self.active():
            return
        for item in self.pending:
            self.process.write((json.dumps(item,ensure_ascii=False)+'\n').encode('utf-8'))
        self.pending.clear()

    def read(self, proc):
        if self.process is not proc:
            return
        self.buffer += bytes(proc.readAllStandardOutput())
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n',1)
            try:
                event = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if event.get('kind') == 'ready':
                self.ready = True
                self.status.emit('موتور Edge WebView2 آماده است.')
                self.flush()
            elif event.get('kind') == 'reused':
                self.status.emit('زبانه موجود بدون بارگذاری مجدد فعال شد.')
            elif event.get('kind') == 'error':
                self.status.emit('خطا در موتور Edge؛ Runtime و نصب برنامه را بررسی کنید.')
            if event.get('kind') in ('ready','loaded','reused','error'):
                self.event_received.emit(event['kind'])

    def failed(self, proc, error):
        if self.process is proc:
            self.status.emit('اجرای موتور Edge ناموفق بود؛ از حالت Qt استفاده کنید.')
            if error == QProcess.ProcessError.FailedToStart:
                self.finished(proc)

    def finished(self, proc):
        if self.process is not proc:
            return
        self.process = None
        self.ready = False
        self.closing = False
        self.pending.clear()
        if self.session is not None:
            Thread(target=shutil.rmtree, args=(self.session,), kwargs={'ignore_errors':True}, daemon=True).start()
            self.session = None
        proc.deleteLater()
        self.event_received.emit('closed')

    def close_session(self):
        if not self.active():
            return
        self.closing = True
        proc = self.process
        proc.write(b'{"cmd":"close"}\n')
        proc.closeWriteChannel()
        QTimer.singleShot(5000, lambda: proc.kill() if self.process is proc and self.active() else None)

    def shutdown(self):
        if self.active():
            proc = self.process
            self.close_session()
            if not proc.waitForFinished(3000):
                proc.kill()
                proc.waitForFinished(1000)
