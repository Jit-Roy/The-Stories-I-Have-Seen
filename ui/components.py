from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QComboBox, QFrame, QSpinBox
from PySide6.QtGui import QPixmap, QImage, QPainter, QPainterPath
from PySide6.QtCore import Qt, QUrl, QRunnable, QThreadPool, Signal, QObject
from PySide6.QtGui import QStandardItemModel, QStandardItem
import requests

from ui.movie_card import ImageLoader

class HorizontalCarousel(QWidget):
    def __init__(self, title, items, card_creator_func, on_view_all=None, custom_header_widget=None):
        super().__init__()
        self.card_creator_func = card_creator_func
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        header_layout.addWidget(title_label)
        
        if custom_header_widget:
            header_layout.addWidget(custom_header_widget)
            
        header_layout.addStretch()
        
        if on_view_all:
            view_all_btn = QPushButton("View all")
            view_all_btn.setStyleSheet("color: #1AE0A1; background: transparent; border: none; font-weight: bold;")
            from ui.theme_manager import ThemeManager
            view_all_btn.setStyleSheet(ThemeManager.format_style(view_all_btn.styleSheet()))
            view_all_btn.setCursor(Qt.PointingHandCursor)
            view_all_btn.clicked.connect(on_view_all)
            header_layout.addWidget(view_all_btn)
            
        layout.addLayout(header_layout)
        
        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedHeight(300)
        scroll.setStyleSheet("border: none; background: transparent;")
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self.h_layout = QHBoxLayout(container)
        self.h_layout.setAlignment(Qt.AlignLeft)
        
        self.update_items(items)
            
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def update_items(self, items):
        # Clear existing
        while self.h_layout.count():
            item = self.h_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        # Add new
        for item in items:
            self.h_layout.addWidget(self.card_creator_func(item))

    def refresh_status(self):
        import tmdb_api
        from ui.movie_card import MovieCard
        db_cache = tmdb_api._get_db_status_map()
        
        for i in range(self.h_layout.count()):
            item = self.h_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, MovieCard):
                    movie_id = widget.movie_data.get("id")
                    widget.movie_data["status"] = db_cache.get(movie_id)
                    widget.update_buttons()

class SegmentedToggle(QWidget):
    toggled = Signal(str)
    
    def __init__(self, option1, option2):
        super().__init__()
        self.opt1 = option1
        self.opt2 = option2
        self.current = option1
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 0, 0)
        layout.setSpacing(0)
        
        self.container = QFrame()
        self.container.setStyleSheet("""
            QFrame {
                border: 1px solid #2D3748;
                border-radius: 15px;
                background-color: transparent;
            }
        """)
        container_layout = QHBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        self.btn1 = QPushButton(option1)
        self.btn2 = QPushButton(option2)
        
        for btn in (self.btn1, self.btn2):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(30)
            btn.clicked.connect(self._on_click)
            
        self.btn1.setStyleSheet(self._get_style(True, True))
        self.btn2.setStyleSheet(self._get_style(False, False))
        
        container_layout.addWidget(self.btn1)
        container_layout.addWidget(self.btn2)
        
        layout.addWidget(self.container)
        
    def _get_style(self, is_active, is_left):
        radius = "border-top-left-radius: 15px; border-bottom-left-radius: 15px;" if is_left else "border-top-right-radius: 15px; border-bottom-right-radius: 15px;"
        bg = "#1A1C23" # Active color (dark blue/purple tint)
        color = "#1AE0A1" # TMDB style teal highlight
        if not is_active:
            bg = "transparent"
            color = "#A0AEC0"
        from ui.theme_manager import ThemeManager
        return ThemeManager.format_style(f"""
            QPushButton {{
                background-color: {bg};
                color: {color};
                border: none;
                padding: 0px 20px;
                font-weight: bold;
                {radius}
            }}
        """)

    def _on_click(self):
        sender = self.sender()
        if sender == self.btn1 and self.current != self.opt1:
            self.set_current(self.opt1)
            self.toggled.emit(self.opt1)
        elif sender == self.btn2 and self.current != self.opt2:
            self.set_current(self.opt2)
            self.toggled.emit(self.opt2)

    def set_current(self, value):
        if value == self.opt1 and self.current != self.opt1:
            self.current = self.opt1
            self.btn1.setStyleSheet(self._get_style(True, True))
            self.btn2.setStyleSheet(self._get_style(False, False))
        elif value == self.opt2 and self.current != self.opt2:
            self.current = self.opt2
            self.btn1.setStyleSheet(self._get_style(False, True))
            self.btn2.setStyleSheet(self._get_style(True, False))

