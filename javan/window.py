from pathlib import Path
from time import time_ns
import sqlite3
from zipfile import BadZipFile
from PySide6.QtCore import Qt, QStandardPaths, QCoreApplication, QEvent, QTimer
from PySide6.QtWebEngineCore import QWebEnginePage
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
from .accounting import prepare_accounting, import_fonts
from .bridge import attach_accounting_bridge


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
        self.accounting_button = self.button(row, 'حسابداری', 'حسابداری، فاکتور و دفتر نسیه (Ctrl+Shift+A)', self.open_accounting)
        self.accounting_button.setObjectName('accountingButton')
        self.accounting_button.setCheckable(True)
        self.session_button = self.button(row, 'پایان جلسه', 'پاک کردن نشست اینترنتی مشتری؛ حسابداری محفوظ می‌ماند', self.end_customer_session)
        self.session_button.setObjectName('sessionButton')
        self.font_button = self.button(row, 'فونت‌ها', 'وارد کردن فونت‌های حسابداری از فایل ZIP یا TTF', self.choose_accounting_fonts)
        self.economy_button = self.button(row, 'سبک', 'کاهش فعالیت تب‌های غیرفعال با رعایت پیشنهاد موتور مرورگر', self.toggle_economy)
        self.economy_button.setObjectName('economyButton')
        self.economy_button.setCheckable(True)
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
        self.tabs.currentChanged.connect(self.resume_current)
        self.economy_timer = QTimer(self)
        self.economy_timer.setInterval(30000)
        self.economy_timer.timeout.connect(self.sleep_background_tabs)
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
                            ('Ctrl+Shift+A', self.open_accounting),
                            ('Ctrl+=', lambda: self.zoom(1)), ('Ctrl+-', lambda: self.zoom(-1)),
                            ('Ctrl+0', lambda: self.zoom(0)), ('Ctrl+Tab', self.next_tab)]:
            shortcut = QShortcut(QKeySequence(seq), self)
            shortcut.activated.connect(action)
            self.shortcuts.append(shortcut)
        self.new_home()
        self._apply_sidebar()

    def accounting_view(self):
        for i in range(self.tabs.count()):
            v = self.tabs.widget(i)
            if getattr(v, 'is_accounting', False):
                return v
        return None

    def open_accounting(self):
        view = self.accounting_view()
        if view is not None:
            self.tabs.setCurrentWidget(view)
            self.accounting_button.setChecked(True)
            return
        view = None
        try:
            path = prepare_accounting(self.store.path.parent)
            view = self.make_tab(path.parent, 'حسابداری')
            if view is None:
                self.accounting_button.setChecked(False)
                return
            view.page().accounting_path = path.resolve()
            attach_accounting_bridge(view, self.store.path.parent / 'accounting-data')
            view.is_accounting = True
            view.open_local(str(path))
            self.sync()
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
            if view is not None:
                view.is_accounting = False
                self.close_tab(self.tabs.indexOf(view))
            self.accounting_button.setChecked(False)
            warn(self, 'باز کردن حسابداری ناموفق بود.\n' + str(exc))

    def toggle_economy(self, enabled):
        if enabled:
            self.economy_timer.start()
            self.status.setText('حالت سبک فعال شد؛ فقط زبانه‌های اینترنتی غیرفعال و امن برای توقف، موقتاً متوقف می‌شوند.')
        else:
            self.economy_timer.stop()
            for i in range(self.tabs.count()):
                self.tabs.widget(i).page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
            self.status.setText('حالت سبک غیرفعال شد.')

    def resume_current(self, *_):
        view = self.current()
        if view is not None:
            view.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)

    def sleep_background_tabs(self):
        # No discard/reload: preserve form state. Never freeze local tools,
        # accounting, foreground tabs, active downloads or print jobs.
        if self.downloads.active_count() or self.print_jobs:
            return
        active = self.current()
        state = QWebEnginePage.LifecycleState
        for i in range(self.tabs.count()):
            view = self.tabs.widget(i)
            if view is active or view.root is not None or view.loading:
                continue
            page = view.page()
            if page.lifecycleState() == state.Active and page.recommendedState() in (state.Frozen, state.Discarded):
                page.setLifecycleState(state.Frozen)

    def end_customer_session(self):
        if self.print_jobs or self.downloads.active_count():
            warn(self, 'ابتدا چاپ و دانلودهای فعال را به پایان برسانید.')
            return
        if not ask(self, 'همه زبانه‌های اینترنتی بسته و نشست ورود مشتری پاک شود؟ فایل‌های دانلودشده روی دیسک حذف نمی‌شوند. حسابداری و ابزارهای HTML محفوظ می‌مانند.'):
            return
        for i in range(self.tabs.count() - 1, -1, -1):
            v = self.tabs.widget(i)
            if v.root is None:
                v.stop()
                self.tabs.removeTab(i)
                v.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.sessions.reset_web()
        self.downloads.clear_finished()
        self.sidebar.clear_active()
        self.new_home()
        self.status.setText('نشست اینترنتی جدید آماده است؛ فایل‌های قبلی را از مسیر دانلود بررسی کنید.')

    def dispose_views(self):
        self.economy_timer.stop()
        for i in range(self.tabs.count() - 1, -1, -1):
            v = self.tabs.widget(i)
            v.stop()
            self.tabs.removeTab(i)
            v.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.sessions.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def choose_accounting_fonts(self):
        names, _ = QFileDialog.getOpenFileNames(self, 'انتخاب فایل‌های فونت ارسالی', '', 'فونت و آرشیو (*.zip *.ttf)')
        if not names:
            return
        try:
            imported = import_fonts(self.store.path.parent, names)
        except (OSError, ValueError, RuntimeError, BadZipFile) as exc:
            warn(self, 'وارد کردن فونت ناموفق بود.\n' + str(exc))
            return
        view = self.accounting_view()
        if view is not None:
            # Refresh the stylesheet only; don't reload an unsaved invoice.
            stamp = time_ns()
            view.page().runJavaScript("(()=>{const e=document.querySelector('link[href^=\"fonts/accounting.css\"]');if(e)e.href='fonts/accounting.css?v=" + str(stamp) + "';})()")
        self.status.setText(f'{len(imported)} فونت محلی وارد شد.')

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
        if getattr(view, 'is_accounting', False) and not ask(self, 'حسابداری بسته شود؟ اطلاعات ثبت‌شده حفظ می‌شود، اما فاکتور ثبت‌نشده ممکن است از دست برود.'):
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
        if getattr(source, 'is_accounting', False):
            self.message(source, 'حسابداری در یک زبانه اختصاصی اجرا می‌شود.')
            return
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
            if getattr(view, 'is_accounting', False) and not view.loading and not ask(self, 'بارگذاری مجدد ممکن است پیش‌نویس ثبت‌نشده را پاک کند. ادامه؟'):
                return
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
        # Update only the progress widget, not every toolbar control, for background load events.
        v.progress_value = n
        if self.current() is v and self.progress.value() != n:
            self.progress.setValue(n)

    def finished(self, v, ok):
        v.loading = False
        self.message(v, 'آماده' if ok else 'بارگذاری ناموفق یا متوقف شد')

    def title_changed(self, v, title):
        index = self.tabs.indexOf(v)
        if index >= 0:
            name = 'حسابداری' if getattr(v, 'is_accounting', False) else ('صفحه اصلی' if v.home else (title or 'زبانه جدید'))
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
        accounting = getattr(v, 'is_accounting', False)
        self.accounting_button.setChecked(accounting)
        url = v.url()
        if url.scheme() in ('http', 'https'):
            v.home = False
        self.page_title.setText('حسابداری و صدور فاکتور' if accounting else ('صفحه اصلی' if v.home else (v.title() or self.tabs.tabText(self.tabs.currentIndex()))))
        self.status.setText(v.last_status)
        self.progress.setVisible(v.loading)
        self.progress.setValue(v.progress_value)
        busy = v in self.print_jobs
        self.back.setEnabled(v.history().canGoBack() and not busy and not accounting)
        self.forward.setEnabled(v.history().canGoForward() and not busy and not accounting)
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
            self.origin.setText('حسابداری آفلاین · SQLite' if accounting else 'HTML محلی')
        else:
            if not self.address.hasFocus() or self.address.property('tabIndex') != self.tabs.currentIndex():
                self.address.setText(url.toString() if url.scheme() in ('http', 'https') else '')
            self.origin.setText(('⚠ اتصال ناامن  |  ' if url.scheme() == 'http' else '') + origin_label(url.toString()))
        self.address.setProperty('tabIndex', self.tabs.currentIndex())

    def print_page(self, view=None):
        v = view if isinstance(view, BrowserView) else self.current()
        if v is None or v in self.print_jobs or v.loading:
            return
        if getattr(v, 'is_accounting', False) and not isinstance(view, BrowserView):
            v.page().runJavaScript('typeof javanPrepareCurrentPrint === "function" && javanPrepareCurrentPrint()', lambda ok: self._native_print(v) if ok else None)
            return
        self._native_print(v)

    @staticmethod
    def _clear_accounting_print(v):
        if getattr(v, 'is_accounting', False):
            v.page().runJavaScript('typeof javanClearPrint === "function" && javanClearPrint()')

    def _native_print(self, v):
        if v in self.print_jobs or self.tabs.indexOf(v) < 0:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle('چاپ صفحه')
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self._clear_accounting_print(v)
            return
        self.print_jobs[v] = printer
        self.message(v, 'در حال چاپ…')
        v.print(printer)

    def print_done(self, v, ok):
        if v not in self.print_jobs:
            return
        self.print_jobs.pop(v, None)
        self._clear_accounting_print(v)
        self.message(v, 'چاپ انجام شد' if ok else 'چاپ ناموفق بود')
        if not ok:
            warn(self, 'چاپ صفحه انجام نشد.')

    def save_pdf(self):
        v = self.current()
        if v is None or v in self.print_jobs or v.loading:
            return
        if getattr(v, 'is_accounting', False):
            v.page().runJavaScript('typeof javanPrepareCurrentPrint === "function" && javanPrepareCurrentPrint()', lambda ok: self._save_prepared_pdf(v) if ok else None)
            return
        self._save_prepared_pdf(v)

    def _save_prepared_pdf(self, v):
        if v in self.print_jobs or self.tabs.indexOf(v) < 0:
            return
        name, _ = QFileDialog.getSaveFileName(self, 'ذخیره PDF', 'page.pdf', 'PDF (*.pdf)')
        if not name:
            self._clear_accounting_print(v)
            return
        path = Path(name)
        if path.suffix.lower() != '.pdf':
            path = path.with_suffix('.pdf')
            if path.exists() and not ask(self, 'فایل PDF موجود جایگزین شود؟'):
                self._clear_accounting_print(v)
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
                self._clear_accounting_print(v)
                self.message(v, 'ساخت PDF ناموفق بود')
                warn(self, str(exc))
                return
            self.print_jobs.pop(v, None)
            self._clear_accounting_print(v)
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
        if self.accounting_view() is not None and not ask(self, 'برنامه بسته شود؟ فاکتورهای ثبت‌شده محفوظ هستند؛ ابتدا فاکتور در حال ویرایش را ثبت کنید.'):
            event.ignore()
            return
        if self.downloads.active_count() and not ask(self, 'دانلود فعال وجود دارد. دانلودها لغو و برنامه بسته شود؟'):
            event.ignore()
            return
        self.downloads.cancel_all()
        self.downloads.hide()
        super().closeEvent(event)
