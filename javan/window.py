from urllib.parse import urlsplit, urlunsplit
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow,
                               QProgressBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from .browser import BrowserView
from .catalog import Link, SAMPLE_LINKS
from .sidebar import Sidebar


def label(text: str, name: str) -> QLabel:
    result = QLabel(text)
    result.setObjectName(name)
    result.setTextFormat(Qt.TextFormat.PlainText)
    return result


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('لینک‌های کاربردی کافینت جوان')
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumSize(800, 520)
        self.resize(1280, 800)
        self._home = True
        self._name = 'صفحه اصلی'
        self._loading = False
        root = QWidget()
        root.setObjectName('root')
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.sidebar = Sidebar(SAMPLE_LINKS)
        outer.addWidget(self.sidebar)
        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(14, 14, 14, 14)
        workspace_layout.setSpacing(10)
        outer.addWidget(workspace, 1)

        top = QFrame()
        top.setObjectName('topbar')
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(12, 9, 12, 9)
        self.menu_button = QPushButton('جمع کردن منو')
        self.menu_button.setObjectName('menuButton')
        self.menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_button.setAccessibleName('نمایش یا جمع کردن منوی خدمات')
        top_layout.addWidget(self.menu_button)
        title_layout = QVBoxLayout()
        title_layout.setSpacing(1)
        self.page_title = label('صفحه اصلی', 'pageTitle')
        self.page_subtitle = label('مرورگر اختصاصی خدمات کافی‌نت', 'pageSubtitle')
        self.page_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        title_layout.addWidget(self.page_title)
        title_layout.addWidget(self.page_subtitle)
        top_layout.addLayout(title_layout, 1)
        self.home_button = QPushButton('صفحه اصلی')
        self.home_button.setObjectName('homeButton')
        self.home_button.setCursor(Qt.CursorShape.PointingHandCursor)
        top_layout.addWidget(self.home_button)
        workspace_layout.addWidget(top)

        browser_card = QFrame()
        browser_card.setObjectName('browserCard')
        browser_layout = QVBoxLayout(browser_card)
        browser_layout.setContentsMargins(1, 1, 1, 1)
        browser_layout.setSpacing(0)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        browser_layout.addWidget(self.progress)
        self.browser = BrowserView()
        self.browser.setAccessibleName('مرورگر داخلی')
        # UI chrome is RTL, but the websites control their own document direction.
        self.browser.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        browser_layout.addWidget(self.browser, 1)
        workspace_layout.addWidget(browser_card, 1)

        status_card = QFrame()
        status_card.setObjectName('statusCard')
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(10, 6, 10, 6)
        self.status = label('آماده', 'status')
        self.address = label('صفحه داخلی', 'address')
        self.address.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.address.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.address.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.address.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        status_layout.addWidget(self.status)
        status_layout.addWidget(self.address, 1)
        workspace_layout.addWidget(status_card)

        self.sidebar.link_selected.connect(self.open_link)
        self.menu_button.clicked.connect(self.toggle_sidebar)
        self.home_button.clicked.connect(self.show_home)
        self.browser.loadStarted.connect(self._load_started)
        self.browser.loadProgress.connect(self.progress.setValue)
        self.browser.loadFinished.connect(self._load_finished)
        self.browser.urlChanged.connect(self._url_changed)
        self.browser.status_message.connect(self.status.setText)
        self.show_home()

    def toggle_sidebar(self):
        visible = not self.sidebar.isHidden()
        self.sidebar.setVisible(not visible)
        self.menu_button.setText('نمایش منو' if visible else 'جمع کردن منو')
        self.menu_button.setToolTip(self.menu_button.text())

    def show_home(self):
        self._home = True
        self._name = 'صفحه اصلی'
        self.sidebar.clear_active()
        self.page_title.setText(self._name)
        self.page_title.setToolTip('')
        self.address.setText('صفحه داخلی')
        self.address.setToolTip('')
        self.browser.show_home()

    def open_link(self, link: Link):
        self._home = False
        self._name = link.title
        self.page_title.setText(link.title)
        self.page_title.setToolTip(link.title)
        self.browser.navigate(link.url)

    def _load_started(self):
        self._loading = True
        self.progress.setValue(0)
        self.progress.show()
        self.status.setText('در حال بارگذاری…')

    def _load_finished(self, success: bool):
        self._loading = False
        self.progress.hide()
        if success:
            self.status.setText('آماده' if self._home else 'بارگذاری کامل شد')
        else:
            self.status.setText('بارگذاری ناموفق؛ اتصال اینترنت و آدرس را بررسی کنید.')
            self.sidebar.clear_active()

    def _url_changed(self, url):
        if self._home and url.scheme() in ('data', 'about'):
            self.address.setText('صفحه داخلی')
            self.address.setToolTip('')
            return
        if url.scheme() in ('http', 'https'):
            # Suppress query/fragment in the status display (may contain tokens).
            self._home = False
            parts = urlsplit(url.toString())
            display = urlunsplit((parts.scheme, parts.netloc.rsplit('@', 1)[-1], parts.path, '', ''))
            self.address.setText(display)
            self.address.setToolTip(display)