class HeroBanner(QWidget):
    def __init__(self, movie, on_explore, on_status_change=None):
        super().__init__()
        self.movie = movie
        self.on_status_change = on_status_change
        self.setObjectName("heroBanner")
        self.setFixedHeight(350)
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignBottom | Qt.AlignLeft)
        layout.setContentsMargins(40, 40, 40, 40)
        
        title = QLabel(movie.get("title", ""))
        title.setObjectName("heroTitle")
        
        info_text = f"⭐ {movie.get('vote_average', 'N/A')}   {movie.get('release_date', '')[:4]}"
        info = QLabel(info_text)
        info.setObjectName("heroInfo")
        
        btn_layout = QHBoxLayout()
        explore_btn = QPushButton("▶ Explore Now")
        explore_btn.setStyleSheet("""
            QPushButton { background-color: #1AE0A1; color: #0F172A; padding: 10px 20px; border-radius: 6px; font-weight: bold; font-size: 14px; }
            QPushButton:hover { background-color: #14B885; }
        """)
        from ui.theme_manager import ThemeManager
        explore_btn.setStyleSheet(ThemeManager.format_style(explore_btn.styleSheet()))
        explore_btn.clicked.connect(lambda: on_explore(movie))
        
        self.wishlist_btn = QPushButton()
        self.wishlist_btn.clicked.connect(lambda checked=False: self.on_action_click())
        
        btn_layout.addWidget(explore_btn)
        btn_layout.addWidget(self.wishlist_btn)
        btn_layout.addStretch()
        
        self.update_buttons()
        
        layout.addWidget(title)
        layout.addWidget(info)
        layout.addSpacing(10)
        layout.addLayout(btn_layout)
        
        self.load_backdrop()

    def on_action_click(self):
        status = self.movie.get("status")
        new_status = "remove" if status == "watch_later" else "watch_later"
        if self.on_status_change:
            self.on_status_change(self.movie, new_status)
        self.update_buttons()

    def update_buttons(self):
        status = self.movie.get("status")
        if status == "watch_later":
            self.wishlist_btn.setText("✓ Wishlisted")
            self.wishlist_btn.setStyleSheet("""
                QPushButton { background: transparent; border: 1px solid #1AE0A1; color: #1AE0A1; padding: 10px 20px; border-radius: 6px; font-weight: bold; font-size: 14px; }
                QPushButton:hover { background: rgba(26, 224, 161, 0.1); }
            """)
        else:
            self.wishlist_btn.setText("+ Add to Wishlist")
            self.wishlist_btn.setStyleSheet("""
                QPushButton { background: transparent; border: 1px solid #A0AEC0; color: #A0AEC0; padding: 10px 20px; border-radius: 6px; font-weight: bold; font-size: 14px; }
                QPushButton:hover { background: rgba(255,255,255,0.1); border-color: white; color: white; }
            """)
            
        from ui.theme_manager import ThemeManager
        self.wishlist_btn.setStyleSheet(ThemeManager.format_style(self.wishlist_btn.styleSheet()))

    def paintEvent(self, event):
        from PySide6.QtGui import QColor, QPainter, QImage, QPixmap
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        if hasattr(self, "_bg_pixmap") and not self._bg_pixmap.isNull():
            # Scale dynamically to the current size, keeping aspect ratio by expanding
            scaled = self._bg_pixmap.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            
            # Center the image to crop evenly
            x = (scaled.width() - self.width()) // 2
            y = (scaled.height() - self.height()) // 2
            
            painter.drawPixmap(0, 0, self.width(), self.height(), scaled, x, y, self.width(), self.height())
            
        # Draw the dark overlay for text readability
        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))
        painter.end()
        super().paintEvent(event)
        
    def load_backdrop(self):
        url = self.movie.get("backdrop_path")
        if not url:
            return
            
        # Fast path: serve from cache synchronously
        from ui.movie_card import ImageLoader
        cached = ImageLoader.get_cached_image(url)
        if cached:
            self.on_image_loaded(cached)
            return
            
        loader = ImageLoader(url)
        loader.signals.finished.connect(self.on_image_loaded)
        QThreadPool.globalInstance().start(loader)
            
    def on_image_loaded(self, image_data):
        from PySide6.QtGui import QImage, QPixmap
        if image_data:
            img = QImage()
            if img.loadFromData(image_data):
                self._bg_pixmap = QPixmap(img)
                self.update()
        else:
            if not hasattr(self, "image_retries"):
                self.image_retries = 3
            if self.image_retries > 0:
                self.image_retries -= 1
                from PySide6.QtCore import QTimer
                QTimer.singleShot(1000, self.load_backdrop)

