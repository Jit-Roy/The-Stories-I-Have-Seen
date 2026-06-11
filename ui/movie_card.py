from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame
from PySide6.QtGui import QPixmap, QImage, QPainter, QPainterPath, QColor
from PySide6.QtCore import Qt, QUrl, QRunnable, QThreadPool, Signal, QObject
import requests

IMAGE_CACHE = {}
ACTIVE_LOADERS = set()

class ImageLoaderSignals(QObject):
    finished = Signal(bytes)

class ImageLoader(QRunnable):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.signals = ImageLoaderSignals()
        ACTIVE_LOADERS.add(self)
        
    @staticmethod
    def get_cached_image(url):
        return IMAGE_CACHE.get(url)
        
    def run(self):
        try:
            if self.url in IMAGE_CACHE:
                self.signals.finished.emit(IMAGE_CACHE[self.url])
                return
                
            headers = {"User-Agent": "WorldsIveWatched/1.0"}
            r = requests.get(self.url, headers=headers, timeout=10)
            if r.status_code == 200:
                IMAGE_CACHE[self.url] = r.content
                try: self.signals.finished.emit(r.content)
                except RuntimeError: pass
            else:
                try: self.signals.finished.emit(b"")
                except RuntimeError: pass
        except Exception:
            try: self.signals.finished.emit(b"")
            except RuntimeError: pass
        finally:
            ACTIVE_LOADERS.discard(self)

class RoundedImage(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap = None
        
    def setPixmap(self, pixmap):
        self.pixmap = pixmap
        super().setPixmap(pixmap)
        
    def clear(self):
        self.pixmap = None
        super().clear()
        
    def paintEvent(self, event):
        if not self.pixmap:
            super().paintEvent(event)
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 12, 12)
        
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, self.width(), self.height(), self.pixmap)

