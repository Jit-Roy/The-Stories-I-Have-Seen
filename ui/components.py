from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QComboBox, QFrame, QSpinBox
from PySide6.QtGui import QPixmap, QImage, QPainter, QPainterPath
from PySide6.QtCore import Qt, QUrl, QRunnable, QThreadPool, Signal, QObject
from PySide6.QtGui import QStandardItemModel, QStandardItem
import requests

class ImageLoaderSignals(QObject):
    finished = Signal(bytes)

class ImageLoader(QRunnable):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.signals = ImageLoaderSignals()
        
    def run(self):
        headers = {"User-Agent": "WorldsIveWatched/1.0"}
        try:
            r = requests.get(self.url, headers=headers, timeout=10)
            if r.status_code == 200:
                self.signals.finished.emit(r.content)
            else:
                self.signals.finished.emit(b"")
        except Exception:
            self.signals.finished.emit(b"")

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
        return f"""
            QPushButton {{
                background-color: {bg};
                color: {color};
                border: none;
                padding: 0px 20px;
                font-weight: bold;
                {radius}
            }}
        """

    def _on_click(self):
        sender = self.sender()
        if sender == self.btn1 and self.current != self.opt1:
            self.current = self.opt1
            self.btn1.setStyleSheet(self._get_style(True, True))
            self.btn2.setStyleSheet(self._get_style(False, False))
            self.toggled.emit(self.opt1)
        elif sender == self.btn2 and self.current != self.opt2:
            self.current = self.opt2
            self.btn1.setStyleSheet(self._get_style(False, True))
            self.btn2.setStyleSheet(self._get_style(True, False))
            self.toggled.emit(self.opt2)

class HeroBanner(QWidget):
    def __init__(self, movie, on_explore):
        super().__init__()
        self.movie = movie
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
        explore_btn.setProperty("class", "primary-btn")
        explore_btn.clicked.connect(lambda: on_explore(movie))
        
        wishlist_btn = QPushButton("+ Add to Wishlist")
        wishlist_btn.setStyleSheet("background: transparent; border: 1px solid #A0AEC0; color: #A0AEC0; padding: 10px 20px; border-radius: 6px;")
        
        btn_layout.addWidget(explore_btn)
        btn_layout.addWidget(wishlist_btn)
        btn_layout.addStretch()
        
        layout.addWidget(title)
        layout.addWidget(info)
        layout.addSpacing(10)
        layout.addLayout(btn_layout)
        
        self.load_backdrop()

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
        if self.movie.get("backdrop_path"):
            loader = ImageLoader(self.movie["backdrop_path"])
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
    def __init__(self, movies, on_explore):
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
            slide = HeroBanner(m, on_explore)
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

class MultiSelectComboBox(QComboBox):
    def __init__(self, placeholder="Select Options", parent=None):
        super().__init__(parent)
        self.placeholder = placeholder
        self.model = QStandardItemModel()
        self.setModel(self.model)
        
        placeholder_item = QStandardItem(self.placeholder)
        placeholder_item.setFlags(Qt.NoItemFlags)
        self.model.appendRow(placeholder_item)
        
        self.view().pressed.connect(self.handle_item_pressed)
        
    def addItem(self, text, data=None):
        item = QStandardItem(text)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        item.setData(Qt.Unchecked, Qt.CheckStateRole)
        item.setData(data, Qt.UserRole)
        self.model.appendRow(item)
        
    def handle_item_pressed(self, index):
        item = self.model.itemFromIndex(index)
        if item.flags() & Qt.ItemIsUserCheckable:
            if item.checkState() == Qt.Checked:
                item.setCheckState(Qt.Unchecked)
            else:
                item.setCheckState(Qt.Checked)
            self._update_text()

    def _update_text(self):
        count = len(self.currentDataList())
        if count > 0:
            self.model.item(0).setText(f"{count} Genres Selected")
        else:
            self.model.item(0).setText(self.placeholder)
        self.setCurrentIndex(0)
        
    def currentDataList(self):
        res = []
        for i in range(1, self.model.rowCount()):
            item = self.model.item(i)
            if item.checkState() == Qt.Checked:
                res.append(item.data(Qt.UserRole))
        return res
        
    def setChecked(self, data_list):
        for i in range(1, self.model.rowCount()):
            item = self.model.item(i)
            if item.data(Qt.UserRole) in data_list:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
        self._update_text()
        
    def count(self):
        return self.model.rowCount()

class DiscoverFilterBarSignals(QObject):
    filters_applied = Signal(dict)

