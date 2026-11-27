"""RTL dialogs for catalog CRUD and backup."""
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from .catalog import Link, group_links
from .storage import read_state

YES = QMessageBox.StandardButton.Yes
NO = QMessageBox.StandardButton.No


def warn(parent, text):
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle('کافینت جوان')
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(text)
    box.exec()


def ask(parent, text):
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle('تأیید عملیات')
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(text)
    box.setStandardButtons(YES | NO)
    box.setDefaultButton(NO)
    return box.exec() == YES


class LinkDialog(QDialog):
    def __init__(self, categories, link=None, parent=None):
        super().__init__(parent)
        self.original = link
        self.result_link = None
        self.setWindowTitle('ویرایش لینک' if link else 'افزودن لینک یا فایل HTML')
        self.resize(580, 320)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title = QLineEdit(link.title if link else '')
        self.title.setMaxLength(200)
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.addItems(list(dict.fromkeys([*categories, 'ابزارهای محلی HTML'])))
        self.category.setCurrentText(link.category if link else 'خدمات دولتی')
        self.category.lineEdit().setMaxLength(120)
        self.kind = QComboBox()
        self.kind.addItem('آدرس اینترنتی', 'web')
        self.kind.addItem('فایل HTML محلی', 'html')
        self.address = QLineEdit(link.url if link else '')
        self.address.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.address.setMaxLength(8192)
        self.browse = QPushButton('انتخاب فایل HTML…')
        self.browse.clicked.connect(self.choose_file)
        address_row = QWidget()
        row = QHBoxLayout(address_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.address, 1)
        row.addWidget(self.browse)
        self.description = QLineEdit(link.description if link else '')
        self.description.setMaxLength(2000)
        form.addRow('نام سامانه', self.title)
        form.addRow('دسته‌بندی (قابل تایپ)', self.category)
        form.addRow('نوع لینک', self.kind)
        form.addRow('آدرس / مسیر', address_row)
        form.addRow('توضیحات', self.description)
        layout.addLayout(form)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('ذخیره')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('انصراف')
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.kind.currentIndexChanged.connect(self.kind_changed)
        if link:
            self.kind.setCurrentIndex(self.kind.findData(link.kind))
        self.kind_changed()

    def kind_changed(self, *_):
        local = self.kind.currentData() == 'html'
        self.browse.setVisible(local)
        self.address.setPlaceholderText('C:/Tools/tool.html' if local else 'https://example.com')
        self.hint.setText('فقط فایل HTML مورد اعتماد؛ دسترسی اینترنت برای ابزار محلی مسدود است. فایل در مسیر اصلی باقی می‌ماند.' if local else 'آدرس را با https:// وارد کنید. دسته‌بندی جدید را می‌توانید تایپ کنید.')

    def choose_file(self):
        name, _ = QFileDialog.getOpenFileName(self, 'انتخاب فایل HTML', '', 'HTML (*.html *.htm)')
        if name:
            path = Path(name).resolve()
            self.address.setText(str(path))
            if not self.title.text().strip():
                self.title.setText(path.stem)
            if not self.original:
                self.category.setCurrentText('ابزارهای محلی HTML')

    def save(self):
        try:
            kind = self.kind.currentData()
            address = self.address.text().strip()
            if kind == 'web' and address and '://' not in address and ':' not in address.split('/')[0]:
                address = 'https://' + address
            link = Link(self.original.id if self.original else uuid4().hex,
                        self.title.text().strip(), address, self.category.currentText().strip(),
                        self.description.text().strip(), kind)
            if kind == 'html' and not Path(address).is_file():
                raise ValueError('فایل HTML در مسیر مشخص‌شده وجود ندارد.')
        except (ValueError, OSError) as exc:
            warn(self, 'اطلاعات نامعتبر است.\n' + str(exc))
            return
        self.result_link = link
        self.accept()


class ManagerDialog(QDialog):
    changed = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle('مدیریت لینک‌ها و پشتیبان‌گیری')
        self.resize(860, 510)
        layout = QVBoxLayout(self)
        heading = QLabel('مدیریت میز کار | لینک‌های اینترنتی و ابزارهای محلی')
        heading.setObjectName('managerHeading')
        layout.addWidget(heading)
        tools = QHBoxLayout()
        for title, callback in [('＋ افزودن', self.add), ('ویرایش', self.edit), ('حذف', self.delete),
                                ('پشتیبان‌گیری', self.export), ('بازیابی', self.restore)]:
            button = QPushButton(title)
            button.setObjectName('managerAction')
            button.clicked.connect(callback)
            tools.addWidget(button)
        layout.addLayout(tools)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['نام', 'دسته', 'نوع', 'آدرس / مسیر'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 155)
        self.table.setColumnWidth(2, 90)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit())
        layout.addWidget(self.table, 1)
        self.info = QLabel()
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        close = QPushButton('بستن')
        close.clicked.connect(self.accept)
        layout.addWidget(close)
        self.refresh()

    def refresh(self):
        links = self.store.state.links
        self.table.setRowCount(len(links))
        for row, link in enumerate(links):
            for col, value in enumerate((link.title, link.category, 'HTML محلی' if link.kind == 'html' else 'وب', link.url)):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, link.id)
                self.table.setItem(row, col, item)
        self.info.setText(f'{len(links)} لینک | تغییرات پس از هر عملیات موفق ذخیره می‌شوند. حذف لینک، فایل اصلی HTML را پاک نمی‌کند.')

    def selected(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        if item is None:
            warn(self, 'ابتدا یک لینک را انتخاب کنید.')
            return None
        return next((x for x in self.store.state.links if x.id == item.data(Qt.ItemDataRole.UserRole)), None)

    def apply(self, operation):
        try:
            operation()
        except (OSError, ValueError) as exc:
            warn(self, 'عملیات انجام نشد. اطلاعات قبلی حفظ شده است.\n' + str(exc))
            return
        self.refresh()
        self.changed.emit()

    def add(self):
        dialog = LinkDialog(group_links(self.store.state.links), parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply(lambda: self.store.add(dialog.result_link))

    def edit(self):
        link = self.selected()
        if link is None:
            return
        dialog = LinkDialog(group_links(self.store.state.links), link, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply(lambda: self.store.edit(dialog.result_link))

    def delete(self):
        link = self.selected()
        if link and ask(self, f'لینک «{link.title}» حذف شود؟ فایل اصلی حذف نمی‌شود.'):
            self.apply(lambda: self.store.delete(link.id))

    def export(self):
        name, _ = QFileDialog.getSaveFileName(self, 'ذخیره پشتیبان', 'JavanLinks-backup.json', 'JSON (*.json)')
        if not name:
            return
        try:
            self.store.export(Path(name))
            self.info.setText('پشتیبان JSON ذخیره شد. فایل‌های HTML و داده‌های داخل ابزارها در آن نیستند.')
        except (OSError, ValueError) as exc:
            warn(self, str(exc))

    def restore(self):
        name, _ = QFileDialog.getOpenFileName(self, 'انتخاب پشتیبان', '', 'JSON (*.json)')
        if not name:
            return
        try:
            state = read_state(Path(name))
        except (OSError, ValueError, RecursionError) as exc:
            warn(self, 'فایل پشتیبان معتبر نیست.\n' + str(exc))
            return
        missing = sum(x.kind == 'html' and not Path(x.url).is_file() for x in state.links)
        if ask(self, f'{len(state.links)} لینک جایگزین فهرست فعلی شود؟\n{missing} فایل محلی در این سیستم یافت نشد.\nنسخه قبلی به‌صورت خودکار ذخیره می‌شود.'):
            self.apply(lambda: self.store.restore(state))
