import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QScrollArea, QFrame, QProgressBar, QPushButton,
    QSizePolicy
)
from PySide6.QtCore import Qt, QSize, QThreadPool
from PySide6.QtGui import QPixmap, QIcon, QImage

from download_manager import DownloadManager
from ui.movie_card import ImageLoader

class DownloadItemWidget(QFrame):
    def __init__(self, tmdb_id, movie_data, parent=None):
        super().__init__(parent)
        self.tmdb_id = tmdb_id
        self.movie_data = movie_data
        
        self.setObjectName("DownloadItem")
        self.setStyleSheet("""
            QFrame#DownloadItem {
                background-color: transparent;
                border-radius: 12px;
                border: none;
            }
            QFrame#DownloadItem:hover {
                background-color: rgba(255, 255, 255, 5);
                border: none;
            }
        """)
        
        self.init_ui()
        self.load_poster()
        
    def init_ui(self):
        self.setFixedHeight(150)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(20)
        layout.setSpacing(20)
        
        # Poster
        self.poster_label = QLabel()
        self.poster_label.setFixedSize(80, 120)
        self.poster_label.setStyleSheet("border-radius: 8px; background-color: #222;")
        self.poster_label.setScaledContents(True)
        layout.addWidget(self.poster_label, alignment=Qt.AlignTop)
        
        # Details Layout
        details_layout = QVBoxLayout()
        details_layout.setSpacing(8)
        
        # Title
        title = self.movie_data.get("title", "Unknown Title")
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: white; font-size: 18px; font-weight: bold;")
        details_layout.addWidget(self.title_label)
        
        # Status Label
        self.status_label = QLabel("Initializing...")
        self.status_label.setStyleSheet("color: #aaa; font-size: 14px;")
        self.status_label.setWordWrap(True)
        details_layout.addWidget(self.status_label)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 4px;
                background-color: rgba(255, 255, 255, 10);
            }
            QProgressBar::chunk {
                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #14B885, stop:1 #1AE0A1);
                border-radius: 4px;
            }
        """)
        self.progress_bar.setValue(0)
        details_layout.addWidget(self.progress_bar)
        
        # Meta info (Speed / ETA)
        self.meta_label = QLabel("")
        self.meta_label.setStyleSheet("color: #888; font-size: 12px;")
        details_layout.addWidget(self.meta_label)
        
        details_layout.addStretch()
        layout.addLayout(details_layout)
        
        # Actions
        actions_layout = QVBoxLayout()
        actions_layout.addStretch()
        
        actions_inner_layout = QHBoxLayout()
        
        self.action_btn = QPushButton("Pause")
        self.action_btn.setFixedSize(100, 36)
        self.action_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 10);
                color: white;
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 30);
            }
        """)
        actions_inner_layout.addWidget(self.action_btn)
        
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setFixedSize(100, 36)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 68, 68, 0.1);
                color: #ff4444;
                border: 1px solid rgba(255, 68, 68, 0.3);
                border-radius: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 68, 68, 0.2);
            }
        """)
        actions_inner_layout.addWidget(self.delete_btn)
        
        actions_layout.addLayout(actions_inner_layout)
        actions_layout.addStretch()
        
        layout.addLayout(actions_layout)
        
        self.action_btn.clicked.connect(self.toggle_pause)
        self.delete_btn.clicked.connect(self.delete_item)

    def delete_item(self):
        manager = DownloadManager()
        manager.remove_download(self.tmdb_id)
        self.hide()
        self.deleteLater()

    def toggle_pause(self):
        manager = DownloadManager()
        if self.action_btn.text() == "Pause":
            manager.pause_download(self.tmdb_id)
        elif self.action_btn.text() == "Resume":
            manager.resume_download(self.tmdb_id)

    def update_progress(self, dl_info):
        self.progress_bar.setValue(int(dl_info.get("percent", 0)))
        
        # Format speed
        speed = dl_info.get("speed", 0)
        if isinstance(speed, str):
            speed = 0
            
        if speed and speed > 1024 * 1024:
            speed_str = f"{speed / (1024 * 1024):.1f} MB/s"
        elif speed and speed > 1024:
            speed_str = f"{speed / 1024:.1f} KB/s"
        else:
            speed_str = f"{speed} B/s" if speed else ""
            
        eta = dl_info.get("eta", 0)
        if eta:
            import datetime
            eta_str = f"ETA: {datetime.timedelta(seconds=int(eta))}"
        else:
            eta_str = ""
        
        if speed_str or eta_str:
            self.meta_label.setText(f"{speed_str}  •  {eta_str}")

    def load_poster(self):
        url = self.movie_data.get("poster_path")
        if not url:
            return

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
            target_w = int(80 * dpr)
            target_h = int(120 * dpr)
            pixmap = QPixmap(img).scaled(target_w, target_h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            pixmap.setDevicePixelRatio(dpr)
            self.poster_label.setPixmap(pixmap)

    def on_image_loaded(self, image_data):
        self._apply_image(image_data)
            
    def update_status(self, status):
        self.status_label.setText(status)
        if status == "Completed":
            self.progress_bar.setValue(100)
            self.meta_label.setText("")
            self.action_btn.setText("Open Folder")
            try:
                self.action_btn.clicked.disconnect()
            except Exception:
                pass
            self.action_btn.clicked.connect(self.open_folder)
            self.action_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #14B885;
                    border: 2px solid #14B885;
                    border-radius: 18px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(20, 184, 133, 0.1);
                    color: #1AE0A1;
                    border: 2px solid #1AE0A1;
                }
            """)
        elif status == "Paused":
            self.action_btn.setText("Resume")
            self.progress_bar.setStyleSheet("""
                QProgressBar::chunk {
                    background-color: #ff9800;
                    border-radius: 4px;
                }
            """)
        elif status == "Downloading...":
            self.action_btn.setText("Pause")
            self.progress_bar.setStyleSheet("""
                QProgressBar::chunk {
                    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #14B885, stop:1 #1AE0A1);
                    border-radius: 4px;
                }
            """)
        elif status.startswith("Error"):
            self.progress_bar.setStyleSheet("""
                QProgressBar::chunk {
                    background-color: #ff4444;
                    border-radius: 4px;
                }
            """)
            
    def open_folder(self):
        import platform
        import subprocess
        
        manager = DownloadManager()
        path = manager.download_path
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

class DownloadsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = DownloadManager()
        self.items = {} # tmdb_id -> DownloadItemWidget
        self.init_ui()
        self.connect_signals()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        # Header
        header = QLabel("Downloads")
        header.setStyleSheet("color: white; font-size: 32px; font-weight: bold;")
        layout.addWidget(header)
        
        # Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 30);
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 50);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
        
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 10, 0) # Right margin for scrollbar
        self.scroll_layout.setSpacing(15)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        
        self.empty_label = QLabel("No active or past downloads.")
        self.empty_label.setStyleSheet("color: #666; font-size: 16px;")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.scroll_layout.addWidget(self.empty_label)
        
        self.scroll_area.setWidget(self.scroll_content)
        layout.addWidget(self.scroll_area)
        
        self.populate_existing_downloads()

    def populate_existing_downloads(self):
        for tmdb_id, dl_info in self.manager.active_downloads.items():
            self.on_download_started(tmdb_id, dl_info)
            self.on_progress_updated(tmdb_id, dl_info)
            self.on_status_updated(tmdb_id, dl_info.get("status", ""))
        
    def connect_signals(self):
        self.manager.download_started.connect(self.on_download_started)
        self.manager.progress_updated.connect(self.on_progress_updated)
        self.manager.status_updated.connect(self.on_status_updated)
        
    def on_download_started(self, tmdb_id, dl_info):
        self.empty_label.hide()
        if tmdb_id not in self.items:
            item = DownloadItemWidget(tmdb_id, dl_info.get("movie_data", {}))
            self.items[tmdb_id] = item
            self.scroll_layout.insertWidget(0, item) # Add to top
            
    def on_progress_updated(self, tmdb_id, dl_info):
        if tmdb_id in self.items:
            try:
                self.items[tmdb_id].update_progress(dl_info)
            except RuntimeError:
                del self.items[tmdb_id]
            
    def on_status_updated(self, tmdb_id, status):
        if tmdb_id in self.items:
            try:
                self.items[tmdb_id].update_status(status)
            except RuntimeError:
                del self.items[tmdb_id]
