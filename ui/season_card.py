from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor

from ui.movie_card import ImageLoader

class SeasonCard(QWidget):
    def __init__(self, season, on_click_callback=None, width=150):
        super().__init__()
        self.season = season
        self.on_click_callback = on_click_callback
        self.setFixedWidth(width)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        self.poster_lbl = QLabel()
        self.poster_lbl.setFixedSize(width, int(width * 1.5))
        self.poster_lbl.setStyleSheet("background-color: #2D3748; border-radius: 8px;")
        self.poster_lbl.setAlignment(Qt.AlignCenter)
        
        name = season.get("name", "Unknown")
        self.title_lbl = QLabel(name)
        self.title_lbl.setStyleSheet("color: white; font-weight: bold; font-size: 13px;")
        self.title_lbl.setWordWrap(True)
        
        ep_count = season.get("episode_count", 0)
        year = season.get("air_date", "")[:4] if season.get("air_date") else "Unknown"
        self.info_lbl = QLabel(f"{ep_count} Episodes • {year}")
        self.info_lbl.setStyleSheet("color: #A0AEC0; font-size: 12px;")
        
        layout.addWidget(self.poster_lbl)
        layout.addWidget(self.title_lbl)
        layout.addWidget(self.info_lbl)
        layout.addStretch()
        
        self.load_poster()

    def load_poster(self):
        path = self.season.get("poster_path")
        if not path:
            self.poster_lbl.setText("No Image")
            return
            
        url = f"https://image.tmdb.org/t/p/w500{path}"
        cached = ImageLoader.get_cached_image(url)
        if cached:
            self.on_poster_loaded(cached)
        else:
            from PySide6.QtCore import QThreadPool
            self.loader = ImageLoader(url)
            self.loader.signals.finished.connect(self.on_poster_loaded)
            QThreadPool.globalInstance().start(self.loader)
            
    def on_poster_loaded(self, image_data):
        if not image_data:
            self.poster_lbl.setText("No Image")
            return
            
        from PySide6.QtGui import QImage, QPixmap
        img = QImage()
        if img.loadFromData(image_data):
            pixmap = QPixmap.fromImage(img)
            scaled = pixmap.scaled(self.poster_lbl.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self.poster_lbl.setPixmap(scaled)
        else:
            self.poster_lbl.setText("No Image")
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.on_click_callback:
            self.on_click_callback(self.season)
        super().mousePressEvent(event)