class MovieCard(QWidget):
    def __init__(self, movie_data, on_status_change, on_click=None):
        super().__init__()
        self.movie_data = movie_data
        self.on_status_change = on_status_change
        self.on_click = on_click
        self.setObjectName("movieCard")
        self.setFixedSize(160, 280)
        self.setCursor(Qt.PointingHandCursor)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignTop)
        
        # Poster Container
        self.poster_container = QWidget()
        self.poster_container.setFixedSize(160, 240)
        poster_layout = QVBoxLayout(self.poster_container)
        poster_layout.setContentsMargins(0, 0, 0, 0)
        
        self.poster_label = RoundedImage()
        self.poster_label.setFixedSize(160, 240)
        self.poster_label.setStyleSheet("background-color: #1A1C23; border-radius: 12px;")
        poster_layout.addWidget(self.poster_label)
        
        # Overlay Buttons (Hidden by default)
        self.overlay = QWidget(self.poster_container)
        self.overlay.setFixedSize(160, 240)
        # Subtle gradient from top and bottom to make white icons pop
        self.overlay.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(0,0,0,0.6), stop:0.25 rgba(0,0,0,0), stop:0.75 rgba(0,0,0,0), stop:1 rgba(0,0,0,0.6));
                border-radius: 12px;
            }
        """)
        overlay_layout = QVBoxLayout(self.overlay)
        overlay_layout.setContentsMargins(8, 8, 8, 8)
        
        overlay_layout.addStretch()
        
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(8)
        
        self.btn_later = QPushButton()
        self.btn_later.setFixedSize(32, 32)
        self.btn_later.setCursor(Qt.PointingHandCursor)
        self.btn_later.clicked.connect(lambda checked=False: self.on_action_click("watch_later"))
        
        self.btn_watched = QPushButton()
        self.btn_watched.setFixedSize(32, 32)
        self.btn_watched.setCursor(Qt.PointingHandCursor)
        self.btn_watched.clicked.connect(lambda checked=False: self.on_action_click("watched"))
        
        btn_layout.addWidget(self.btn_later)
        btn_layout.addWidget(self.btn_watched)
        
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        bottom_row.addLayout(btn_layout)
        
        overlay_layout.addLayout(bottom_row)
        
        self.update_buttons()
        
        self.overlay.hide()
        layout.addWidget(self.poster_container)
        
        # Title
        self.title_label = QLabel(self.movie_data.get("title", "Unknown"))
        self.title_label.setObjectName("movieTitle")
        self.title_label.setWordWrap(True)
        # Limit to 1 line
        font_metrics = self.title_label.fontMetrics()
        elided_text = font_metrics.elidedText(self.title_label.text(), Qt.ElideRight, 150)
        self.title_label.setText(elided_text)
        layout.addWidget(self.title_label)
        
        # Info
        rating = self.movie_data.get("vote_average", "N/A")
        date = self.movie_data.get("release_date", "")[:4] if self.movie_data.get("release_date") else ""
        info_text = f"⭐ {rating}   {date}"
        self.info_label = QLabel(info_text)
        self.info_label.setObjectName("movieInfo")
        layout.addWidget(self.info_label)
        
        self.setLayout(layout)
        
        self.load_poster()

    def on_action_click(self, target_status):
        current_status = self.movie_data.get("status")
        new_status = "remove" if current_status == target_status else target_status
        if self.on_status_change:
            self.on_status_change(self.movie_data, new_status)
        self.update_buttons()

    def update_buttons(self):
        status = self.movie_data.get("status")
        base_style = "border-radius: 15px; font-weight: bold; font-size: 16px; border: none;"
        
        if status == "watched":
            self.btn_watched.setText("✓")
            self.btn_watched.setStyleSheet(f"""
                QPushButton {{ {base_style} background-color: rgba(26, 224, 161, 0.4); color: #1AE0A1; }}
                QPushButton:hover {{ background-color: rgba(26, 224, 161, 0.6); color: white; }}
            """)
            self.btn_watched.setToolTip("Remove from Watched")
        else:
            self.btn_watched.setText("✓")
            self.btn_watched.setStyleSheet(f"""
                QPushButton {{ {base_style} background-color: rgba(255, 255, 255, 0.15); color: rgba(255, 255, 255, 0.8); }}
                QPushButton:hover {{ background-color: rgba(255, 255, 255, 0.25); color: white; }}
            """)
            self.btn_watched.setToolTip("Mark as Watched")
            
        if status == "watch_later":
            self.btn_later.setText("+")
            self.btn_later.setStyleSheet(f"""
                QPushButton {{ {base_style} font-size: 20px; background-color: rgba(26, 224, 161, 0.4); color: #1AE0A1; padding-bottom: 2px; }}
                QPushButton:hover {{ background-color: rgba(26, 224, 161, 0.6); color: white; }}
            """)
            self.btn_later.setToolTip("Remove from Watch Later")
        else:
            self.btn_later.setText("+")
            self.btn_later.setStyleSheet(f"""
                QPushButton {{ {base_style} font-size: 20px; background-color: rgba(255, 255, 255, 0.15); color: rgba(255, 255, 255, 0.8); padding-bottom: 2px; }}
                QPushButton:hover {{ background-color: rgba(255, 255, 255, 0.25); color: white; }}
            """)
            self.btn_later.setToolTip("Add to Watch Later")
    def enterEvent(self, event):
        self.overlay.show()
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        self.overlay.hide()
        super().leaveEvent(event)
        
    def mousePressEvent(self, event):
        if self.on_click:
            self.on_click(self.movie_data)
        super().mousePressEvent(event)
        
    def load_poster(self):
        url = self.movie_data.get("poster_path")
        if url:
            loader = ImageLoader(url)
            loader.signals.finished.connect(self.on_image_loaded)
            QThreadPool.globalInstance().start(loader)
        
    def on_image_loaded(self, image_data):
        if image_data:
            img = QImage()
            if img.loadFromData(image_data):
                pixmap = QPixmap(img).scaled(160, 240, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                self.poster_label.setPixmap(pixmap)
        else:
            if not hasattr(self, "image_retries"):
                self.image_retries = 3
            if self.image_retries > 0:
                self.image_retries -= 1
                from PySide6.QtCore import QTimer
                QTimer.singleShot(1000, self.load_poster)

class SeriesFolderCard(QWidget):
    def __init__(self, series_name, movie_count, on_click):
        super().__init__()
        self.series_name = series_name
        self.setObjectName("seriesFolder")
        self.setFixedSize(160, 280)
        self.setCursor(Qt.PointingHandCursor)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignTop)
        
        self.poster_container = QWidget()
        self.poster_container.setFixedSize(160, 240)
        poster_layout = QVBoxLayout(self.poster_container)
        poster_layout.setContentsMargins(0, 0, 0, 0)
        
        self.poster_label = RoundedImage()
        self.poster_label.setFixedSize(160, 240)
        self.poster_label.setStyleSheet("background-color: #1A1C23; border-radius: 12px;")
        poster_layout.addWidget(self.poster_label)
        
        self.overlay = QWidget(self.poster_container)
        self.overlay.setFixedSize(160, 240)
        self.overlay.setStyleSheet("background-color: rgba(0,0,0,0.65); border-radius: 12px;")
        overlay_layout = QVBoxLayout(self.overlay)
        overlay_layout.setAlignment(Qt.AlignCenter)
        
        title_label = QLabel(series_name)
        title_label.setWordWrap(True)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #E2E8F0; border: none; background: transparent;")
        
        count_label = QLabel(f"{movie_count} movies")
        count_label.setAlignment(Qt.AlignCenter)
        count_label.setStyleSheet("color: #1AE0A1; font-weight: bold; border: none; background: transparent;")
        
        open_btn = QPushButton("View Collection")
        open_btn.setStyleSheet("""
            QPushButton { background-color: #1AE0A1; color: #0F172A; border-radius: 6px; padding: 10px 20px; font-weight: bold; }
            QPushButton:hover { background-color: #14B885; }
        """)
        open_btn.clicked.connect(lambda: on_click(series_name))
        
        overlay_layout.addWidget(title_label)
        overlay_layout.addWidget(count_label)
        overlay_layout.addSpacing(20)
        overlay_layout.addWidget(open_btn)
        
        layout.addWidget(self.poster_container)
        self.setLayout(layout)
        
        self.load_poster()

    def load_poster(self):
        class Signals(QObject):
            finished = Signal(bytes)
        
        self.signals = Signals()
        self.signals.finished.connect(self.on_image_loaded)
        
        class FullWorker(QRunnable):
            def __init__(self, series, signals):
                super().__init__()
                self.series = series
                self.signals = signals
            def run(self):
                import tmdb_api
                url = tmdb_api.get_collection_poster(self.series)
                if url:
                    loader = ImageLoader(url)
                    loader.signals = self.signals
                    loader.run()
                else:
                    self.signals.finished.emit(b"")
                    
        QThreadPool.globalInstance().start(FullWorker(self.series_name, self.signals))
        
    def on_image_loaded(self, image_data):
        if image_data:
            img = QImage()
            if img.loadFromData(image_data):
                pixmap = QPixmap(img).scaled(160, 240, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                self.poster_label.setPixmap(pixmap)