class HeroCarousel(QWidget):
    def __init__(self, movies, on_explore, on_status_change=None):
        self.on_status_change = on_status_change  # kept for refresh
        super().__init__()
        self.movies = movies
        self.setFixedHeight(350)
        self.current_idx = 0
        
        # Inner sliding container
        self.inner = QWidget(self)
        self.inner_layout = QHBoxLayout(self.inner)
        self.inner_layout.setContentsMargins(0, 0, 0, 0)
        self.inner_layout.setSpacing(0)
        
        self.slides = []
        movies_with_clone = movies + [movies[0]] if movies else []
        for m in movies_with_clone:
            slide = HeroBanner(m, on_explore, on_status_change)
            self.inner_layout.addWidget(slide)
            self.slides.append(slide)
            
        # Main layout for overlaying dots
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 20)
        main_layout.addStretch()
        
        # Dots
        self.dots_layout = QHBoxLayout()
        self.dots_layout.setAlignment(Qt.AlignCenter)
        self.dots_layout.setSpacing(10)
        
        self.dots = []
        for i in range(len(movies)):
            dot = QPushButton()
            dot.setFixedSize(12, 12)
            dot.setCursor(Qt.PointingHandCursor)
            dot.clicked.connect(lambda checked=False, idx=i: self.slide_to(idx, restart_timer=True))
            self.dots_layout.addWidget(dot)
            self.dots.append(dot)
            
        self.update_dots()
        main_layout.addLayout(self.dots_layout)
        
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QTimer
        self.anim = QPropertyAnimation(self.inner, b"pos")
        self.anim.setDuration(600)
        self.anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.anim.finished.connect(self._on_anim_finished)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next_slide)
        self.timer.start(6000)
        
    def _on_anim_finished(self):
        if self.current_idx == len(self.movies):
            # We reached the cloned slide at the end, snap back instantly to index 0
            self.current_idx = 0
            self.inner.move(-self.width() * 0, 0)
        
    def update_dots(self):
        real_idx = self.current_idx % len(self.movies) if self.movies else 0
        for i, dot in enumerate(self.dots):
            if i == real_idx:
                dot.setStyleSheet("background-color: #1AE0A1; border-radius: 6px; border: none;")
            else:
                dot.setStyleSheet("background-color: #4A5568; border-radius: 6px; border: none;")
                
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.movies: return
        self.inner.resize(self.width() * (len(self.movies) + 1), self.height())
        for slide in self.slides:
            slide.setFixedSize(self.width(), self.height())
        self.inner.move(-self.width() * self.current_idx, 0)
        
    def next_slide(self):
        if not self.movies: return
        # Advance by 1, allowing it to hit the cloned slide at len(self.movies)
        target_idx = self.current_idx + 1
        self.slide_to(target_idx, restart_timer=False)
        
    def slide_to(self, idx, restart_timer=False):
        self.current_idx = idx
        self.update_dots()
        from PySide6.QtCore import QPoint
        self.anim.setEndValue(QPoint(-self.width() * self.current_idx, 0))
        self.anim.start()
        if restart_timer:
            self.timer.start(6000)

    def refresh_status(self):
        """Re-read DB status for every slide and update their buttons."""
        import tmdb_api
        db_map = {m["id"]: m["status"] for m in __import__("database").get_movies()}
        for slide in self.slides:
            slide.movie["status"] = db_map.get(slide.movie["id"])
            slide.update_buttons()

