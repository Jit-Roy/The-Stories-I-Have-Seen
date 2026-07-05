from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame
from PySide6.QtGui import QPixmap, QImage, QPainter, QPainterPath, QColor, QIcon
from PySide6.QtCore import Qt, QUrl, QRunnable, QThreadPool, Signal, QObject
import requests
import hashlib
import os

# ---------------------------------------------------------------------------
# Disk-persistent image cache with in-memory LRU layer
# ---------------------------------------------------------------------------
_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "tsic", "images")
os.makedirs(_CACHE_DIR, exist_ok=True)

_MEM_CACHE_MAX = 300            # max number of images kept in RAM
_mem_cache: dict[str, bytes] = {}   # url -> raw bytes (insertion-ordered in Python 3.7+)
ACTIVE_LOADERS = set()


def _url_to_cache_path(url: str) -> str:
    key = hashlib.md5(url.encode()).hexdigest()
    return os.path.join(_CACHE_DIR, key)


def _mem_put(url: str, data: bytes):
    """Insert into in-memory LRU cache, evicting oldest entry when full."""
    if url in _mem_cache:
        _mem_cache.pop(url)          # re-insert at end (most recently used)
    elif len(_mem_cache) >= _MEM_CACHE_MAX:
        _mem_cache.pop(next(iter(_mem_cache)))  # evict oldest
    _mem_cache[url] = data


def _get_cached_image(url: str) -> bytes | None:
    """Check memory cache first, then disk cache."""
    if url in _mem_cache:
        # Promote to end (LRU touch)
        data = _mem_cache.pop(url)
        _mem_cache[url] = data
        return data
    path = _url_to_cache_path(url)
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                data = f.read()
            _mem_put(url, data)
            return data
        except OSError:
            pass
    return None


def _save_to_disk(url: str, data: bytes):
    path = _url_to_cache_path(url)
    try:
        with open(path, "wb") as f:
            f.write(data)
    except OSError:
        pass


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
        return _get_cached_image(url)

    def run(self):
        try:
            cached = _get_cached_image(self.url)
            if cached is not None:
                self.signals.finished.emit(cached)
                return

            headers = {"User-Agent": "WorldsIveWatched/1.0"}
            r = requests.get(self.url, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.content
                _mem_put(self.url, data)
                _save_to_disk(self.url, data)
                try:
                    self.signals.finished.emit(data)
                except RuntimeError:
                    pass
            else:
                try:
                    self.signals.finished.emit(b"")
                except RuntimeError:
                    pass
        except Exception:
            try:
                self.signals.finished.emit(b"")
            except RuntimeError:
                pass
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
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

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

        # Add TV badge
        if self.movie_data.get("media_type") == "tv":
            tv_badge = QLabel(self.poster_container)
            icon = QIcon("assets/icons/tv_badge.svg")
            tv_badge.setPixmap(icon.pixmap(14, 14))
            tv_badge.setAlignment(Qt.AlignCenter)
            tv_badge.setStyleSheet("background-color: transparent;")
            tv_badge.setFixedSize(24, 24)
            tv_badge.move(8, 8)

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
        if not url:
            return

        # Fast path: serve from cache synchronously (avoids spawning a thread)
        cached = ImageLoader.get_cached_image(url)
        if cached:
            self._apply_image(cached)
            return

        loader = ImageLoader(url)
        loader.signals.finished.connect(self.on_image_loaded)
        QThreadPool.globalInstance().start(loader)

    def _apply_image(self, image_data: bytes):
        if not image_data:
            return
        img = QImage()
        if img.loadFromData(image_data):
            dpr = self.devicePixelRatioF()
            target_w = int(160 * dpr)
            target_h = int(240 * dpr)
            pixmap = QPixmap(img).scaled(target_w, target_h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            pixmap.setDevicePixelRatio(dpr)
            self.poster_label.setPixmap(pixmap)

    def on_image_loaded(self, image_data):
        self._apply_image(image_data)
        if not image_data:
            if not hasattr(self, "image_retries"):
                self.image_retries = 3
            if self.image_retries > 0:
                self.image_retries -= 1
                from PySide6.QtCore import QTimer
                QTimer.singleShot(1000, self.load_poster)


class SeriesFolderCard(QFrame):
    def __init__(self, series_name, count, on_click, media_type="movie"):
        super().__init__()
        self.series_name = series_name
        self.count = count
        self.on_click = on_click
        self.media_type = media_type
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
        self.overlay.setStyleSheet("background-color: rgba(0,0,0,0.75); border-radius: 12px;")
        overlay_layout = QVBoxLayout(self.overlay)
        overlay_layout.setContentsMargins(10, 10, 10, 10)

        title_label = QLabel(series_name)
        title_label.setWordWrap(True)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #E2E8F0; border: none; background: transparent;")

        count_label = QLabel(f"{self.count} items" if self.media_type == "tv" else f"{self.count} movies")
        count_label.setAlignment(Qt.AlignCenter)
        count_label.setStyleSheet("color: #1AE0A1; font-weight: bold; font-size: 13px; border: none; background: transparent;")

        open_btn = QPushButton("View Collection")
        open_btn.setStyleSheet("""
            QPushButton { background-color: transparent; color: #1AE0A1; border: 1.5px solid #1AE0A1; border-radius: 6px; padding: 8px 10px; font-weight: bold; font-size: 13px; }
            QPushButton:hover { background-color: rgba(26, 224, 161, 0.1); }
        """)
        open_btn.clicked.connect(lambda: on_click(series_name))

        overlay_layout.addStretch()
        overlay_layout.addWidget(title_label)
        overlay_layout.addWidget(count_label)
        overlay_layout.addSpacing(15)
        overlay_layout.addWidget(open_btn)
        overlay_layout.addStretch()

        layout.addWidget(self.poster_container)
        self.setLayout(layout)

        self.load_poster()

    def load_poster(self):
        class Signals(QObject):
            finished = Signal(bytes)

        self.signals = Signals()
        self.signals.finished.connect(self.on_image_loaded)

        class FullWorker(QRunnable):
            def __init__(self, series, media_type, signals):
                super().__init__()
                self.series = series
                self.media_type = media_type
                self.signals = signals

            def run(self):
                import tmdb_api
                url = tmdb_api.get_collection_poster(self.series, self.media_type)
                if url:
                    loader = ImageLoader(url)
                    loader.signals = self.signals
                    loader.run()
                else:
                    self.signals.finished.emit(b"")

        QThreadPool.globalInstance().start(FullWorker(self.series_name, self.media_type, self.signals))

    def on_image_loaded(self, image_data):
        if image_data:
            img = QImage()
            if img.loadFromData(image_data):
                dpr = self.devicePixelRatioF()
                target_w = int(160 * dpr)
                target_h = int(240 * dpr)
                pixmap = QPixmap(img).scaled(target_w, target_h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                pixmap.setDevicePixelRatio(dpr)
                self.poster_label.setPixmap(pixmap)
