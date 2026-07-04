from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QApplication
)
from PySide6.QtCore import Qt, QThreadPool, QUrl, QRunnable, Signal, QObject
from PySide6.QtGui import QPixmap, QImage, QPainter, QDesktopServices, QColor, QPainterPath
from ui.movie_card import RoundedImage, ImageLoader, MovieCard
from ui.components import HorizontalCarousel
from ui.stream_dialog import StreamSelectionDialog
from ui.chrome_sniffer import ChromeSnifferDialog
import tmdb_api
from download_manager import DownloadManager
from PySide6.QtWidgets import QDialog, QWidget


# ---------------------------------------------------------------------------
# Worker: fetch movie details off the GUI thread
# ---------------------------------------------------------------------------
class _DetailWorkerSignals(QObject):
    finished = Signal(object)   # emits the details dict or None


class _DetailWorker(QRunnable):
    def __init__(self, movie_id):
        super().__init__()
        self.movie_id = movie_id
        self.signals = _DetailWorkerSignals()

    def run(self):
        try:
            details = tmdb_api.get_movie_details(self.movie_id)
        except Exception as e:
            print(f"DetailWorker error: {e}")
            details = None
        self.signals.finished.emit(details)


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
    def __init__(self, go_back_callback, change_status_callback, show_movie_detail_callback):
        super().__init__()
        self.go_back = go_back_callback
        self.change_status = change_status_callback
        self.show_movie_detail = show_movie_detail_callback
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
        back_btn.setStyleSheet("background-color: transparent; color: white; font-weight: bold; font-size: 28px; border: none;")
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
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 32px; font-weight: bold; color: white;")
        self.title_label.setWordWrap(True)

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
        self.btn_play = QPushButton("▶   Play Movie")
        self.btn_play.setCursor(Qt.PointingHandCursor)
        self.btn_play.setStyleSheet("""
            QPushButton {
                background-color: #E50914; color: white; border-radius: 6px;
                padding: 10px 24px; font-weight: bold; font-size: 14px; border: none;
            }
            QPushButton:hover { background-color: #F40612; }
        """)
        self.btn_play.clicked.connect(self.play_movie)

        self.btn_watched = QPushButton("Mark Watched")
        self.btn_watched.setCursor(Qt.PointingHandCursor)
        self.btn_watched.clicked.connect(
            lambda: self.change_status(
                self.movie_data,
                "remove" if self.movie_data.get("status") == "watched" else "watched"
            )
        )

        self.btn_later = QPushButton("Watch Later")
        self.btn_later.setCursor(Qt.PointingHandCursor)
        self.btn_later.clicked.connect(
            lambda: self.change_status(
                self.movie_data,
                "remove" if self.movie_data.get("status") == "watch_later" else "watch_later"
            )
        )

        self.btn_download = QPushButton("↓ Download")
        self.btn_download.setCursor(Qt.PointingHandCursor)
        self.btn_download.setStyleSheet("""
            QPushButton {
                background-color: #8a2be2; color: white; border-radius: 6px;
                padding: 10px 24px; font-weight: bold; font-size: 14px; border: none;
            }
            QPushButton:hover { background-color: #9b4dca; }
        """)
        self.btn_download.clicked.connect(self.download_movie)

        action_layout.addWidget(self.btn_play)
        action_layout.addWidget(self.btn_download)
        action_layout.addWidget(self.btn_watched)
        action_layout.addWidget(self.btn_later)
        action_layout.addStretch()

        info_layout.addWidget(self.title_label)
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

        self.trailers_container = QWidget()
        self.trailers_layout = QVBoxLayout(self.trailers_container)
        self.trailers_layout.setContentsMargins(0, 0, 0, 0)
        self.left_column.addWidget(self.trailers_container)
        self.left_column.addSpacing(30)

        self.similar_container = QWidget()
        self.similar_layout = QVBoxLayout(self.similar_container)
        self.similar_layout.setContentsMargins(0, 0, 0, 0)
        self.left_column.addWidget(self.similar_container)
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
        if tmdb_id:
            import webbrowser
            url = f"https://vidsrc.sbs/embed/movie/{tmdb_id}"
            print(f"[Player] Opening system browser: {url}")
            webbrowser.open(url)

    def download_movie(self):
        if not self.movie_data:
            return
            
        tmdb_id = self.movie_data.get("id")
        manager = DownloadManager()
        
        # Check current status
        dl_info = manager.active_downloads.get(tmdb_id)
        if dl_info:
            status = dl_info.get("status", "")
            if status == "Paused":
                manager.resume_download(tmdb_id)
                self.btn_download.setText("Initializing...")
                return
            elif status == "Pending selection...":
                pass # allow re-opening dialog if needed
            elif status not in ("Completed", "Error", "Download Failed", "Error: Restart required") and not status.startswith("Error"):
                manager.pause_download(tmdb_id)
                return
        
        # Ensure download manager is passed to detail page during setup
        if not hasattr(self, "download_manager") or not self.download_manager:
            return

        movie_id = str(self.movie_data.get('id', ''))
        if not movie_id:
            return

        # Native Chrome Sniffer approach
        dialog = ChromeSnifferDialog(movie_id, self)
        if dialog.exec():
            selection = dialog.get_selection()
            if selection and selection.get('m3u8_url'):
                # Pass to download_manager to do the fast probe and trigger stream selection
                self.btn_download.setText("Fetching options...")
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
        self._clear_layout(self.trailers_layout)
        self._clear_layout(self.similar_layout)
        self.facts_label.setText("")
        self.btn_download.setText("↓ Download")
        self.btn_download.setEnabled(True)
        self.update_buttons()

        # ── Fast-path: serve poster from cache if available ───────────
        poster_path = movie_data.get("poster_path")
        if poster_path:
            cached = ImageLoader.get_cached_image(poster_path)
            if cached:
                self.on_poster_loaded(cached)

        # ── Kick off the details worker (non-blocking) ────────────────
        worker = _DetailWorker(movie_id)
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

        # Re-inject fresh DB status (details cache may have been stale)
        import tmdb_api
        tmdb_api.inject_db_status([self.movie_data])

        date = details.get("release_date", "")[:4]
        runtime = details.get("runtime", 0)
        genres = ", ".join(details.get("genres", []))
        rating = round(details.get("vote_average", 0), 1)
        self.meta_label.setText(f"{date} • {runtime} min • {genres} • ⭐ {rating}/10")

        tagline = details.get("tagline")
        self.tagline_label.setText(f'"{tagline}"' if tagline else "")
        self.tagline_label.setVisible(bool(tagline))

        director = details.get("director", "Unknown")
        cast = ", ".join(details.get("cast", []))
        self.credits_label.setText(f"<b>Director:</b> {director}<br><b>Cast:</b> {cast}")
        self.credits_label.setVisible(True)

        self.overview_label.setText(details.get("overview", "No overview available."))

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

        # --- Similar Movies ---
        similar = details.get("similar", [])
        if similar:
            carousel = HorizontalCarousel(
                "Similar Movies",
                similar,
                lambda m: MovieCard(m, self.change_status, self.show_movie_detail)
            )
            self.similar_layout.addWidget(carousel)

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
            facts_html += f'<p><b>Homepage</b><br><a href="{details["homepage"]}" style="color: #1AE0A1;">Visit Site</a></p>'

        self.facts_label.setText(facts_html)
        self.facts_label.setOpenExternalLinks(True)

        self.update_buttons()

    # ------------------------------------------------------------------
    # Button state
    # ------------------------------------------------------------------
    def update_buttons(self):
        status = self.movie_data.get("status") if self.movie_data else None

        if status == "watched":
            self.btn_watched.setText("✓ Watched")
            self.btn_watched.setStyleSheet("""
                QPushButton { background-color: #14B885; color: #0F172A; border-radius: 6px; padding: 10px 20px; font-weight: bold; font-size: 14px; border: none; }
                QPushButton:hover { background-color: #1AE0A1; }
            """)
        else:
            self.btn_watched.setText("Mark Watched")
            self.btn_watched.setStyleSheet("""
                QPushButton { background-color: #1AE0A1; color: #0F172A; border-radius: 6px; padding: 10px 20px; font-weight: bold; font-size: 14px; border: none; }
                QPushButton:hover { background-color: #14B885; }
            """)

        if status == "watch_later":
            self.btn_later.setText("✓ Watch Later")
            self.btn_later.setStyleSheet("""
                QPushButton { background-color: transparent; color: #1AE0A1; border: 1.5px solid #1AE0A1; border-radius: 6px; padding: 10px 20px; font-weight: bold; font-size: 14px; }
                QPushButton:hover { background-color: rgba(26, 224, 161, 0.1); }
            """)
        else:
            self.btn_later.setText("Watch Later")
            self.btn_later.setStyleSheet("""
                QPushButton { background-color: transparent; color: white; border: 1.5px solid rgba(255,255,255,0.6); border-radius: 6px; padding: 10px 20px; font-weight: bold; font-size: 14px; }
                QPushButton:hover { background-color: rgba(255,255,255,0.1); border-color: white; color: white; }
            """)

        # Download button state
        tmdb_id = self.movie_data.get("id") if self.movie_data else None
        if tmdb_id:
            dl_info = self.download_manager.active_downloads.get(tmdb_id)
            if dl_info:
                status = dl_info.get("status", "")
                if status == "Completed":
                    self.btn_download.setText("✓ Downloaded")
                    self.btn_download.setStyleSheet("""
                        QPushButton { background-color: #14B885; color: #0F172A; border-radius: 6px; padding: 10px 24px; font-weight: bold; font-size: 14px; border: none; }
                        QPushButton:hover { background-color: #1AE0A1; }
                    """)
                    self.btn_download.setEnabled(True)
                elif status.startswith("Error"):
                    self.btn_download.setText("Download Failed")
                    self.btn_download.setStyleSheet("""
                        QPushButton { background-color: #E50914; color: white; border-radius: 6px; padding: 10px 24px; font-weight: bold; font-size: 14px; border: none; }
                        QPushButton:hover { background-color: #F40612; }
                    """)
                    self.btn_download.setEnabled(True)
                elif status == "Paused":
                    self.btn_download.setText("▶ Resume")
                    self.btn_download.setStyleSheet("""
                        QPushButton { background-color: #ff9800; color: white; border-radius: 6px; padding: 10px 24px; font-weight: bold; font-size: 14px; border: none; }
                        QPushButton:hover { background-color: #e68a00; }
                    """)
                    self.btn_download.setEnabled(True)
                else:
                    percent = int(dl_info.get("percent", 0))
                    if percent > 0:
                        self.btn_download.setText(f"⏸ Downloading... {percent}%")
                        self.btn_download.setEnabled(True)
                        self.btn_download.setStyleSheet(f"""
                            QPushButton {{
                                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8a2be2, stop:{percent/100.0} #8a2be2, stop:{percent/100.0} #3c1464, stop:1 #3c1464);
                                color: white; border-radius: 6px; padding: 10px 24px; font-weight: bold; font-size: 14px; border: none;
                            }}
                            QPushButton:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9b4dca, stop:{percent/100.0} #9b4dca, stop:{percent/100.0} #4d1a80, stop:1 #4d1a80); }}
                        """)
                    else:
                        self.btn_download.setText(f"⏸ {status}")
                        self.btn_download.setEnabled(True)
                        self.btn_download.setStyleSheet("""
                            QPushButton { background-color: #8a2be2; color: white; border-radius: 6px; padding: 10px 24px; font-weight: bold; font-size: 14px; border: none; }
                            QPushButton:hover { background-color: #9b4dca; }
                        """)
            else:
                self.btn_download.setText("↓ Download")
                self.btn_download.setStyleSheet("""
                    QPushButton {
                        background-color: #8a2be2; color: white; border-radius: 6px;
                        padding: 10px 24px; font-weight: bold; font-size: 14px; border: none;
                    }
                    QPushButton:hover { background-color: #9b4dca; }
                """)
                self.btn_download.setEnabled(True)

    def _on_probe_finished(self, tmdb_id, results, error_msg):
        if self.movie_data and self.movie_data.get("id") == tmdb_id:
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
        if self.movie_data and self.movie_data.get("id") == tmdb_id:
            percent = int(dl_info.get("percent", 0))
            if percent > 0:
                self.btn_download.setText(f"⏸ Downloading... {percent}%")
                self.btn_download.setStyleSheet(f"""
                    QPushButton {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8a2be2, stop:{percent/100.0} #8a2be2, stop:{percent/100.0} #3c1464, stop:1 #3c1464);
                        color: white; border-radius: 6px; padding: 10px 24px; font-weight: bold; font-size: 14px; border: none;
                    }}
                    QPushButton:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9b4dca, stop:{percent/100.0} #9b4dca, stop:{percent/100.0} #4d1a80, stop:1 #4d1a80); }}
                """)

    def _on_download_status(self, tmdb_id, status):
        if self.movie_data and self.movie_data.get("id") == tmdb_id:
            if status == "Completed" or status.startswith("Error") or status == "Paused":
                self.update_buttons() # Let update_buttons handle the colors for end states
            else:
                self.btn_download.setText(f"⏸ {status}")

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
