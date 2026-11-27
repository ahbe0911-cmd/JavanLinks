"""A single WebEngine view; the browser controller can be reused for tabs later."""
from pathlib import Path
from PySide6.QtCore import QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

HOME_HTML = '''<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box} body{margin:0;background:#f8fafc;color:#18283b;font-family:Vazirmatn,Vazir,Tahoma,'Segoe UI',sans-serif;line-height:1.9}
main{max-width:920px;margin:0 auto;padding:clamp(22px,5vw,62px)}
.hero{background:linear-gradient(125deg,#14263c,#1c4556);color:#fff;border-radius:22px;padding:clamp(24px,5vw,45px);position:relative;overflow:hidden}
.eyebrow{font-size:12px;letter-spacing:.4px;color:#a8e0d8} h1{font-size:clamp(24px,3.5vw,36px);margin:10px 0 12px} p{margin:0;color:inherit} .hero p{color:#d3e2ed;font-size:14px}
h2{font-size:17px;margin:32px 0 14px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}
article{background:#fff;border:1px solid #e0e7ef;border-radius:14px;padding:18px;min-height:130px} article b{display:block;margin:8px 0 4px} article p{font-size:12px;color:#607387}
.num{font-size:12px;background:#e3f3ef;color:#186761;border-radius:8px;padding:3px 10px;display:inline-block} .foot{font-size:12px;color:#607387;margin-top:24px}
</style></head><body><main><div class="hero"><div class="eyebrow">میز کار دیجیتال &nbsp; / &nbsp; نسخه ۰.۲</div><h1>لینک‌های کاربردی کافینت جوان</h1><p>سامانه موردنظر خود را از منوی سمت راست انتخاب کنید تا در همین محیط باز شود.</p></div>
<h2>دسترسی به خدمات</h2><div class="grid"><article><span class="num">۰۱</span><b>خدمات دولتی</b><p>دسترسی به درگاه‌های عمومی و مالیاتی</p></article><article><span class="num">۰۲</span><b>بانکی و چک</b><p>اطلاعات و سامانه‌های بانکی</p></article><article><span class="num">۰۳</span><b>آموزشی</b><p>آزمون‌ها و ثبت‌نام‌های آموزشی</p></article><article><span class="num">۰۴</span><b>خدمات پستی</b><p>پیگیری و خدمات مرسولات</p></article></div>
<p class="foot">برای یافتن سریع‌تر یک سامانه، نام آن را در کادر جستجوی منو بنویسید.</p></main></body></html>'''


class BrowserPage(QWebEnginePage):
    navigation_blocked = Signal(str)

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        # Phase 1 only allows ordinary web navigation and its own HTML landing page.
        # Local document trust rules will be handled separately in phase 2.
        if is_main_frame and url.scheme().lower() not in ('http', 'https', 'about', 'data', 'blob'):
            self.navigation_blocked.emit(url.scheme())
            return False
        return super().acceptNavigationRequest(url, navigation_type, is_main_frame)


class LocalPolicy(QWebEngineUrlRequestInterceptor):
    """Local tools are isolated from web sessions and restricted to their folder."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = None

    def allows(self, url):
        if url.scheme().lower() in ('data', 'blob', 'about'):
            return True
        if url.isLocalFile() and not url.host() and self.root is not None:
            try:
                return Path(url.toLocalFile()).resolve().is_relative_to(self.root)
            except (OSError, ValueError, RuntimeError):
                return False
        return False

    def interceptRequest(self, info):
        if not self.allows(info.requestUrl()):
            info.block(True)


class LocalPage(QWebEnginePage):
    def __init__(self, profile, policy, parent):
        super().__init__(profile, parent)
        self.policy = policy

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        return self.policy.allows(url)


class BrowserView(QWebEngineView):
    status_message = Signal(str)

    def __init__(self, parent=None, local_data=None):
        super().__init__(parent)
        self.local_data = local_data
        self.local_profile = None
        self.local_page = None
        self.local_policy = None
        # An unnamed profile is off-the-record; cookies remain available within
        # the current process but aren't intentionally persisted across launches.
        self.profile = QWebEngineProfile(QApplication.instance())
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self.browser_page = BrowserPage(self.profile, self)
        self.setPage(self.browser_page)
        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        self.browser_page.navigation_blocked.connect(lambda scheme: self.status_message.emit(f'این نوع آدرس پشتیبانی نمی‌شود: {scheme}'))
        self.profile.downloadRequested.connect(self._cancel_download)
        self.browser_page.newWindowRequested.connect(self._popup_requested)

    def _cancel_download(self, request):
        request.cancel()
        self.status_message.emit('مدیریت دانلود در فاز سوم فعال خواهد شد.')

    def _popup_requested(self, request):
        # A single-view shell has no popup/tab container yet. Do not silently
        # replace an authentication page or send anything to another browser.
        self.status_message.emit('پنجره‌های جدید و تب‌ها در فاز سوم پشتیبانی می‌شوند.')

    def navigate(self, address: str):
        url = QUrl(address)
        if not url.isValid() or url.scheme().lower() not in ('http', 'https') or not url.host() or url.userInfo():
            self.status_message.emit('آدرس اینترنتی معتبر نیست.')
            return
        self._web_mode()
        self.setUrl(url)

    def _web_mode(self):
        if self.local_page is not None:
            self.local_page.triggerAction(QWebEnginePage.WebAction.Stop)
            self.setPage(self.browser_page)
            self.local_page.deleteLater()
            self.local_page = None
            self.local_policy.root = None

    def open_local(self, address):
        path = Path(address).resolve()
        if not path.is_file() or path.suffix.lower() not in ('.html', '.htm'):
            raise ValueError('فایل HTML یافت نشد.')
        self._web_mode()
        if self.local_profile is None:
            self.local_profile = QWebEngineProfile('JavanLocalTools', QApplication.instance())
            if self.local_data is not None:
                self.local_profile.setPersistentStoragePath(str(Path(self.local_data) / 'local-web-storage'))
                self.local_profile.setCachePath(str(Path(self.local_data) / 'local-web-cache'))
            self.local_profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
            self.local_policy = LocalPolicy(self.local_profile)
            self.local_profile.setUrlRequestInterceptor(self.local_policy)
            self.local_profile.downloadRequested.connect(self._cancel_download)
        self.local_policy.root = path.parent
        self.local_page = LocalPage(self.local_profile, self.local_policy, self)
        settings = self.local_page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        self.local_page.newWindowRequested.connect(self._popup_requested)
        self.setPage(self.local_page)
        self.setUrl(QUrl.fromLocalFile(str(path)))

    def show_home(self):
        self._web_mode()
        self.setHtml(HOME_HTML)
