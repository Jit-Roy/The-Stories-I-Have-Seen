from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QApplication
)
from PySide6.QtCore import Qt, QThreadPool, QUrl, QRunnable, Signal, QObject, QSize, QTimer, QRectF
from PySide6.QtGui import QPixmap, QImage, QPainter, QDesktopServices, QColor, QPainterPath, QIcon, QPen
from ui.movie_card import RoundedImage, ImageLoader, MovieCard
from ui.components import HorizontalCarousel
from ui.stream_dialog import StreamSelectionDialog
from ui.chrome_sniffer import ChromeSnifferDialog

import tmdb_api
from download_manager import DownloadManager
from PySide6.QtWidgets import QDialog, QWidget
DETAILS_CACHE = {}

class ProfileCard(QWidget):
    def __init__(self, cast_data, on_click_callback):
        super().__init__()
        self.cast_data = cast_data
        self.on_click = on_click_callback
        self.setFixedSize(120, 230)
        self.setCursor(Qt.PointingHandCursor)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        self.img_label = RoundedImage()
        self.img_label.setFixedSize(120, 180)
        self.img_label.setStyleSheet("background-color: #1A1C23; border-radius: 8px;")
        layout.addWidget(self.img_label)

        # Hover gradient overlay — same as MovieCard (hidden by default)
        self.hover_overlay = QWidget(self.img_label)
        self.hover_overlay.setFixedSize(120, 180)
        self.hover_overlay.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(0,0,0,0.6), stop:0.25 rgba(0,0,0,0), stop:0.75 rgba(0,0,0,0), stop:1 rgba(0,0,0,0.6));
                border-radius: 8px;
            }
        """)
        self.hover_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hover_overlay.hide()
        
        name = QLabel(cast_data.get("name", ""))
        name.setStyleSheet("color: white; font-weight: bold; font-size: 12px;")
        name.setWordWrap(True)
        name.setAlignment(Qt.AlignCenter)
        layout.addWidget(name)
        layout.addStretch()
        
        self.load_image()

    def enterEvent(self, event):
        self.hover_overlay.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover_overlay.hide()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if self.on_click:
            self.on_click(self.cast_data.get("id"))
        super().mousePressEvent(event)

    def load_image(self):
        p_path = self.cast_data.get("profile_path")
        if not p_path:
            return
            
        url = f"https://image.tmdb.org/t/p/w200{p_path}"
        cached = ImageLoader.get_cached_image(url)
        if cached:
            self.on_image_loaded(cached)
            return
            
        loader = ImageLoader(url)
        loader.signals.finished.connect(self.on_image_loaded)
        QThreadPool.globalInstance().start(loader)

    def on_image_loaded(self, data):
        if data:
            pm = QImage()
            if pm.loadFromData(data):
                dpr = self.devicePixelRatioF()
                target_w = int(120 * dpr)
                target_h = int(180 * dpr)
                pixmap = QPixmap(pm).scaled(target_w, target_h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                pixmap.setDevicePixelRatio(dpr)
                self.img_label.setPixmap(pixmap)


# ---------------------------------------------------------------------------
# Worker: fetch movie details off the GUI thread
# ---------------------------------------------------------------------------
class _DetailWorkerSignals(QObject):
    finished = Signal(object)   # emits the details dict or None


class _DetailWorker(QRunnable):
    def __init__(self, movie_id, media_type="movie"):
        super().__init__()
        self.movie_id = movie_id
        self.media_type = media_type
        self.signals = _DetailWorkerSignals()

    def run(self):
        try:
            if self.media_type == "tv":
                details = tmdb_api.get_tv_details(self.movie_id)
            else:
                details = tmdb_api.get_movie_details(self.movie_id)
                
            if details:
                details["media_type"] = self.media_type
                details["age_rating"] = tmdb_api.get_age_rating(self.movie_id, self.media_type)
        except Exception as e:
            print(f"DetailWorker error: {e}")
            details = None
        try:
            self.signals.finished.emit(details)
        except RuntimeError:
            pass

class AnimatedDownloadButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 40)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton { background-color: transparent; border-radius: 20px; border: none; }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }
        """)
        import os
        self._icon_idle = QIcon(os.path.join("assets", "icons", "download.svg"))
        self._icon_done = QIcon(os.path.join("assets", "icons", "check.svg"))
        
        self.state = "idle" # idle, loading, downloading, completed
        self.progress = 0
        self.angle = 0
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._rotate)
        self.timer.setInterval(30)
        
    def _rotate(self):
        self.angle = (self.angle + 10) % 360
        self.update()
        
    def set_state(self, state, progress=0):
        if self.state != state:
            self.state = state
            if state == "loading":
                self.timer.start()
            else:
                self.timer.stop()
        self.progress = progress
        self.update()
        
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        
        if self.state == "loading":
            from ui.theme_manager import ThemeManager
            pen = QPen(QColor(ThemeManager.get_color("primary")))
            pen.setWidth(3)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            span_angle = 120 * 16
            start_angle = -self.angle * 16
            margin = 8
            arc_rect = QRectF(margin, margin, rect.width() - 2*margin, rect.height() - 2*margin)
            painter.drawArc(arc_rect, start_angle, span_angle)
            
        elif self.state == "downloading":
            pen_bg = QPen(QColor(255, 255, 255, 30))
            pen_bg.setWidth(3)
            painter.setPen(pen_bg)
            margin = 2
            ring_rect = QRectF(margin, margin, rect.width() - 2*margin, rect.height() - 2*margin)
            painter.drawEllipse(ring_rect)
            
            from ui.theme_manager import ThemeManager
            pen_fg = QPen(QColor(ThemeManager.get_color("primary")))
            pen_fg.setWidth(3)
            pen_fg.setCapStyle(Qt.RoundCap)
            painter.setPen(pen_fg)
            span_angle = int((self.progress / 100.0) * 360 * 16)
            start_angle = 90 * 16
            painter.drawArc(ring_rect, start_angle, -span_angle)
            
            icon_rect = rect.adjusted(10, 10, -10, -10)
            self._icon_idle.paint(painter, icon_rect)
            
        elif self.state == "completed":
            self._icon_done.paint(painter, rect.adjusted(8, 8, -8, -8))
        else:
            self._icon_idle.paint(painter, rect.adjusted(8, 8, -8, -8))