from PySide6.QtWidgets import QGridLayout

class FlowLayout(QGridLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSpacing(15)
        self._widgets = []
        self._current_columns = 0
        
    def add_widget(self, widget):
        self._widgets.append(widget)
        # Reflow will be triggered by the scroll area resize event
        
    def clear(self):
        while self.count():
            item = self.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._widgets.clear()
        self._current_columns = 0
        
    def reflow(self, width=None):
        if width is None:
            if not self.parentWidget(): return
            width = self.parentWidget().width()
            
        if width <= 0: return
        
        columns = max(1, width // 220)
        
        # Don't reflow if columns haven't changed and widget count is the same
        if columns == self._current_columns and self.count() == len(self._widgets):
            return
            
        self._current_columns = columns
        
        # Take everything out of the grid
        while self.count():
            self.takeAt(0)
            
        # Re-add with new columns
        for i, widget in enumerate(self._widgets):
            row = i // columns
            col = i % columns
            self.addWidget(widget, row, col)

class ResizableScrollArea(QScrollArea):
    def __init__(self, flow_layout):
        super().__init__()
        self.flow_layout = flow_layout
        self.setWidgetResizable(True)
        self.setStyleSheet("border: none; background: transparent;")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.viewport():
            self.flow_layout.reflow(self.viewport().width())

class FilterComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import Qt
        self.view().setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view().setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view().setTextElideMode(Qt.ElideRight)
        self.currentTextChanged.connect(self._on_text_changed)

    def _on_text_changed(self, text):
        self.updateGeometry()

    def sizeHint(self):
        from PySide6.QtGui import QFont, QFontMetrics
        font = QFont(self.font().family())
        font.setPointSize(10)
        font.setWeight(QFont.Weight.DemiBold)
        fm = QFontMetrics(font)
        
        text = self.currentText()
        if not text:
            text = "      "
            
        text_width = fm.horizontalAdvance(text)
        # 65px buffer accounts for left/right padding, arrow width, and Qt internal frame margins
        width = text_width + 65
        size = super().sizeHint()
        size.setWidth(width)
        return size

    def minimumSizeHint(self):
        return self.sizeHint()
        
class SearchableComboBox(FilterComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(False)
        from PySide6.QtWidgets import QMenu, QWidgetAction, QLineEdit, QListWidget, QWidget, QVBoxLayout
        from PySide6.QtCore import Qt
        
        self.search_menu = QMenu(self)
        self.search_menu.setStyleSheet("""
            QMenu {
                background-color: #0F121A;
                border: 1px solid #1E2840;
                border-radius: 10px;
                padding: 4px;
            }
        """)
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search...")
        self.search_edit.setStyleSheet("""
            QLineEdit {
                background-color: #141720;
                color: #C4D0E0;
                border: 1px solid #242D42;
                border-radius: 6px;
                padding: 6px;
                margin: 4px;
            }
            QLineEdit:focus {
                border: 1px solid #374D6B;
            }
        """)
        
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                color: #C4D0E0;
                border: none;
                outline: 0;
            }
            QListWidget::item {
                min-height: 34px;
                padding-left: 12px;
                border-radius: 6px;
            }
            QListWidget::item:hover {
                background-color: #1C2030;
                color: #DCE8F4;
            }
            QListWidget::item:selected {
                background-color: #1AE0A1;
                color: #07111E;
            }
        """)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setTextElideMode(Qt.ElideRight)
        self.list_widget.setFixedHeight(250)
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.search_edit)
        layout.addWidget(self.list_widget)
        
        action = QWidgetAction(self)
        action.setDefaultWidget(container)
        self.search_menu.addAction(action)
        
        self.search_edit.textChanged.connect(self._filter_items)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        
    def showPopup(self):
        from PySide6.QtWidgets import QListWidget
        self.search_edit.clear()
        
        # Force the menu and the list widget to respect the exact button width
        w = self.width()
        self.search_menu.setFixedWidth(w)
        self.list_widget.setMaximumWidth(w)
        
        self.search_menu.popup(self.mapToGlobal(self.rect().bottomLeft()))
        
        # Scroll to and highlight the currently selected item
        curr_text = self.currentText()
        if curr_text:
            from PySide6.QtCore import Qt
            items = self.list_widget.findItems(curr_text, Qt.MatchExactly)
            if items:
                self.list_widget.setCurrentItem(items[0])
                self.list_widget.scrollToItem(items[0], QListWidget.PositionAtCenter)
                
        self.search_edit.setFocus()
        
    def addItem(self, text, data=None):
        super().addItem(text, data)
        from PySide6.QtWidgets import QListWidgetItem
        item = QListWidgetItem(text)
        item.setToolTip(text)
        self.list_widget.addItem(item)
        
    def _filter_items(self, text):
        text = text.lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(text not in item.text().lower())
            
    def _on_item_clicked(self, item):
        idx = self.list_widget.row(item)
        self.setCurrentIndex(idx)
        self.search_menu.hide()

class MultiSelectComboBox(FilterComboBox):
    def __init__(self, placeholder="Select Options", parent=None):
        super().__init__(parent)
        self.placeholder = placeholder
        self.model = QStandardItemModel()
        self.setModel(self.model)
        
        placeholder_item = QStandardItem(self.placeholder)
        placeholder_item.setFlags(Qt.NoItemFlags)
        self.model.appendRow(placeholder_item)
        
        self.view().viewport().installEventFilter(self)
        self.model.itemChanged.connect(self._on_item_changed)
        
    def addItem(self, text, data=None):
        item = QStandardItem(text)
        item.setToolTip(text)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        item.setData(Qt.Unchecked, Qt.CheckStateRole)
        item.setData(data, Qt.UserRole)
        self.model.appendRow(item)
        
    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj == self.view().viewport():
            if event.type() == QEvent.Type.MouseButtonRelease:
                index = self.view().indexAt(event.pos())
                if index.isValid() and index.row() > 0:
                    item = self.model.itemFromIndex(index)
                    if item.flags() & Qt.ItemIsUserCheckable:
                        new_state = Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
                        item.setCheckState(new_state)
                    return True
        return super().eventFilter(obj, event)

    def hidePopup(self):
        super().hidePopup()
        self.setCurrentIndex(0)

    def _on_item_changed(self, item):
        if item.row() > 0:
            self._update_text()

    def _update_text(self):
        count = len(self.currentDataList())
        if count > 0:
            self.model.item(0).setText(f"{count} Genres Selected")
        else:
            self.model.item(0).setText(self.placeholder)
        self.setCurrentIndex(0)
        self.updateGeometry()
        
    def currentDataList(self):
        res = []
        for i in range(1, self.model.rowCount()):
            item = self.model.item(i)
            if item.checkState() == Qt.Checked:
                res.append(item.data(Qt.UserRole))
        return res
        
    def setChecked(self, data_list):
        str_data_list = [str(x) for x in data_list]
        self.model.blockSignals(True)
        for i in range(1, self.model.rowCount()):
            item = self.model.item(i)
            if str(item.data(Qt.UserRole)) in str_data_list:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
        self.model.blockSignals(False)
        self._update_text()
        
    def count(self):
        return self.model.rowCount()

class DiscoverFilterBarSignals(QObject):
    filters_applied = Signal(dict)

GLOBAL_FILTER_STATE = {}

class DiscoverFilterBar(QWidget):
    def __init__(self):
        super().__init__()
        self.signals = DiscoverFilterBarSignals()
        self.base_params = {}
        self._pending_params = {}

        # ── Design tokens ─────────────────────────────────────────────────────
        BASE       = "#141720"   # control resting background
        BASE_HVR   = "#1C2030"   # hovered control
        BASE_OPEN  = "#11141C"   # combo open / active
        BORDER     = "#242D42"   # resting border
        BORDER_HVR = "#374D6B"   # hovered border
        ACCENT     = "#1AE0A1"   # primary accent / focus ring
        ACCENT2    = "#0EC8D8"   # gradient second stop
        ACCENT_DK  = "#13BC89"   # accent pressed / hover
        TEXT       = "#C4D0E0"   # control primary text
        TEXT_MUTED = "#40506A"   # label "FROM" / "TO"
        TEXT_SEL   = "#07111E"   # text on accent selection
        POPUP_BG   = "#0F121A"   # dropdown popup bg
        POPUP_BDR  = "#1E2840"   # dropdown popup border
        BTN_TEXT   = "#061018"   # discover button text

        import os
        svg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons", "down_arrow.svg").replace("\\", "/")

        # ── Shared combo style ─────────────────────────────────────────────────
        combo_style = f"""
            QComboBox {{
                background-color: {BASE};
                border: 1px solid {BORDER};
                color: {TEXT};
                padding: 6px 26px 6px 12px;
                border-radius: 10px;
                font-weight: 600;
                font-size: 10pt;
                selection-background-color: transparent;
            }}
            QComboBox:hover {{
                border-color: {BORDER_HVR};
                background-color: {BASE_HVR};
                color: #DCE8F4;
            }}
            QComboBox:focus {{
                border: 1px solid {BORDER_HVR};
                color: #DCE8F4;
            }}
            QComboBox:on {{
                border: 1px solid {BORDER_HVR};
                background-color: {BASE_OPEN};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 26px;
                border: none;
            }}
            QComboBox::down-arrow {{
                image: url("{svg_path}");
                width: 12px;
                height: 12px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {POPUP_BG};
                color: {TEXT};
                selection-background-color: {ACCENT};
                selection-color: {TEXT_SEL};
                border: 1px solid {POPUP_BDR};
                border-radius: 10px;
                padding: 5px;
                outline: 0;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 34px;
                padding-left: 12px;
                border-radius: 6px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {BASE_HVR};
                color: #DCE8F4;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: {ACCENT};
                color: {TEXT_SEL};
            }}
        """

        year_combo_style = combo_style.replace("padding: 6px 26px 6px 12px;", "padding: 6px 20px 6px 10px;")

        # ── Year range labels ──────────────────────────────────────────────────
        label_style = f"""
            QLabel {{
                color: {TEXT_MUTED};
                font-size: 10px;
                font-weight: 700;
            }}
        """

        # ── Thin vertical separator ────────────────────────────────────────────
        def make_sep():
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.VLine)
            sep.setFixedSize(1, 20)
            sep.setStyleSheet(f"background-color: #1C2535; border: none;")
            return sep

        # ── Controls ───────────────────────────────────────────────────────────

        # SHOW ME
        self.show_me_combo = FilterComboBox()
        self.show_me_combo.setStyleSheet(combo_style)
        self.show_me_combo.addItem("Everything", "all")
        self.show_me_combo.addItem("Movies I Haven't Seen", "unseen")

        # GENRES (multi-select, styled identically)
        self.genre_combo = MultiSelectComboBox("All Genres")
        self.genre_combo.setStyleSheet(combo_style)

        # SORT
        self.sort_combo = FilterComboBox()
        self.sort_combo.setStyleSheet(combo_style)
        self.sort_combo.addItem("Most Popular",       "popularity.desc")
        self.sort_combo.addItem("Highest Rated",      "vote_average.desc")
        self.sort_combo.addItem("Newest Releases",    "primary_release_date.desc")
        self.sort_combo.addItem("Highest Revenue",    "revenue.desc")

        # COUNTRY
        self.country_combo = SearchableComboBox()
        self.country_combo.setStyleSheet(combo_style)
        self.country_combo.setMinimumWidth(160)
        self.country_combo.addItem("Any Country", None)

        # LANGUAGE
        self.language_combo = SearchableComboBox()
        self.language_combo.setStyleSheet(combo_style)
        self.language_combo.setMinimumWidth(160)
        self.language_combo.addItem("Any Language", None)
        
        # ── YEAR RANGE
        import datetime
        current_year = datetime.datetime.now().year        # YEAR (FROM / TO)
        self.from_year = FilterComboBox()
        self.to_year   = FilterComboBox()

        for combo in (self.from_year, self.to_year):
            combo.setStyleSheet(year_combo_style)
            combo.setMaxVisibleItems(8)
            combo.addItem("Any", None)
            for y in range(current_year + 5, 1899, -1):
                combo.addItem(str(y), y)

        self.from_year.setCurrentIndex(0)
        self.to_year.setCurrentIndex(0)

        from_label = QLabel("FROM")
        to_label   = QLabel("TO")
        
        from PySide6.QtWidgets import QSizePolicy
        
        for lbl in (from_label, to_label):
            lbl.setStyleSheet(label_style)
            lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            
        for combo in (self.from_year, self.to_year):
            combo.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

        year_layout = QHBoxLayout()
        year_layout.setSpacing(6)
        year_layout.setContentsMargins(0, 0, 0, 0)
        year_layout.addWidget(from_label)
        year_layout.addWidget(self.from_year)
        year_layout.addWidget(to_label)
        year_layout.addWidget(self.to_year)

        # RATING
        self.rating_combo = FilterComboBox()
        self.rating_combo.setStyleSheet(combo_style)
        self.rating_combo.setMaxVisibleItems(8)
        self.rating_combo.addItem("Any Rating", None)
        for i in range(9, 0, -1):
            self.rating_combo.addItem(f"{i}+  ★ Stars", float(i))

        # DISCOVER BUTTON — gradient, no border, strong presence
        self.discover_btn = QPushButton("Discover")
        self.discover_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {ACCENT},
                    stop:1 {ACCENT2}
                );
                color: {BTN_TEXT};
                border-radius: 10px;
                padding: 8px 18px;
                font-weight: 700;
                font-size: 10pt;
                border: none;
            }}
            QPushButton:hover {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {ACCENT_DK},
                    stop:1 #0AB6C4
                );
            }}
            QPushButton:pressed {{
                background-color: {ACCENT_DK};
                padding-top: 10px;
                padding-bottom: 8px;
            }}
        """)
        self.discover_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.discover_btn.clicked.connect(self._apply)

        # ── Layout ─────────────────────────────────────────────────────────────
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 1. Scrollable filter container
        scroll_area = QScrollArea()
        scroll_area.setFixedHeight(50)
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
        """)

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        filter_layout = QHBoxLayout(scroll_content)
        filter_layout.setSpacing(10)
        filter_layout.setContentsMargins(0, 0, 0, 0)

        filter_layout.addWidget(self.show_me_combo)
        filter_layout.addWidget(self.genre_combo)
        filter_layout.addWidget(self.sort_combo)
        filter_layout.addWidget(self.country_combo)
        filter_layout.addWidget(self.language_combo)
        filter_layout.addLayout(year_layout)
        filter_layout.addWidget(self.rating_combo)
        filter_layout.addStretch()

        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

        # 2. Bottom row: Discover button
        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(self.discover_btn)
        bottom_layout.addStretch()
        
        main_layout.addLayout(bottom_layout)
        
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    # ── Unchanged logic below ──────────────────────────────────────────────────

    def populate_genres(self, genres):
        if self.genre_combo.count() > 1:
            return
        for genre in genres:
            self.genre_combo.addItem(genre["name"], genre["id"])
        if hasattr(self, '_pending_params') and "with_genres" in self._pending_params:
            genres_list = [int(x) for x in self._pending_params["with_genres"].split(",")]
            self.genre_combo.setChecked(genres_list)

    def populate_languages(self, languages):
        if self.language_combo.count() > 1:
            return
        for lang in languages:
            self.language_combo.addItem(lang.get("english_name", ""), lang.get("iso_639_1", ""))
        if hasattr(self, '_pending_params') and "with_original_language" in self._pending_params:
            idx = self.language_combo.findData(self._pending_params["with_original_language"])
            self.language_combo.setCurrentIndex(max(0, idx))

    def populate_countries(self, countries):
        if self.country_combo.count() > 1:
            return
        for country in countries:
            self.country_combo.addItem(country.get("english_name", ""), country.get("iso_3166_1", ""))
        if hasattr(self, '_pending_params') and "with_origin_country" in self._pending_params:
            idx = self.country_combo.findData(self._pending_params["with_origin_country"])
            self.country_combo.setCurrentIndex(max(0, idx))

    def set_params(self, params):
        if params is None:
            params = {}
            
        # Retain parameters that don't have a UI control
        ui_keys = ["show_me", "with_genres", "sort_by", "with_original_language", 
                  "with_origin_country", "primary_release_date.gte", 
                  "primary_release_date.lte", "vote_average.gte", "query"]
        self.base_params = {k: v for k, v in params.items() if k not in ui_keys}
            
        main_win = self.window()
        if hasattr(main_win, "search_bar"):
            if "query" in params:
                main_win.search_bar.setText(params["query"])
            else:
                main_win.search_bar.clear()

        if "show_me" in params:
            idx = self.show_me_combo.findData(params["show_me"])
            self.show_me_combo.setCurrentIndex(max(0, idx))
        else:
            self.show_me_combo.setCurrentIndex(0)

        if "with_genres" in params:
            self._pending_params["with_genres"] = params["with_genres"]
            genres_list = [int(x) for x in str(params["with_genres"]).split(",")]
            self.genre_combo.setChecked(genres_list)
        else:
            self.genre_combo.setChecked([])

        if "with_original_language" in params:
            self._pending_params["with_original_language"] = params["with_original_language"]
            idx = self.language_combo.findData(params["with_original_language"])
            self.language_combo.setCurrentIndex(max(0, idx))
        else:
            self.language_combo.setCurrentIndex(0)
            
        if "with_origin_country" in params:
            self._pending_params["with_origin_country"] = params["with_origin_country"]
            idx = self.country_combo.findData(params["with_origin_country"])
            self.country_combo.setCurrentIndex(max(0, idx))
        else:
            self.country_combo.setCurrentIndex(0)

        if "sort_by" in params:
            idx = self.sort_combo.findData(params["sort_by"])
            self.sort_combo.setCurrentIndex(max(0, idx))
        else:
            self.sort_combo.setCurrentIndex(0)

        if "primary_release_date.gte" in params:
            year_start = int(params["primary_release_date.gte"].split("-")[0])
            idx = self.from_year.findData(year_start)
            self.from_year.setCurrentIndex(max(0, idx))
        else:
            self.from_year.setCurrentIndex(0)

        if "primary_release_date.lte" in params:
            year_end = int(params["primary_release_date.lte"].split("-")[0])
            idx = self.to_year.findData(year_end)
            self.to_year.setCurrentIndex(max(0, idx))
        else:
            self.to_year.setCurrentIndex(0)

        if "vote_average.gte" in params:
            idx = self.rating_combo.findData(params["vote_average.gte"])
            self.rating_combo.setCurrentIndex(max(0, idx))
        else:
            self.rating_combo.setCurrentIndex(0)

    def _apply(self):
        params = self.base_params.copy()

        show_me = self.show_me_combo.currentData()
        if show_me:
            params["show_me"] = show_me

        genres_selected = self.genre_combo.currentDataList()
        if genres_selected:
            params["with_genres"] = ",".join(map(str, genres_selected))

        sort_by = self.sort_combo.currentData()
        if sort_by:
            params["sort_by"] = sort_by

        lang = self.language_combo.currentData()
        if lang:
            params["with_original_language"] = lang
            
        country = self.country_combo.currentData()
        if country:
            params["with_origin_country"] = country

        from_y = self.from_year.currentData()
        if from_y is not None:
            params["primary_release_date.gte"] = f"{from_y}-01-01"

        to_y = self.to_year.currentData()
        if to_y is not None:
            params["primary_release_date.lte"] = f"{to_y}-12-31"

        rating = self.rating_combo.currentData()
        if rating:
            params["vote_average.gte"] = rating
            params["vote_count.gte"] = 100

        # Hook up the main search bar to combine keyword and filters
        main_win = self.window()
        if hasattr(main_win, "search_bar"):
            query = main_win.search_bar.text().strip()
            if query:
                params["query"] = query

        global GLOBAL_FILTER_STATE
        GLOBAL_FILTER_STATE.clear()
        GLOBAL_FILTER_STATE.update(params)

        self.signals.filters_applied.emit(params)
