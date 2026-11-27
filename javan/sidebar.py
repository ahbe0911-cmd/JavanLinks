from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QFrame, QLabel, QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout

from .catalog import Link, filter_links, group_links


class Sidebar(QFrame):
    link_selected = Signal(object)

    def __init__(self, links: tuple[Link, ...], parent=None):
        super().__init__(parent)
        self.setObjectName('sidebar')
        self.setFixedWidth(310)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._links = tuple(links)
        self._active_id: str | None = None
        self._lookup = {link.id: link for link in links}
        if len(self._lookup) != len(links):
            raise ValueError('Duplicate link IDs')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 16)
        layout.setSpacing(13)

        brand = QFrame()
        brand.setObjectName('brand')
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(12, 15, 12, 15)
        name = QLabel('کافینت جوان')
        name.setObjectName('brandTitle')
        subtitle = QLabel('میز کار خدمات اینترنتی')
        subtitle.setObjectName('brandSub')
        brand_layout.addWidget(name)
        brand_layout.addWidget(subtitle)
        layout.addWidget(brand)

        self.search = QLineEdit()
        self.search.setObjectName('search')
        self.search.setPlaceholderText('جستجوی نام سایت یا دسته‌بندی…')
        self.search.setAccessibleName('جستجوی لینک‌ها')
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        heading = QLabel('دسته‌بندی خدمات')
        heading.setObjectName('sectionTitle')
        layout.addWidget(heading)

        self.tree = QTreeWidget()
        self.tree.setObjectName('catalog')
        self.tree.setAccessibleName('فهرست لینک‌های کاربردی')
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.setIndentation(16)
        self.tree.setUniformRowHeights(True)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        layout.addWidget(self.tree, 1)
        self.empty = QLabel('نتیجه‌ای پیدا نشد.')
        self.empty.setObjectName('empty')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty)
        self.count = QLabel()
        self.count.setObjectName('sidebarHint')
        layout.addWidget(self.count)
        self.search.textChanged.connect(self._refresh)
        self.tree.itemClicked.connect(self._activate)
        # Double-click may also emit itemActivated on some platforms. Use only
        # itemClicked for mouse and the tree's keyboard activation for Enter.
        self.tree.itemActivated.connect(self._keyboard_activate)
        self._refresh('')

    def _refresh(self, query: str):
        matches = filter_links(self._links, query)
        self.tree.clear()
        for category, entries in group_links(matches).items():
            group = QTreeWidgetItem([category])
            group.setFlags(Qt.ItemFlag.ItemIsEnabled)
            font = QFont(self.font())
            font.setBold(True)
            group.setFont(0, font)
            group.setForeground(0, QBrush(QColor('#9dc4d9')))
            self.tree.addTopLevelItem(group)
            for link in entries:
                item = QTreeWidgetItem([link.title])
                item.setData(0, Qt.ItemDataRole.UserRole, link.id)
                item.setToolTip(0, f'{link.title}\n{link.url}')
                group.addChild(item)
                if link.id == self._active_id:
                    self.tree.setCurrentItem(item)
            group.setExpanded(True)
        self.tree.setVisible(bool(matches))
        self.empty.setVisible(not matches)
        self.count.setText(f'{len(matches)} لینک از {len(self._links)} لینک نمونه')

    def _activate(self, item, _column):
        link_id = item.data(0, Qt.ItemDataRole.UserRole)
        if link_id in self._lookup:
            if link_id == self._active_id:
                return
            self._active_id = link_id
            self.link_selected.emit(self._lookup[link_id])

    def _keyboard_activate(self, item, column):
        self._activate(item, column)

    def clear_active(self):
        self._active_id = None
        self.tree.clearSelection()