class DiscoverFilterBar(QWidget):
    def __init__(self):
        super().__init__()
        self.signals = DiscoverFilterBarSignals()
        
        filter_layout = QHBoxLayout(self)
        filter_layout.setSpacing(10)
        filter_layout.setContentsMargins(0, 0, 0, 10)
        
        combo_style = """
            QComboBox {
                background-color: #1A1C23;
                border: 1px solid #2D3748;
                color: #E2E8F0;
                padding: 8px 15px;
                border-radius: 15px;
                font-weight: bold;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1A1C23;
                color: #E2E8F0;
                selection-background-color: #1AE0A1;
            }
        """
        
        # SHOW ME
        self.show_me_combo = QComboBox()
        self.show_me_combo.setStyleSheet(combo_style)
        self.show_me_combo.addItem("Everything", "all")
        self.show_me_combo.addItem("Movies I Haven't Seen", "unseen")
        
        # GENRES (Multi-Select)
        self.genre_combo = MultiSelectComboBox("All Genres")
        self.genre_combo.setStyleSheet(combo_style)
        
        # SORT
        self.sort_combo = QComboBox()
        self.sort_combo.setStyleSheet(combo_style)
        self.sort_combo.addItem("Most Popular", "popularity.desc")
        self.sort_combo.addItem("Highest Rated", "vote_average.desc")
        self.sort_combo.addItem("Newest Releases", "primary_release_date.desc")
        self.sort_combo.addItem("Highest Revenue", "revenue.desc")
        
        # LANGUAGE
        self.language_combo = QComboBox()
        self.language_combo.setStyleSheet(combo_style)
        self.language_combo.addItem("Any Language", None)
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("Spanish", "es")
        self.language_combo.addItem("French", "fr")
        self.language_combo.addItem("Korean", "ko")
        self.language_combo.addItem("Japanese", "ja")
        self.language_combo.addItem("Hindi", "hi")
        
        # YEAR RANGE
        import datetime
        current_year = datetime.datetime.now().year
        
        self.from_year = QSpinBox()
        self.to_year = QSpinBox()
        
        for spin in (self.from_year, self.to_year):
            spin.setRange(1900, current_year + 5)
            spin.setSpecialValueText("Any")
            spin.setStyleSheet("""
                QSpinBox {
                    background-color: #1A1C23;
                    border: 1px solid #2D3748;
                    color: #E2E8F0;
                    padding: 8px 15px;
                    border-radius: 15px;
                    font-weight: bold;
                }
            """)
            
        self.from_year.setValue(1900)
        self.to_year.setValue(current_year + 5)
        
        year_layout = QHBoxLayout()
        year_layout.setSpacing(5)
        year_layout.addWidget(QLabel("From"))
        year_layout.addWidget(self.from_year)
        year_layout.addWidget(QLabel("To"))
        year_layout.addWidget(self.to_year)
        
        # RATING
        
        self.rating_combo = QComboBox()
        self.rating_combo.setStyleSheet(combo_style)
        self.rating_combo.addItem("Any Rating", None)
        self.rating_combo.addItem("8+ Stars", 8.0)
        self.rating_combo.addItem("7+ Stars", 7.0)
        self.rating_combo.addItem("6+ Stars", 6.0)
        
        self.discover_btn = QPushButton("Discover")
        self.discover_btn.setStyleSheet("""
            QPushButton {
                background-color: #1AE0A1;
                color: #0F172A;
                border-radius: 15px;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #14B886; }
        """)
        self.discover_btn.setCursor(Qt.PointingHandCursor)
        self.discover_btn.clicked.connect(self._apply)
        
        filter_layout.addWidget(self.show_me_combo)
        filter_layout.addWidget(self.genre_combo)
        filter_layout.addWidget(self.sort_combo)
        filter_layout.addWidget(self.language_combo)
        filter_layout.addLayout(year_layout)
        filter_layout.addWidget(self.rating_combo)
        filter_layout.addWidget(self.discover_btn)
        filter_layout.addStretch()
        
    def populate_genres(self, genres):
        if self.genre_combo.count() > 1: return
        for genre in genres:
            self.genre_combo.addItem(genre["name"], genre["id"])
            
    def set_params(self, params):
        if not params: return
        
        if "show_me" in params:
            idx = self.show_me_combo.findData(params["show_me"])
            if idx >= 0: self.show_me_combo.setCurrentIndex(idx)
            
        if "with_genres" in params:
            genres_list = params["with_genres"].split(",")
            self.genre_combo.setChecked(genres_list)
            
        if "with_original_language" in params:
            idx = self.language_combo.findData(params["with_original_language"])
            if idx >= 0: self.language_combo.setCurrentIndex(idx)
            
        if "sort_by" in params:
            idx = self.sort_combo.findData(params["sort_by"])
            if idx >= 0: self.sort_combo.setCurrentIndex(idx)
            
        if "primary_release_date.gte" in params:
            year_start = int(params["primary_release_date.gte"].split("-")[0])
            self.from_year.setValue(year_start)
            
        if "primary_release_date.lte" in params:
            year_end = int(params["primary_release_date.lte"].split("-")[0])
            self.to_year.setValue(year_end)
            
        if "vote_average.gte" in params:
            idx = self.rating_combo.findData(params["vote_average.gte"])
            if idx >= 0: self.rating_combo.setCurrentIndex(idx)
            
    def _apply(self):
        params = {}
        
        show_me = self.show_me_combo.currentData()
        if show_me: params["show_me"] = show_me
        
        genres_selected = self.genre_combo.currentDataList()
        if genres_selected: params["with_genres"] = ",".join(map(str, genres_selected))
            
        sort_by = self.sort_combo.currentData()
        if sort_by: params["sort_by"] = sort_by
        
        lang = self.language_combo.currentData()
        if lang: params["with_original_language"] = lang
            
        if self.from_year.value() > self.from_year.minimum():
            params["primary_release_date.gte"] = f"{self.from_year.value()}-01-01"
            
        if self.to_year.value() < self.to_year.maximum():
            params["primary_release_date.lte"] = f"{self.to_year.value()}-12-31"
                
        rating = self.rating_combo.currentData()
        if rating:
            params["vote_average.gte"] = rating
            params["vote_count.gte"] = 100
            
        self.signals.filters_applied.emit(params)
