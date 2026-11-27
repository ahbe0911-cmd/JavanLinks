from pathlib import Path
from PySide6.QtCore import Qt, QStandardPaths
from PySide6.QtGui import QKeySequence, QShortcut, QPageLayout, QPageSize
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow, QLineEdit,
    QProgressBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget, QTabWidget,
    QDialog, QFileDialog)
from .browser import BrowserView, BrowserSessions
from .browser_utils import next_zoom, web_address, origin_label
from .catalog import Link
from .sidebar import Sidebar
from .storage import CatalogStore, atomic_write
from .manager import ManagerDialog, warn, ask
from .downloads import DownloadManager


def label(text, name):
    item = QLabel(text)
    item.setObjectName(name)
    item.setTextFormat(Qt.TextFormat.PlainText)
    return item


class MainWindow(QMainWindow):
    MAX_TABS = 24

    def __init__(self, store=None):
        super().__init__()
        self.store = store if store is not None else CatalogStore(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / 'catalog.json')
        self.setWindowTitle('لینک‌های کاربردی کافینت جوان')
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumSize(920, 550)
        self.resize(1280, 800)
        self.print_jobs = {}
        self.shortcuts = []
        self.downloads = DownloadManager(self)
        self.sessions = BrowserSessions(self.store.path.parent, self.downloads.receive)
        root = QWidget()
        root.setObjectName('root')
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.sidebar = Sidebar(self.store.state.links)
        outer.addWidget(self.sidebar)
        workspace = QWidget()
        outer.addWidget(workspace, 1)
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        top = QFrame()
        top.setObjectName('topbar')
        row = QHBoxLayout(top)
        row.setContentsMargins(8, 7, 8, 7)
        self.menu_button = self.button(row, 'منو', 'جمع یا باز کردن منو', self.toggle_sidebar)
        self.page_title = label('صفحه اصلی', 'pageTitle')
        self.page_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        row.addWidget(self.page_title, 1)
        self.download_button = self.button(row, 'دانلودها', 'مدیریت دانلود', self.show_downloads)
        self.print_button = self.button(row, 'چاپ', 'چاپ صفحه (Ctrl+P)', self.print_page)
        self.pdf_button = self.button(row, 'PDF', 'ذخیره صفحه به صورت PDF', self.save_pdf)
        self.button(row, '＋ زبانه', 'زبانه جدید (Ctrl+T)', self.new_home)
        layout.addWidget(top)

        toolbar = QFrame()
        toolbar.setObjectName('topbar')
        nav = QHBoxLayout(toolbar)
        nav.setContentsMargins(8, 6, 8, 6)
        nav.setSpacing(4)
        toolbar.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        nav.setDirection(QHBoxLayout.Direction.LeftToRight)
        self.back = self.button(nav, '←', 'بازگشت (Alt+Left)', lambda: self.current().back())
        self.forward = self.button(nav, '→', 'جلو (Alt+Right)', lambda: self.current().forward())
        self.reload = self.button(nav, '↻', 'بارگذاری مجدد (Ctrl+R)', self.reload_or_stop)
        self.home_button = self.button(nav, 'خانه', 'صفحه اصلی', self.show_home)
        self.address = QLineEdit()
        self.address.setObjectName('addressBar')
        self.address.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.address.setPlaceholderText('https://...')
        self.address.setAccessibleName('آدرس صفحه اینترنتی')
        self.address.returnPressed.connect(self.navigate_address)
        nav.addWidget(self.address, 1)
        self.go = self.button(nav, 'برو', 'باز کردن آدرس', self.navigate_address)
        self.minus = self.button(nav, '−', 'کوچک‌نمایی (Ctrl+-)', lambda: self.zoom(-1))
        self.zoom_label = self.button(nav, '100%', 'بازنشانی بزرگ‌نمایی (Ctrl+0)', lambda: self.zoom(0))
        self.plus = self.button(nav, '+', 'بزرگ‌نمایی (Ctrl++)', lambda: self.zoom(1))
        layout.addWidget(toolbar)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.tabs = QTabWidget()
        self.tabs.setObjectName('browserTabs')
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.sync)
        layout.addWidget(self.tabs, 1)
        status_card = QFrame()
        status_card.setObjectName('statusCard')
        bottom = QHBoxLayout(status_card)
        bottom.setContentsMargins(10, 5, 10, 5)
        self.status = label('آماده', 'status')
        self.origin = label('صفحه داخلی', 'address')
        self.origin.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.origin.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.origin.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        bottom.addWidget(self.status)
        bottom.addWidget(self.origin, 1)
        layout.addWidget(status_card)

        self.sidebar.link_selected.connect(self.open_link)
        self.sidebar.manage_requested.connect(self.manage_links)
        self.downloads.changed.connect(self.download_count)
        for seq, action in [('Ctrl+T', self.new_home), ('Ctrl+W', lambda: self.close_tab(self.tabs.currentIndex())),
                            ('Ctrl+L', self.focus_address), ('Ctrl+R', self.reload_or_stop), ('F5', self.reload_or_stop),
                            ('Alt+Left', lambda: self.current().back()), ('Alt+Right', lambda: self.current().forward()),
                            ('Ctrl+P', self.print_page), ('Ctrl+J', self.show_downloads),
                            ('Ctrl+=', lambda: self.zoom(1)), ('Ctrl+-', lambda: self.zoom(-1)),
                            ('Ctrl+0', lambda: self.zoom(0)), ('Ctrl+Tab', self.next_tab)]:
            shortcut = QShortcut(QKeySequence(seq), self)
            shortcut.activated.connect(action)
            self.shortcuts.append(shortcut)
        self.new_home()
        self._apply_sidebar()

    @staticmethod
    def button(layout, text, hint, callback):
        b = QPushButton(text)
        b.setObjectName('browserAction')
        b.setToolTip(hint)
        b.setAccessibleName(hint)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(callback)
        layout.addWidget(b)
        return b

    @property
    def browser(self):
        return self.current()

    def current(self):
        return self.tabs.currentWidget()

    def make_tab(self, root=None, title='زبانه جدید'):
        if self.tabs.count() >= self.MAX_TABS:
            self.status.setText('حداکثر ۲۴ زبانه باز مجاز است.')
            return None
        view = BrowserView(self.sessions, root)
        view.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        view.setAccessibleName('مرورگر داخلی')
        view.loadStarted.connect(lambda: self.started(view))
        view.loadProgress.connect(lambda n: self.loading(view, n))
        view.loadFinished.connect(lambda ok: self.finished(view, ok))
        view.titleChanged.connect(lambda name: self.title_changed(view, name))
        view.urlChanged.connect(lambda _: self.sync_if(view))
        view.status_message.connect(lambda msg: self.message(view, msg))
        view.popup_requested.connect(self.popup)
        view.page().windowCloseRequested.connect(lambda: self.close_tab(self.tabs.indexOf(view)))
        view.printRequested.connect(lambda: self.print_page(view))
        view.printFinished.connect(lambda ok: self.print_done(view, ok))
        self.tabs.addTab(view, title)
        self.tabs.setCurrentWidget(view)
        return view

    def new_home(self):
        view = self.make_tab(title='صفحه اصلی')
        if view is not None:
            view.show_home()
            self.sync()
        return view

    def show_home(self):
        for i in range(self.tabs.count()):
            view = self.tabs.widget(i)
            if view.home:
                self.tabs.setCurrentWidget(view)
                return
        self.new_home()

    def close_tab(self, index):
        if index < 0 or index >= self.tabs.count():
            return
        view = self.tabs.widget(index)
        if view in self.print_jobs:
            warn(self, 'تا پایان چاپ یا ساخت PDF، این زبانه را نبندید.')
            return
        view.stop()
        self.tabs.removeTab(index)
        view.deleteLater()
        if not self.tabs.count():
            self.new_home()
        self.sync()

    def next_tab(self):
        if self.tabs.count():
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % self.tabs.count())

    def open_link(self, link: Link):
        for i in range(self.tabs.count()):
            v = self.tabs.widget(i)
            if v.link_id == link.id:
                self.tabs.setCurrentWidget(v)
                return
        root = None
        if link.kind == 'html':
            try:
                path = Path(link.url).resolve()
                if not path.is_file():
                    raise ValueError('فایل HTML در مسیر ذخیره‌شده پیدا نشد.')
                root = path.parent
            except (OSError, ValueError, RuntimeError) as exc:
                warn(self, str(exc))
                self.sidebar.clear_active()
                return
            if not ask(self, 'فقط فایل HTML مورد اعتماد را اجرا کنید. این ابزار به فایل‌های پوشه خودش دسترسی دارد. ادامه می‌دهید؟'):
                self.sidebar.clear_active()
                return
        v = self.make_tab(root, link.title)
        if v is None:
            self.sidebar.clear_active()
            return
        v.link_id = link.id
        try:
            if root is None:
                v.navigate(link.url)
            else:
                v.open_local(link.url)
        except (OSError, ValueError, RuntimeError) as exc:
            warn(self, str(exc))
            self.close_tab(self.tabs.indexOf(v))

    def popup(self, source, request):
        if not request.isUserInitiated():
            self.message(source, 'پنجره خودکار مسدود شد.')
            return
        url = request.requestedUrl()
        if source.root is not None and not source.page().policy.allows(url):
            self.message(source, 'باز کردن پنجره خارج از پوشه مجاز نیست.')
            return
        if source.root is None and url.scheme() not in ('http', 'https', 'about', ''):
            self.message(source, 'نوع آدرس پنجره مجاز نیست.')
            return
        view = self.make_tab(source.root)
        if view is not None:
            request.openIn(view.page())

    def navigate_address(self):
        view = self.current()
        if view is None or view in self.print_jobs:
            return
        try:
            url = web_address(self.address.text())
            if view.root is not None:
                view = self.make_tab()
                if view is None:
                    return
            view.link_id = None
            view.navigate(url)
            self.sidebar.clear_active()
        except ValueError as exc:
            warn(self, str(exc))

    def focus_address(self):
        if self.address.isReadOnly():
            self.new_home()
        self.address.setFocus()
        self.address.selectAll()

    def reload_or_stop(self):
        view = self.current()
        if view is not None and view not in self.print_jobs:
            if view.loading:
                view.stop()
            elif view.home:
                view.show_home()
            else:
                view.reload()

    def zoom(self, delta):
        v = self.current()
        if v is not None:
            percent = 100 if delta == 0 else next_zoom(round(v.zoomFactor() * 100), delta)
            v.setZoomFactor(percent / 100)
            self.sync()

    def started(self, v):
        v.loading = True
        v.progress_value = 0
        self.message(v, 'در حال بارگذاری…')

    def loading(self, v, n):
        v.progress_value = n
        self.sync_if(v)

    def finished(self, v, ok):
        v.loading = False
        self.message(v, 'آماده' if ok else 'بارگذاری ناموفق یا متوقف شد')

    def title_changed(self, v, title):
        index = self.tabs.indexOf(v)
        if index >= 0:
            name = 'صفحه اصلی' if v.home else (title or 'زبانه جدید')
            self.tabs.setTabText(index, name[:50])
            self.tabs.setTabToolTip(index, name)
        self.sync_if(v)

    def message(self, v, text):
        v.last_status = text
        self.sync_if(v)

    def sync_if(self, v):
        if self.current() is v:
            self.sync()

    def sync(self, *_):
        v = self.current()
        if v is None:
            return
        url = v.url()
        if url.scheme() in ('http', 'https'):
            v.home = False
        self.page_title.setText('صفحه اصلی' if v.home else (v.title() or self.tabs.tabText(self.tabs.currentIndex())))
        self.status.setText(v.last_status)
        self.progress.setVisible(v.loading)
        self.progress.setValue(v.progress_value)
        busy = v in self.print_jobs
        self.back.setEnabled(v.history().canGoBack() and not busy)
        self.forward.setEnabled(v.history().canGoForward() and not busy)
        self.reload.setText('×' if v.loading else '↻')
        self.reload.setEnabled(not busy)
        self.zoom_label.setText(f'{round(v.zoomFactor() * 100)}%')
        self.print_button.setEnabled(not busy and not v.loading)
        self.pdf_button.setEnabled(not busy and not v.loading)
        self.address.setReadOnly(v.root is not None or busy)
        self.go.setEnabled(v.root is None and not busy)
        # Always show the true origin separately; do not expose tokens in status.
        if v.root is not None:
            self.address.setText(url.toLocalFile())
            self.origin.setText('HTML محلی')
        else:
            if not self.address.hasFocus() or self.address.property('tabIndex') != self.tabs.currentIndex():
                self.address.setText(url.toString() if url.scheme() in ('http', 'https') else '')
            self.origin.setText(origin_label(url.toString()))
        self.address.setProperty('tabIndex', self.tabs.currentIndex())

    def print_page(self, view=None):
        v = view if isinstance(view, BrowserView) else self.current()
        if v is None or v in self.print_jobs or v.loading:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle('چاپ صفحه')
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.print_jobs[v] = printer
        self.message(v, 'در حال چاپ…')
        v.print(printer)

    def print_done(self, v, ok):
        if v not in self.print_jobs:
            return
        self.print_jobs.pop(v, None)
        self.message(v, 'چاپ انجام شد' if ok else 'چاپ ناموفق بود')
        if not ok:
            warn(self, 'چاپ صفحه انجام نشد.')

    def save_pdf(self):
        v = self.current()
        if v is None or v in self.print_jobs or v.loading:
            return
        name, _ = QFileDialog.getSaveFileName(self, 'ذخیره PDF', 'page.pdf', 'PDF (*.pdf)')
        if not name:
            return
        path = Path(name)
        if path.suffix.lower() != '.pdf':
            path = path.with_suffix('.pdf')
            if path.exists() and not ask(self, 'فایل PDF موجود جایگزین شود؟'):
                return
        self.print_jobs[v] = path
        self.message(v, 'در حال ساخت PDF…')

        def complete(data):
            try:
                if not data:
                    raise ValueError('موتور مرورگر PDF تولید نکرد.')
                atomic_write(path, bytes(data))
            except (OSError, ValueError) as exc:
                self.print_jobs.pop(v, None)
                self.message(v, 'ساخت PDF ناموفق بود')
                warn(self, str(exc))
                return
            self.print_jobs.pop(v, None)
            self.message(v, 'PDF ذخیره شد')

        v.page().printToPdf(complete)

    def download_count(self):
        n = self.downloads.active_count()
        self.download_button.setText(f'دانلودها ({n})' if n else 'دانلودها')

    def show_downloads(self):
        self.downloads.show()
        self.downloads.raise_()
        self.downloads.activateWindow()

    def _apply_sidebar(self):
        collapsed = self.store.state.sidebar_collapsed
        self.sidebar.setVisible(not collapsed)
        self.menu_button.setText('نمایش منو' if collapsed else 'جمع کردن منو')

    def manage_links(self):
        dialog = ManagerDialog(self.store, self)
        dialog.changed.connect(self.catalog_changed)
        dialog.exec()

    def catalog_changed(self):
        self.sidebar.set_links(self.store.state.links)
        # Existing pages remain open, but future launches use edited addresses.
        for i in range(self.tabs.count()):
            self.tabs.widget(i).link_id = None
        self._apply_sidebar()

    def toggle_sidebar(self):
        try:
            self.store.set_sidebar(not self.store.state.sidebar_collapsed)
        except (OSError, ValueError) as exc:
            warn(self, str(exc))
            return
        self._apply_sidebar()

    def closeEvent(self, event):
        if self.print_jobs:
            warn(self, 'ابتدا منتظر پایان چاپ یا ساخت PDF بمانید.')
            event.ignore()
            return
        if self.downloads.active_count() and not ask(self, 'دانلود فعال وجود دارد. دانلودها لغو و برنامه بسته شود؟'):
            event.ignore()
            return
        self.downloads.cancel_all()
        self.downloads.hide()
        super().closeEvent(event)
