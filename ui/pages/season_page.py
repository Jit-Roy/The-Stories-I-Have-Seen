import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QApplication, QDialog
)
from PySide6.QtCore import Qt, QThreadPool, QRunnable, Signal, QObject, QUrl
from PySide6.QtGui import QCursor, QDesktopServices

import tmdb_api
from ui.movie_card import RoundedImage, ImageLoader
from ui.chrome_sniffer import ChromeSnifferDialog
from download_manager import DownloadManager

SEASON_CACHE = {}

class _SeasonWorkerSignals(QObject):
    finished = Signal(dict)

import threading
_worker_lock = threading.Lock()
ACTIVE_WORKERS = set()

class _SeasonWorker(QRunnable):
    def __init__(self, tv_id, season_number):
        super().__init__()
        self.tv_id = tv_id
        self.season_number = season_number
        self.signals = _SeasonWorkerSignals()
        with _worker_lock:
            ACTIVE_WORKERS.add(self)

    def run(self):
        try:
            data = tmdb_api.get_tv_season_details(self.tv_id, self.season_number)
            try:
                self.signals.finished.emit(data if data else {})
            except RuntimeError:
                pass
        finally:
            with _worker_lock:
                ACTIVE_WORKERS.discard(self)

class EpisodeCard(QFrame):
    def __init__(self, episode, tv_id, season_number, download_manager):
        super().__init__()
        self.episode = episode
        self.tv_id = tv_id
        self.season_number = season_number
        self.download_manager = download_manager

        self.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border-radius: 10px;
            }
        """)
        self.setFixedHeight(160)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Thumbnail
        self.img_label = RoundedImage()
        self.img_label.setFixedSize(200, 112)
        self.img_label.setStyleSheet("background-color: #0F172A; border-radius: 8px;")
        layout.addWidget(self.img_label)

        # Details
        details_layout = QVBoxLayout()
        details_layout.setContentsMargins(0, 0, 0, 0)

        ep_num = episode.get("episode_number", 0)
        title = episode.get("name", f"Episode {ep_num}")
        
        title_lbl = QLabel(f"{ep_num}. {title}")
        title_lbl.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        details_layout.addWidget(title_lbl)

        runtime = episode.get("runtime", 0)
        runtime_str = f"{runtime} min" if runtime else "Unknown runtime"
        air_date = episode.get("air_date", "Unknown date")
        
        meta_lbl = QLabel(f"⭐ {episode.get('vote_average', 0)}/10 • {runtime_str} • {air_date}")
        meta_lbl.setStyleSheet("color: #A0AEC0; font-size: 12px;")
        details_layout.addWidget(meta_lbl)

        overview = episode.get("overview", "No overview available.")
        if len(overview) > 150:
            overview = overview[:147] + "..."
        overview_lbl = QLabel(overview)
        overview_lbl.setStyleSheet("color: #CBD5E1; font-size: 13px;")
        overview_lbl.setWordWrap(True)
        details_layout.addWidget(overview_lbl)
        
        details_layout.addStretch()
        layout.addLayout(details_layout)
        
        # Buttons
        btns_layout = QHBoxLayout()
        btns_layout.setSpacing(10)
        
        primary = ThemeManager.get_color("primary")
        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {primary};
                color: {primary};
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.1);
            }}
        """)
        self.btn_play.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_play.clicked.connect(self._on_play)
        btns_layout.addWidget(self.btn_play)
        
        self.btn_download = QPushButton(" Download")
        from PySide6.QtGui import QIcon
        self.btn_download.setIcon(QIcon("assets/icons/downloads.svg"))
        self.btn_download.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.5);
                color: white;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        self.btn_download.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_download.clicked.connect(self._on_download)
        btns_layout.addWidget(self.btn_download)

        layout.addLayout(btns_layout)
        layout.setAlignment(btns_layout, Qt.AlignRight | Qt.AlignVCenter)

        self.download_manager.status_updated.connect(self._on_download_status)
        self.download_manager.progress_updated.connect(self._on_download_progress)
        self.download_manager.probe_finished.connect(self._on_probe_finished)
        self.load_thumbnail()
        
        # Sync initial state if it's already in the download manager
        ep_id = self.episode.get("id", self.tv_id)
        if ep_id in self.download_manager.active_downloads:
            dl_info = self.download_manager.active_downloads[ep_id]
            self._on_download_status(ep_id, dl_info.get("status", ""))
            self._on_download_progress(ep_id, dl_info)

    def _on_probe_finished(self, tmdb_id, results, error_msg):
        ep_id = self.episode.get("id", self.tv_id)
        if tmdb_id == ep_id:
            if not error_msg and results:
                from ui.stream_dialog import StreamSelectionDialog
                dialog = StreamSelectionDialog(results, self)
                if dialog.exec() == QDialog.Accepted:
                    sel = dialog.get_selection()
                    ep_num = self.episode.get("episode_number", 1)
                    movie = {
                        "id": ep_id, 
                        "media_type": "tv", 
                        "title": f"{self.episode.get('name')} (S{self.season_number}E{ep_num})", 
                        "year": (self.episode.get("air_date") or "")[:4],
                        "poster_path": f"https://image.tmdb.org/t/p/w500{self.episode.get('still_path')}" if self.episode.get("still_path") else None
                    }
                    self.download_manager.start_download(
                        movie,
                        m3u8_url=sel['m3u8_url'],
                        page_url=sel['embed_url'],
                        audio_format_id=sel['audio_id'],
                        subtitle_lang=sel['subtitle'],
                        cookies=sel.get('cookies', []),
                        headers=sel.get('headers', {})
                    )
                else:
                    self.download_manager.active_downloads.pop(tmdb_id, None)
                    self.btn_download.setText(" Download")
                    from PySide6.QtGui import QIcon
                    self.btn_download.setIcon(QIcon("assets/icons/downloads.svg"))
            else:
                self.btn_download.setText(" Download")
                from PySide6.QtGui import QIcon
                self.btn_download.setIcon(QIcon("assets/icons/downloads.svg"))

    def _on_download_status(self, tmdb_id, status):
        ep_id = self.episode.get("id", self.tv_id)
        if tmdb_id == ep_id:
            # Reset stylesheet for all states except "Downloading..."
            if status != "Downloading...":
                self.btn_download.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(255, 255, 255, 0.1);
                        border: 1px solid rgba(255, 255, 255, 0.5);
                        color: white;
                        padding: 10px 20px;
                        border-radius: 6px;
                        font-weight: bold;
                        font-size: 14px;
                    }
                    QPushButton:hover {
                        background-color: rgba(255, 255, 255, 0.2);
                    }
                """)
                
            if status in ["Probing servers...", "Pending selection...", "Initializing..."]:
                self.btn_download.setText("Loading...")
                from PySide6.QtGui import QIcon
                self.btn_download.setIcon(QIcon())
            elif status == "Downloading...":
                self.btn_download.setText("Downloading...")
            elif status == "Completed":
                self.btn_download.setText("Downloaded")
            elif status == "Paused":
                self.btn_download.setText("Resume")
            else:
                self.btn_download.setText(" Download")
                from PySide6.QtGui import QIcon
                self.btn_download.setIcon(QIcon("assets/icons/downloads.svg"))

    def _on_download_progress(self, tmdb_id, dl_info):
        ep_id = self.episode.get("id", self.tv_id)
        if tmdb_id == ep_id and dl_info.get("status") == "Downloading...":
            percent = max(0, min(100, dl_info.get("percent", 0))) / 100.0
            
            # Ensure stop points are strictly increasing for Qt
            stop2 = percent + 0.001
            if stop2 > 1.0:
                stop2 = 1.0
                
            from ui.theme_manager import ThemeManager
            rgba_base = ThemeManager.THEMES[ThemeManager.get_current_theme_name()]["rgba_base"]
            
            self.btn_download.setStyleSheet(f"""
                QPushButton {{
                    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 rgba({rgba_base}, 0.4), stop:{percent} rgba({rgba_base}, 0.4), stop:{stop2} rgba(255, 255, 255, 0.1), stop:1 rgba(255, 255, 255, 0.1));
                    border: 1px solid rgba(255, 255, 255, 0.5);
                    color: white;
                    padding: 10px 20px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 14px;
                }}
                QPushButton:hover {{
                    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 rgba({rgba_base}, 0.5), stop:{percent} rgba({rgba_base}, 0.5), stop:{stop2} rgba(255, 255, 255, 0.2), stop:1 rgba(255, 255, 255, 0.2));
                }}
            """)

    def load_thumbnail(self):
        path = self.episode.get("still_path")
        if not path:
            return
            
        url = f"https://image.tmdb.org/t/p/w300{path}"
        cached = ImageLoader.get_cached_image(url)
        if cached:
            self.on_image_loaded(cached)
            return
            
        loader = ImageLoader(url)
        loader.signals.finished.connect(self.on_image_loaded)
        QThreadPool.globalInstance().start(loader)

    def on_image_loaded(self, image_data):
        if not image_data:
            return
            
        from PySide6.QtGui import QImage, QPixmap
        img = QImage()
        if img.loadFromData(image_data):
            pixmap = QPixmap.fromImage(img)
            scaled = pixmap.scaled(self.img_label.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self.img_label.setPixmap(scaled)

    def _on_play(self):
        ep_num = self.episode.get("episode_number", 1)
        url = f"https://vidsrc.sbs/embed/tv/{self.tv_id}/{self.season_number}/{ep_num}"
        QDesktopServices.openUrl(QUrl(url))

    def _on_download(self):
        ep_num = self.episode.get("episode_number", 1)
        ep_id = self.episode.get("id", self.tv_id)
        dialog = ChromeSnifferDialog(self.tv_id, self, "tv", season_number=self.season_number, episode_number=ep_num)
        if dialog.exec():
            selection = dialog.get_selection()
            if selection and selection.get('m3u8_url'):
                self.btn_download.setText("Loading...")
                from PySide6.QtGui import QIcon
                self.btn_download.setIcon(QIcon())
                self.download_manager.start_fast_probe(
                    movie_data={"id": ep_id, "media_type": "tv", "title": f"{self.episode.get('name')} (S{self.season_number}E{ep_num})"},
                    m3u8_url=selection['m3u8_url'],
                    embed_url=selection['embed_url'],
                    cookies=selection.get('cookies', []),
                    headers=selection.get('headers', {})
                )

class SeasonPage(QWidget):
    def __init__(self, go_back_callback):
        super().__init__()
        self.go_back_callback = go_back_callback
        self.download_manager = DownloadManager()

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(40, 20, 40, 20)
        
        # Header
        header_layout = QHBoxLayout()
        self.btn_back = QPushButton("←")
        self.btn_back.setFixedSize(40, 40)
        from ui.theme_manager import ThemeManager
        primary = ThemeManager.get_color("primary")
        self.btn_back.setStyleSheet(f"""
            QPushButton {{ background-color: transparent; color: white; font-size: 28px; font-weight: bold; border: none; }}
            QPushButton:hover {{ color: {primary}; }}
        """)
        self.btn_back.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_back.clicked.connect(self.go_back_callback)
        header_layout.addWidget(self.btn_back)

        self.title_lbl = QLabel()
        self.title_lbl.setStyleSheet("color: white; font-size: 24px; font-weight: bold; margin-left: 15px;")
        header_layout.addWidget(self.title_lbl)
        header_layout.addStretch()

        self.layout.addLayout(header_layout)
        self.layout.addSpacing(20)

        # Scroll area for episodes
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        
        self.episodes_container = QWidget()
        self.episodes_container.setStyleSheet("background: transparent;")
        self.episodes_layout = QVBoxLayout(self.episodes_container)
        self.episodes_layout.setContentsMargins(0, 0, 0, 0)
        self.episodes_layout.setSpacing(15)
        self.episodes_layout.setAlignment(Qt.AlignTop)
        
        self.scroll.setWidget(self.episodes_container)
        self.layout.addWidget(self.scroll)
        
        from ui.theme_manager import ThemeManager
        ThemeManager.apply_theme_to_widget(self)

    def load_season(self, tv_id, tv_name, season_number):
        self.title_lbl.setText(f"{tv_name} - Season {season_number}")
        
        # Clear existing
        while self.episodes_layout.count():
            item = self.episodes_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        # ── Smart Cache Check ─────────────────────────────────────────
        cache_key = (tv_id, season_number)
        if cache_key in SEASON_CACHE:
            self._on_season_loaded(SEASON_CACHE[cache_key], tv_id, season_number)
            return

        lbl = QLabel("Loading episodes...")
        lbl.setStyleSheet("color: #A0AEC0;")
        self.episodes_layout.addWidget(lbl)

        self._worker = _SeasonWorker(tv_id, season_number)
        self._worker.signals.finished.connect(lambda data: self._on_season_loaded(data, tv_id, season_number))
        QThreadPool.globalInstance().start(self._worker)

    def _on_season_loaded(self, data, tv_id, season_number):
        while self.episodes_layout.count():
            item = self.episodes_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        # ── Smart Cache Store ─────────────────────────────────────────
        cache_key = (tv_id, season_number)
        if len(SEASON_CACHE) > 100:
            try:
                SEASON_CACHE.pop(next(iter(SEASON_CACHE)))
            except Exception:
                pass
        SEASON_CACHE[cache_key] = data

        episodes = data.get("episodes", [])
        if not episodes:
            lbl = QLabel("No episodes found.")
            lbl.setStyleSheet("color: #A0AEC0;")
            self.episodes_layout.addWidget(lbl)
            return
            
        for ep in episodes:
            card = EpisodeCard(ep, tv_id, season_number, self.download_manager)
            self.episodes_layout.addWidget(card)
            
        from ui.theme_manager import ThemeManager
        ThemeManager.apply_theme_to_widget(self)