# ---------------------------------------------------------------------------
# BackdropFrame — caches the scaled pixmap so paintEvent is cheap
# ---------------------------------------------------------------------------
class BackdropFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._source_pixmap = None   # original download
        self._scaled_pixmap = None   # cached scaled version
        self._last_size = None       # size at which we last scaled

    def setPixmap(self, pixmap):
        self._source_pixmap = pixmap
        self._scaled_pixmap = None   # invalidate cache
        self._last_size = None
        self.update()

    def clearPixmap(self):
        self._source_pixmap = None
        self._scaled_pixmap = None
        self._last_size = None
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._source_pixmap:
            return

        current_size = self.size()

        # Only re-scale when the size actually changes (or first paint)
        if self._scaled_pixmap is None or self._last_size != current_size:
            self._scaled_pixmap = self._source_pixmap.scaled(
                current_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            self._last_size = current_size

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 12, 12)
        painter.setClipPath(path)

        x = (self.width() - self._scaled_pixmap.width()) // 2
        y = (self.height() - self._scaled_pixmap.height()) // 2
        painter.drawPixmap(x, y, self._scaled_pixmap)
        painter.fillRect(0, 0, self.width(), self.height(), QColor(0, 0, 0, 180))


# ---------------------------------------------------------------------------
# Main detail page
# ---------------------------------------------------------------------------
class MovieDetailPage(QWidget):
    def __init__(self, go_back_callback, change_status_callback, show_movie_detail_callback, show_person_detail_callback=None, show_grid_callback=None, show_season_detail_callback=None):
        super().__init__()
        self.go_back = go_back_callback
        self.change_status = change_status_callback
        self.show_movie_detail = show_movie_detail_callback
        self.show_person_detail = show_person_detail_callback
        self.show_grid_view = show_grid_callback
        self.show_season_detail = show_season_detail_callback
        self.movie_data = None
        self._last_details = None       # cached result for change_status re-use
        self._pending_movie_id = None   # guard against stale worker responses

        self.download_manager = DownloadManager()
        self.download_manager.progress_updated.connect(self._on_download_progress)
        self.download_manager.status_updated.connect(self._on_download_status)
        self.download_manager.probe_finished.connect(self._on_probe_finished)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Header with back button
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(10, 10, 10, 10)
        back_btn = QPushButton("←")
        back_btn.setFixedSize(40, 40)
        from ui.theme_manager import ThemeManager
        primary = ThemeManager.get_color("primary")
        back_btn.setStyleSheet(f"""
            QPushButton {{ background-color: transparent; color: white; font-weight: bold; font-size: 28px; border: none; }}
            QPushButton:hover {{ color: {primary}; }}
        """)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self.go_back)
        header_layout.addWidget(back_btn)
        header_layout.addStretch()
        self.layout.addLayout(header_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setAlignment(Qt.AlignTop)
        self.content_layout.setContentsMargins(0, 0, 0, 0)

        # =====================================================================
        # 1. HERO BANNER (BACKDROP CONTAINER)
        # =====================================================================
        self.backdrop_container = BackdropFrame()
        self.backdrop_container.setMinimumHeight(380)
        self.backdrop_container.setStyleSheet("BackdropFrame { background-color: #1A1C23; border-radius: 12px; }")

        bd_layout = QHBoxLayout(self.backdrop_container)
        bd_layout.setContentsMargins(30, 30, 30, 30)

        self.poster_label = RoundedImage()
        self.poster_label.setFixedSize(160, 240)
        self.poster_label.setStyleSheet("background-color: #1A1C23; border-radius: 12px;")
        bd_layout.addWidget(self.poster_label)

        info_layout = QVBoxLayout()
        title_row = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 32px; font-weight: bold; color: white;")
        self.title_label.setWordWrap(True)
        title_row.addWidget(self.title_label)
        title_row.addStretch()

        self.btn_download = AnimatedDownloadButton()
        self.btn_download.setToolTip("Download Movie")
        self.btn_download.clicked.connect(self.download_movie)
        title_row.addWidget(self.btn_download, alignment=Qt.AlignTop)

        self.tagline_label = QLabel()
        self.tagline_label.setStyleSheet("font-size: 16px; font-style: italic; color: #A0AEC0;")
        self.tagline_label.setWordWrap(True)

        self.meta_label = QLabel()
        self.meta_label.setStyleSheet("font-size: 16px; color: #A0AEC0;")

        self.credits_label = QLabel()
        self.credits_label.setStyleSheet("font-size: 14px; color: #CBD5E0;")
        self.credits_label.setWordWrap(True)

        self.overview_label = QLabel()
        self.overview_label.setStyleSheet("font-size: 16px; color: #E2E8F0; line-height: 1.5;")
        self.overview_label.setWordWrap(True)

        action_layout = QHBoxLayout()
        self.btn_play = QPushButton("▶   Play")
        self.btn_play.setFixedHeight(45)
        self.btn_play.setCursor(Qt.PointingHandCursor)
        self.btn_play.setStyleSheet("""
            /* COMPLEMENTARY */
            QPushButton {
                background-color: #FF2A6C; color: #0F172A; border-radius: 6px;
                padding: 10px 24px; font-weight: bold; font-size: 14px; border: none;
            }
            QPushButton:hover { background-color: #FF2A6C; }
        """)
        self.btn_play.clicked.connect(self.play_movie)

        self.btn_watched = QPushButton("Mark Watched")
        self.btn_watched.setFixedHeight(45)
        self.btn_watched.setCursor(Qt.PointingHandCursor)
        self.btn_watched.clicked.connect(
            lambda: self.change_status(
                self.movie_data,
                "remove" if self.movie_data.get("status") == "watched" else "watched"
            )
        )

        self.btn_later = QPushButton("Watch Later")
        self.btn_later.setFixedHeight(45)
        self.btn_later.setCursor(Qt.PointingHandCursor)
        self.btn_later.clicked.connect(
            lambda: self.change_status(
                self.movie_data,
                "remove" if self.movie_data.get("status") == "watch_later" else "watch_later"
            )
        )
        
        action_layout.addWidget(self.btn_play)
        action_layout.addWidget(self.btn_watched)
        action_layout.addWidget(self.btn_later)
        action_layout.addStretch()

        info_layout.addLayout(title_row)
        info_layout.addWidget(self.tagline_label)
        info_layout.addWidget(self.meta_label)
        info_layout.addSpacing(10)
        info_layout.addWidget(self.credits_label)
        info_layout.addSpacing(10)
        info_layout.addWidget(self.overview_label)
        info_layout.addStretch()
        info_layout.addSpacing(20)
        info_layout.addLayout(action_layout)

        bd_layout.addSpacing(30)
        bd_layout.addLayout(info_layout)

        self.content_layout.addWidget(self.backdrop_container)
        self.content_layout.addSpacing(30)

        # =====================================================================
        # 2. EXTENDED DATA LAYOUT (TWO COLUMNS)
        # =====================================================================
        extended_container = QWidget()
        extended_layout = QHBoxLayout(extended_container)
        extended_layout.setAlignment(Qt.AlignTop)
        extended_layout.setContentsMargins(10, 0, 10, 0)

        # --- Left Column: Media & Discovery ---
        self.left_column = QVBoxLayout()
        self.left_column.setAlignment(Qt.AlignTop)

        self.cast_container = QWidget()
        self.cast_layout = QVBoxLayout(self.cast_container)
        self.cast_layout.setContentsMargins(0, 0, 0, 0)
        self.left_column.addWidget(self.cast_container)
        self.left_column.addSpacing(30)
        
        self.trailers_container = QWidget()
        self.trailers_layout = QVBoxLayout(self.trailers_container)
        self.trailers_layout.setContentsMargins(0, 0, 0, 0)
        self.left_column.addWidget(self.trailers_container)
        self.left_column.addSpacing(30)

        self.seasons_container = QWidget()
        self.seasons_layout = QVBoxLayout(self.seasons_container)
        self.seasons_layout.setContentsMargins(0, 0, 0, 0)
        self.left_column.addWidget(self.seasons_container)

        self.similar_container = QWidget()
        self.similar_layout = QVBoxLayout(self.similar_container)
        self.similar_layout.setContentsMargins(0, 0, 0, 0)
        self.left_column.addWidget(self.similar_container)
        
        self.recommendations_container = QWidget()
        self.recommendations_layout = QVBoxLayout(self.recommendations_container)
        self.recommendations_layout.setContentsMargins(0, 0, 0, 0)
        self.left_column.addWidget(self.recommendations_container)
        
        self.left_column.addStretch()

        # --- Right Column: Facts Sidebar ---
        self.right_column = QVBoxLayout()
        self.right_column.setAlignment(Qt.AlignTop)
        self.right_column.setContentsMargins(20, 0, 0, 0)

        facts_title = QLabel("Facts")
        facts_title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        self.right_column.addWidget(facts_title)
        self.right_column.addSpacing(10)

        self.facts_label = QLabel()
        self.facts_label.setStyleSheet("font-size: 14px; color: #E2E8F0; line-height: 1.6;")
        self.facts_label.setWordWrap(True)
        self.facts_label.setFixedWidth(250)
        self.right_column.addWidget(self.facts_label)
        self.right_column.addStretch()

        extended_layout.addLayout(self.left_column, stretch=3)
        extended_layout.addLayout(self.right_column, stretch=1)

        self.content_layout.addWidget(extended_container)
        self.content_layout.addStretch()

        scroll.setWidget(self.content_widget)
        self.layout.addWidget(scroll)

    # ------------------------------------------------------------------
    # Player controls
    # ------------------------------------------------------------------
    def play_movie(self):
        if not self.movie_data:
            return
        tmdb_id = self.movie_data.get("id")
        
        m_type = self.movie_data.get("media_type")
        if not m_type:
            if "name" in self.movie_data and "title" not in self.movie_data:
                m_type = "tv"
            else:
                m_type = "movie"
                
        if tmdb_id:
            import webbrowser
            if m_type == "tv":
                url = f"https://vidsrc.sbs/embed/tv/{tmdb_id}/1/1"
            else:
                url = f"https://vidsrc.sbs/embed/movie/{tmdb_id}"
            print(f"[Player] Opening system browser: {url}")
            webbrowser.open(url)



    def download_movie(self):
        if not self.movie_data:
            return
            
        tmdb_id = self.movie_data.get("id")
        # Always use self.download_manager — NOT a new DownloadManager() instance,
        # which would be disconnected from the progress/status signals.
        manager = self.download_manager
        if not manager:
            return
        
        # Check current status
        dl_info = manager.active_downloads.get(tmdb_id)
        if dl_info:
            status = dl_info.get("status", "")
            if status == "Paused":
                manager.resume_download(tmdb_id)
                self.btn_download.setToolTip("Initializing...")
                self.btn_download.set_state("loading")
                return
            elif status == "Pending selection...":
                pass # allow re-opening dialog if needed
            elif status not in ("Completed", "Error", "Download Failed", "Error: Restart required") and not status.startswith("Error"):
                manager.pause_download(tmdb_id)
                return
        
        # Ensure download manager is passed to detail page during setup
        if not hasattr(self, "download_manager") or not self.download_manager:
            return

        m_type = self.movie_data.get("media_type")
        if not m_type:
            if "name" in self.movie_data and "title" not in self.movie_data:
                m_type = "tv"
            else:
                m_type = "movie"

        movie_id = str(self.movie_data.get('id', ''))
        if not movie_id:
            return

        # Native Chrome Sniffer approach
        dialog = ChromeSnifferDialog(movie_id, self, m_type)
        if dialog.exec():
            selection = dialog.get_selection()
            if selection and selection.get('m3u8_url'):
                # Pass to download_manager to do the fast probe and trigger stream selection
                self.btn_download.setToolTip("Fetching options...")
                self.btn_download.set_state("loading")
                self.download_manager.start_fast_probe(
                    movie_data=self.movie_data,
                    m3u8_url=selection['m3u8_url'],
                    embed_url=selection['embed_url'],
                    cookies=selection.get('cookies', []),
                    headers=selection.get('headers', {})
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())
                item.layout().deleteLater()

    # ------------------------------------------------------------------
    # Public entry-point — non-blocking
    # ------------------------------------------------------------------
    def load_movie(self, movie_data):
        self.movie_data = movie_data
        self._last_details = None
        movie_id = movie_data["id"]
        self._pending_movie_id = movie_id

        # ── Immediate UI reset ─────────────────────────────────────────
        self.title_label.setText(movie_data.get("title", "Unknown"))
        self.tagline_label.setVisible(False)
        self.meta_label.setText("Loading…")
        self.credits_label.setVisible(False)
        self.overview_label.setText(movie_data.get("overview", ""))
        self.poster_label.clear()
        self.backdrop_container.clearPixmap()
        self._clear_layout(self.cast_layout)
        self._clear_layout(self.trailers_layout)
        self._clear_layout(self.seasons_layout)
        self._clear_layout(self.similar_layout)
        self._clear_layout(self.recommendations_layout)
        self.facts_label.setText("")
        self.btn_download.setToolTip("Download Movie")
        self.btn_download.set_state("idle")
        self.btn_download.setEnabled(True)
        self.update_buttons()

        # ── Fast-path: serve poster from cache if available ───────────
        poster_path = movie_data.get("poster_path")
        if poster_path:
            cached = ImageLoader.get_cached_image(poster_path)
            if cached:
                self.on_poster_loaded(cached)

        # ── Smart Cache Check ─────────────────────────────────────────
        media_type = movie_data.get("media_type", "movie")
        cache_key = (movie_id, media_type)
        if cache_key in DETAILS_CACHE:
            self._on_details_loaded(DETAILS_CACHE[cache_key])
            return

        # ── Kick off the details worker (non-blocking) ────────────────
        worker = _DetailWorker(movie_id, media_type)
        worker.signals.finished.connect(self._on_details_loaded)
        QThreadPool.globalInstance().start(worker)

        # ── Start image loaders ───────────────────────────────────────
        if movie_data.get("backdrop_path"):
            bd_loader = ImageLoader(movie_data["backdrop_path"])
            bd_loader.signals.finished.connect(self.on_backdrop_loaded)
            QThreadPool.globalInstance().start(bd_loader)

        if poster_path and not ImageLoader.get_cached_image(poster_path):
            poster_loader = ImageLoader(poster_path)
            poster_loader.signals.finished.connect(self.on_poster_loaded)
            QThreadPool.globalInstance().start(poster_loader)

    # ------------------------------------------------------------------
    # Slot: called on main thread when the worker finishes
    # ------------------------------------------------------------------
    def _on_details_loaded(self, details):
        # Guard: ignore stale responses if the user navigated away
        if not details or details.get("id") != self._pending_movie_id:
            if not details:
                self.meta_label.setText("Details unavailable")
            return

        self._last_details = details
        
        # ── Smart Cache Store ─────────────────────────────────────────
        media_type = details.get("media_type", self.movie_data.get("media_type", "movie"))
        cache_key = (details.get("id"), media_type)
        if len(DETAILS_CACHE) > 100:
            try:
                DETAILS_CACHE.pop(next(iter(DETAILS_CACHE)))
            except Exception:
                pass
        DETAILS_CACHE[cache_key] = details

        # Re-inject fresh DB status (details cache may have been stale)
        import tmdb_api
        tmdb_api.inject_db_status([self.movie_data])

        raw_date = details.get("release_date", "")
        if raw_date and len(raw_date) >= 10:
            try:
                from datetime import datetime
                date = datetime.strptime(raw_date[:10], "%Y-%m-%d").strftime("%b %d, %Y")
            except Exception:
                date = raw_date[:4]
        else:
            date = raw_date[:4] if raw_date else "Unknown Date"
        runtime = details.get("runtime", 0)
        genres = ", ".join(details.get("genres", []))
        rating = round(details.get("vote_average", 0), 1)
        age_rating = details.get("age_rating")
        age_str = f" • {age_rating}" if age_rating else ""
        self.meta_label.setText(f"{date} • {runtime} min • {genres}{age_str} • ⭐ {rating}/10")

        tagline = details.get("tagline")
        self.tagline_label.setText(f'"{tagline}"' if tagline else "")
        self.tagline_label.setVisible(bool(tagline))

        director = details.get("director", "Unknown")
        self.credits_label.setText(f"<b>Director/Creator:</b> {director}")
        self.credits_label.setVisible(True)

        self.overview_label.setText(details.get("overview", "No overview available."))

        # --- Cast ---
        cast_details = details.get("cast_details", [])
        if cast_details and hasattr(self, 'show_person_detail') and self.show_person_detail:
            lbl = QLabel("Cast")
            lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: white; margin-bottom: 10px;")
            self.cast_layout.addWidget(lbl)
            
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setStyleSheet("background: transparent; border: none;")
            scroll.setFixedHeight(260)
            
            content = QWidget()
            content.setStyleSheet("background: transparent;")
            h_layout = QHBoxLayout(content)
            h_layout.setContentsMargins(0, 0, 0, 0)
            h_layout.setSpacing(15)
            h_layout.setAlignment(Qt.AlignLeft)
            
            for c in cast_details:
                card = ProfileCard(c, self.show_person_detail)
                h_layout.addWidget(card)
                
            scroll.setWidget(content)
            self.cast_layout.addWidget(scroll)

        # --- Trailers ---
        trailers = details.get("trailers", [])
        if trailers:
            lbl = QLabel("Videos & Trailers")
            lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: white; margin-bottom: 10px;")
            self.trailers_layout.addWidget(lbl)

            trailer_btns_layout = QHBoxLayout()
            trailer_btns_layout.setAlignment(Qt.AlignLeft)
            for t in trailers[:3]:
                name = t["name"]
                if len(name) > 35:
                    name = name[:32] + "..."
                btn = QPushButton(f"▶ {name}")
                btn.setStyleSheet("background-color: rgba(255,255,255,0.1); color: white; border-radius: 6px; padding: 10px; font-size: 13px;")
                btn.setCursor(Qt.PointingHandCursor)
                key = t["key"]
                btn.clicked.connect(lambda _, k=key: QDesktopServices.openUrl(QUrl(f"https://www.youtube.com/watch?v={k}")))
                trailer_btns_layout.addWidget(btn)
            self.trailers_layout.addLayout(trailer_btns_layout)

        # --- Seasons ---
        seasons = details.get("seasons", [])
        if seasons:
            def on_season_click(season):
                if hasattr(self, 'show_season_detail') and self.show_season_detail:
                    tv_name = self.movie_data.get("title", self.movie_data.get("name", "Unknown"))
                    self.show_season_detail(self.movie_data.get("id"), tv_name, season.get("season_number", 1))

            from ui.season_card import SeasonCard
            carousel = HorizontalCarousel(
                "Seasons",
                seasons,
                lambda s: SeasonCard(s, on_click_callback=on_season_click),
                on_view_all=None
            )
            self.seasons_layout.addWidget(carousel)

        similar = details.get("similar", [])
        if similar:
            tmdb_api.inject_db_status(similar)  # re-inject: cached data may be stale
            _s_id = self.movie_data.get("id")
            _s_type = self.movie_data.get("media_type")
            _s_title = self.movie_data.get('title', self.movie_data.get('name', 'Unknown'))
            def handle_view_all(*args, _sid=_s_id, _stype=_s_type, _stitle=_s_title):
                if self.show_grid_view:
                    title = f"Similar to: {_stitle}"
                    if _stype == "tv":
                        self.show_grid_view(title, lambda page=1, _id=_sid: tmdb_api.get_similar_tv(_id, page=page))
                    else:
                        self.show_grid_view(title, lambda page=1, _id=_sid: tmdb_api.get_similar_movies(_id, page=page))
                        
            carousel = HorizontalCarousel(
                "Similar Movies" if self.movie_data.get("media_type") != "tv" else "Similar Shows",
                similar,
                lambda m: MovieCard(m, self.change_status, self.show_movie_detail),
                on_view_all=handle_view_all if self.show_grid_view else None
            )
            self.similar_layout.addWidget(carousel)

        # --- Recommendations ---
        recommendations = details.get("recommendations", [])
        if recommendations:
            tmdb_api.inject_db_status(recommendations)  # re-inject: cached data may be stale
            _r_id = self.movie_data.get("id")
            _r_type = self.movie_data.get("media_type")
            _r_title = self.movie_data.get('title', self.movie_data.get('name', 'Unknown'))
            def handle_view_all_rec(*args, _rid=_r_id, _rtype=_r_type, _rtitle=_r_title):
                if self.show_grid_view:
                    title = f"Recommendations for: {_rtitle}"
                    if _rtype == "tv":
                        self.show_grid_view(title, lambda page=1, _id=_rid: tmdb_api.get_recommended_tv(_id, page=page))
                    else:
                        self.show_grid_view(title, lambda page=1, _id=_rid: tmdb_api.get_recommended_movies(_id, page=page))
                        
            carousel = HorizontalCarousel(
                "Recommendations",
                recommendations,
                lambda m: MovieCard(m, self.change_status, self.show_movie_detail),
                on_view_all=handle_view_all_rec if self.show_grid_view else None
            )
            self.recommendations_layout.addWidget(carousel)

        # --- Facts Sidebar ---
        def format_money(amount):
            if not amount:
                return "-"
            if amount >= 1_000_000_000:
                return f"${amount/1_000_000_000:.1f}B"
            if amount >= 1_000_000:
                return f"${amount/1_000_000:.1f}M"
            return f"${amount:,}"

        status = details.get("tmdb_status", "-")
        lang = details.get("original_language", "-")
        budget = format_money(details.get("budget", 0))
        revenue = format_money(details.get("revenue", 0))
        companies = ", ".join(details.get("production_companies", [])) or "-"

        facts_html = f"""
        <p><b>Status</b><br>{status}</p>
        <p><b>Original Language</b><br>{lang}</p>
        <p><b>Budget</b><br>{budget}</p>
        <p><b>Revenue</b><br>{revenue}</p>
        <p><b>Studios</b><br>{companies}</p>
        """
        if details.get("homepage"):
            from ui.theme_manager import ThemeManager
            primary = ThemeManager.get_color("primary")
            facts_html += f'<p><b>Homepage</b><br><a href="{details["homepage"]}" style="color: {primary};">Visit Site</a></p>'

        self.facts_label.setText(facts_html)
        self.facts_label.setOpenExternalLinks(True)
        


        self.update_buttons()

    # ------------------------------------------------------------------
    # Button state
    # ------------------------------------------------------------------
    def update_buttons(self):
        status = self.movie_data.get("status") if self.movie_data else None

        from ui.theme_manager import ThemeManager
        primary = ThemeManager.get_color("primary")
        secondary = ThemeManager.THEMES[ThemeManager.get_current_theme_name()].get("secondary", primary)
        rgba_base = ThemeManager.THEMES[ThemeManager.get_current_theme_name()]["rgba_base"]

        if status == "watched":
            self.btn_watched.setText("✓ Watched")
            self.btn_watched.setStyleSheet(f"""
                QPushButton {{ background-color: {secondary}; color: #0F172A; border-radius: 6px; padding: 10px 24px; font-weight: bold; font-size: 14px; border: none; }}
                QPushButton:hover {{ background-color: {ThemeManager.lighten_hex(secondary, 0.2)}; }}
            """)
        else:
            self.btn_watched.setText("Mark Watched")
            self.btn_watched.setStyleSheet(f"""
                QPushButton {{ background-color: {primary}; color: #0F172A; border-radius: 6px; padding: 10px 24px; font-weight: bold; font-size: 14px; border: none; }}
                QPushButton:hover {{ background-color: {ThemeManager.lighten_hex(primary, 0.2)}; }}
            """)

        if status == "watch_later":
            self.btn_later.setText("✓ Watch Later")
            self.btn_later.setStyleSheet(f"""
                QPushButton {{ background-color: transparent; color: {primary}; border: 1.5px solid {primary}; border-radius: 6px; padding: 10px 24px; font-weight: bold; font-size: 14px; }}
                QPushButton:hover {{ background-color: rgba({rgba_base}, 0.1); }}
            """)
        else:
            self.btn_later.setText("Watch Later")
            self.btn_later.setStyleSheet("""
                QPushButton { background-color: transparent; color: white; border: 1.5px solid rgba(255,255,255,0.6); border-radius: 6px; padding: 10px 24px; font-weight: bold; font-size: 14px; }
                QPushButton:hover { background-color: rgba(255,255,255,0.1); border-color: white; color: white; }
            """)
        from ui.theme_manager import ThemeManager
        play_color = ThemeManager.get_color("complementary")
        play_hover = ThemeManager.lighten_hex(play_color, 0.2)
        self.btn_play.setStyleSheet(f"""
            /* COMPLEMENTARY */
            QPushButton {{
                background-color: {play_color}; color: #0F172A; border-radius: 6px;
                padding: 10px 24px; font-weight: bold; font-size: 14px; border: none;
            }}
            QPushButton:hover {{ background-color: {play_hover}; }}
        """)
        
        ThemeManager.apply_theme_to_widget(self)
        # Download button state
        tmdb_id = self.movie_data.get("id") if self.movie_data else None
        if tmdb_id:
            dl_info = self.download_manager.active_downloads.get(tmdb_id)
            if not dl_info:
                # Try integer cast just in case
                try:
                    dl_info = self.download_manager.active_downloads.get(int(tmdb_id))
                except:
                    pass
                if not dl_info:
                    try:
                        dl_info = self.download_manager.active_downloads.get(str(tmdb_id))
                    except:
                        pass
            
            if dl_info:
                status = dl_info.get("status", "")
                if status == "Completed":
                    self.btn_download.setToolTip("Downloaded")
                    self.btn_download.set_state("completed")
                    self.btn_download.setEnabled(True)
                elif status.startswith("Error"):
                    self.btn_download.setToolTip("Download Failed")
                    self.btn_download.set_state("idle")
                    self.btn_download.setEnabled(True)
                elif status == "Paused":
                    self.btn_download.setToolTip("Resume Download")
                    self.btn_download.set_state("idle")
                    self.btn_download.setEnabled(True)
                else:
                    percent = int(dl_info.get("percent", 0))
                    if percent > 0:
                        self.btn_download.setToolTip(f"Downloading... {percent}%")
                        self.btn_download.setEnabled(True)
                        self.btn_download.set_state("downloading", percent)
                    else:
                        self.btn_download.setToolTip(status)
                        self.btn_download.setEnabled(True)
                        self.btn_download.set_state("loading")
            else:
                self.btn_download.setToolTip("Download Movie")
                self.btn_download.set_state("idle")
                self.btn_download.setEnabled(True)

    def _on_probe_finished(self, tmdb_id, results, error_msg):
        if self.movie_data and str(self.movie_data.get("id")) == str(tmdb_id):
            if not error_msg and results:
                dialog = StreamSelectionDialog(results, self)
                if dialog.exec() == QDialog.Accepted:
                    sel = dialog.get_selection()
                    movie = self._last_details if self._last_details else self.movie_data
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
                    self.update_buttons()
            else:
                self.update_buttons()

    def _on_download_progress(self, tmdb_id, dl_info):
        if self.movie_data and str(self.movie_data.get("id")) == str(tmdb_id):
            percent = int(dl_info.get("percent", 0))
            if percent >= 0:
                self.btn_download.setToolTip(f"Downloading... {percent}%")
                self.btn_download.set_state("downloading", percent)

    def _on_download_status(self, tmdb_id, status):
        if self.movie_data and str(self.movie_data.get("id")) == str(tmdb_id):
            if status == "Completed" or status.startswith("Error") or status == "Paused":
                self.update_buttons() # Let update_buttons handle the colors for end states
            else:
                self.btn_download.setToolTip(status)
                if status in ["Probing...", "Initializing...", "Downloading...", "Pending selection..."]:
                    self.btn_download.set_state("loading")

    # ------------------------------------------------------------------
    # Image callbacks
    # ------------------------------------------------------------------
    def on_backdrop_loaded(self, image_data):
        if image_data:
            img = QImage()
            if img.loadFromData(image_data):
                self.backdrop_container.setPixmap(QPixmap.fromImage(img))

    def on_poster_loaded(self, image_data):
        if image_data:
            img = QImage()
            if img.loadFromData(image_data):
                pixmap = QPixmap(img).scaled(160, 240, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                self.poster_label.setPixmap(pixmap)
