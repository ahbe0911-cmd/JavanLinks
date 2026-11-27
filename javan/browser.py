"""Shared web session and isolated local profiles for tabbed browsing."""
from pathlib import Path
from hashlib import sha256
import json
from .storage import atomic_write
from .diagnostics import LOGGER
from PySide6.QtCore import QObject
from PySide6.QtCore import QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication
from .manager import ask

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
</style></head><body><main><div class="hero"><div class="eyebrow">میز کار دیجیتال &nbsp; / &nbsp; نسخه ۰.۶ (آزمایشی)</div><h1>لینک‌های کاربردی کافینت جوان</h1><p>سامانه موردنظر خود را از منوی سمت راست انتخاب کنید تا در همین محیط باز شود.</p></div>
<h2>دسترسی به خدمات</h2><div class="grid"><article><span class="num">۰۱</span><b>خدمات دولتی</b><p>دسترسی به درگاه‌های عمومی و مالیاتی</p></article><article><span class="num">۰۲</span><b>بانکی و چک</b><p>اطلاعات و سامانه‌های بانکی</p></article><article><span class="num">۰۳</span><b>آموزشی</b><p>آزمون‌ها و ثبت‌نام‌های آموزشی</p></article><article><span class="num">۰۴</span><b>خدمات پستی</b><p>پیگیری و خدمات مرسولات</p></article></div>
<p class="foot">برای یافتن سریع‌تر یک سامانه، نام آن را در کادر جستجوی منو بنویسید.</p></main></body></html>'''


class BrowserPage(QWebEnginePage):
    navigation_blocked = Signal(str)

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        # Never write arbitrary web content or URL into diagnostic logs.
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            LOGGER.warning('WebEngine script error at line %d', line_number)



    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if url.scheme().lower() not in ('http', 'https', 'about', 'data', 'blob'):
            self.navigation_blocked.emit(url.scheme())
            return False
        return super().acceptNavigationRequest(url, navigation_type, is_main_frame)


class LocalPolicy(QWebEngineUrlRequestInterceptor):
    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root).resolve()

    def allows(self, url):
        if url.scheme() == 'qrc' and url.path() == '/qtwebchannel/qwebchannel.js' and not url.host() and self.root.name == 'accounting':
            return True
        if url.scheme().lower() in ('data', 'blob', 'about'):
            return True
        if url.isLocalFile() and not url.host():
            try:
                return Path(url.toLocalFile()).resolve().is_relative_to(self.root)
            except (OSError, ValueError, RuntimeError):
                return False
        return False

    def interceptRequest(self, info):
        if not self.allows(info.requestUrl()):
            info.block(True)


class LocalPage(BrowserPage):
    console_diagnostic = None

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        # Only the synthetic CI probe enables this diagnostic callback.
        if self.console_diagnostic is not None:
            self.console_diagnostic(f'JS console line {line_number}: {message}')
        super().javaScriptConsoleMessage(level, message, line_number, source_id)

    def __init__(self, profile, policy, parent):
        super().__init__(profile, parent)
        self.policy = policy
        self.accounting_path = None

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if self.accounting_path is not None:
            try:
                allowed = is_main_frame and url.isLocalFile() and not url.host() and Path(url.toLocalFile()).resolve() == self.accounting_path
            except (OSError, ValueError, RuntimeError):
                allowed = False
        else:
            allowed = self.policy.allows(url)
        if not allowed:
            self.navigation_blocked.emit(url.scheme())
        return allowed


class BrowserSessions(QObject):
    """Profiles live for the application lifetime, longer than their pages."""
    def __init__(self, folder, download_handler):
        super().__init__(QApplication.instance())
        self.folder = Path(folder)
        self.download_handler = download_handler
        self.web = self._new_web_profile()
        self.local_profiles = {}

    def _new_web_profile(self):
        profile = QWebEngineProfile(self)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        profile.setHttpCacheMaximumSize(32 * 1024 * 1024)
        profile.setPermissionPersistencePolicy(QWebEngineProfile.PersistentPermissionsPolicy.AskEveryTime)
        profile.downloadRequested.connect(self.download_handler)
        return profile

    def reset_web(self):
        old = self.web
        self.web = self._new_web_profile()
        old.cookieStore().deleteAllCookies()
        old.clearHttpCache()
        old.deleteLater()

    def _profile_key(self, root):
        key = sha256(str(root).encode('utf-8')).hexdigest()[:32]
        if root != (self.folder / 'accounting').resolve():
            return key
        # Preserve the exact legacy profile path whenever it already exists.
        # A marker keeps the choice independent of a subsequent path change.
        marker = self.folder / 'accounting-profile.json'
        profiles = self.folder / 'local-profiles'
        if marker.exists():
            config = json.loads(marker.read_text(encoding='utf-8'))
            selected = config.get('profile_key')
            if not isinstance(selected, str) or not (selected == 'accounting-v1' or
                (len(selected) == 32 and all(c in '0123456789abcdef' for c in selected))):
                raise ValueError('تنظیمات پروفایل حسابداری خراب است.')
            if not (profiles / selected / 'storage').is_dir() and not (self.folder / 'accounting-data' / 'ledger.db').exists():
                raise ValueError('پروفایل قدیمی حسابداری یافت نشد؛ ابتدا داده را بازیابی کنید.')
            return selected
        if (profiles / key / 'storage').is_dir():
            selected = key
        elif (profiles / 'accounting-v1' / 'storage').is_dir():
            selected = 'accounting-v1'
        elif (self.folder / 'accounting-data' / 'ledger.db').exists():
            selected = 'accounting-v1'
        else:
            # A moved legacy data directory may contain a differently hashed
            # profile. Do not guess which of several profiles contains finances.
            candidates = [p for p in profiles.glob('*') if p.is_dir() and (p / 'storage').is_dir()]
            if candidates:
                raise ValueError('پروفایل قدیمی با مسیر فعلی تطابق ندارد. برای جلوگیری از افتتاح دفتر خالی، ابتدا از نسخه قبلی پشتیبان حسابداری بگیرید یا مسیر را بازیابی کنید.')
            selected = 'accounting-v1'
        # Create the directory first so an interrupted first start is recoverable.
        (profiles / selected / 'storage').mkdir(parents=True, exist_ok=True)
        atomic_write(marker, json.dumps({'profile_key': selected}).encode('utf-8'))
        return selected

    def local(self, root):
        root = Path(root).resolve()
        if root not in self.local_profiles:
            key = self._profile_key(root)
            profile = QWebEngineProfile('JavanLocal-' + key, self)
            profile.setPersistentStoragePath(str(self.folder / 'local-profiles' / key / 'storage'))
            profile.setCachePath(str(self.folder / 'local-profiles' / key / 'cache'))
            profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
            policy = LocalPolicy(root, profile)
            profile.setUrlRequestInterceptor(policy)
            profile.downloadRequested.connect(self.download_handler)
            self.local_profiles[root] = (profile, policy)
        return self.local_profiles[root]


class BrowserView(QWebEngineView):
    status_message = Signal(str)
    popup_requested = Signal(object, object)

    def __init__(self, sessions, root=None, parent=None):
        super().__init__(parent)
        self.root = Path(root).resolve() if root is not None else None
        self.home = False
        self.link_id = None
        self.loading = False
        self.progress_value = 0
        self.last_status = 'آماده'
        if self.root is None:
            page = BrowserPage(sessions.web, self)
        else:
            profile, policy = sessions.local(self.root)
            page = LocalPage(profile, policy, self)
        self.setPage(page)
        settings = page.settings()
        A = QWebEngineSettings.WebAttribute
        settings.setAttribute(A.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(A.LocalContentCanAccessFileUrls, self.root is not None)
        settings.setAttribute(A.LocalStorageEnabled, True)
        settings.setAttribute(A.JavascriptCanOpenWindows, self.root is None)
        settings.setAttribute(A.PluginsEnabled, True)
        settings.setAttribute(A.PdfViewerEnabled, True)
        page.navigation_blocked.connect(lambda scheme: self.status_message.emit('دسترسی به این آدرس مسدود است: ' + scheme))
        page.newWindowRequested.connect(lambda request: self.popup_requested.emit(self, request))
        page.renderProcessTerminated.connect(self._renderer_stopped)
        page.certificateError.connect(self._reject_certificate)
        page.permissionRequested.connect(self._permission_requested)

    def _reject_certificate(self, error):
        error.rejectCertificate()
        self.status_message.emit('گواهی امنیتی سایت معتبر نیست؛ دسترسی مسدود شد.')

    def _renderer_stopped(self, status, code):
        LOGGER.warning('WebEngine renderer stopped; status=%s code=%d', status.name, code)
        self.status_message.emit('پردازش مرورگر متوقف شد؛ در صورت نیاز صفحه را دوباره بارگذاری کنید.')

    def _permission_requested(self, permission):
        from PySide6.QtWebEngineCore import QWebEnginePermission
        allowed = {
            QWebEnginePermission.PermissionType.MediaAudioCapture: 'میکروفون',
            QWebEnginePermission.PermissionType.MediaVideoCapture: 'دوربین',
            QWebEnginePermission.PermissionType.MediaAudioVideoCapture: 'دوربین و میکروفون',
        }
        origin = permission.origin()
        kind = allowed.get(permission.permissionType())
        if self.root is None and kind and origin.scheme() == 'https' and origin.host():
            if ask(self, 'اجازه دسترسی به ' + kind + ' برای ' + origin.host() + ' در این نشست؟'):
                permission.grant()
                return
        permission.deny()


    def navigate(self, address):
        url = QUrl(address)
        if self.root is not None or not url.isValid() or url.scheme().lower() not in ('http', 'https') or not url.host() or url.userInfo():
            raise ValueError('آدرس اینترنتی معتبر نیست.')
        self.home = False
        self.setUrl(url)

    def open_local(self, address):
        path = Path(address).resolve()
        if self.root is None or not path.is_relative_to(self.root) or not path.is_file() or path.suffix.lower() not in ('.html', '.htm'):
            raise ValueError('فایل HTML معتبر یافت نشد.')
        self.home = False
        self.setUrl(QUrl.fromLocalFile(str(path)))

    def show_home(self):
        if self.root is not None:
            raise ValueError('صفحه اصلی باید در زبانه وب باز شود.')
        self.home = True
        self.link_id = None
        self.setHtml(HOME_HTML)
