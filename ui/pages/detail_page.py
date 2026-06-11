from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QFrame, QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage, QPainter, QDesktopServices, QColor, QPainterPath
from ui.movie_card import RoundedImage, ImageLoader, MovieCard
from ui.components import HorizontalCarousel
from PySide6.QtCore import QThreadPool, QUrl
import tmdb_api

class BackdropFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.bg_pixmap = None

    def setPixmap(self, pixmap):
        self.bg_pixmap = pixmap
        self.update()

    def clearPixmap(self):
        self.bg_pixmap = None
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.bg_pixmap:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            
            path = QPainterPath()
            path.addRoundedRect(0, 0, self.width(), self.height(), 12, 12)
            painter.setClipPath(path)
            
            scaled_pm = self.bg_pixmap.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x = (self.width() - scaled_pm.width()) // 2
            y = (self.height() - scaled_pm.height()) // 2
            
            painter.drawPixmap(x, y, scaled_pm)
            painter.fillRect(0, 0, self.width(), self.height(), QColor(0, 0, 0, 180))

class MovieDetailPage(QWidget):
    def __init__(self, go_back_callback, change_status_callback, show_movie_detail_callback):
        super().__init__()
        self.go_back = go_back_callback
        self.change_status = change_status_callback
        self.show_movie_detail = show_movie_detail_callback
        self.movie_data = None
        
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
        self.btn_watched = QPushButton("Mark Watched")
        self.btn_watched.setCursor(Qt.PointingHandCursor)
        self.btn_watched.clicked.connect(lambda: self.change_status(self.movie_data, "remove" if self.movie_data.get("status") == "watched" else "watched"))
        
        self.btn_later = QPushButton("Watch Later")
        self.btn_later.setCursor(Qt.PointingHandCursor)
        self.btn_later.clicked.connect(lambda: self.change_status(self.movie_data, "remove" if self.movie_data.get("status") == "watch_later" else "watch_later"))
        
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
        info_layout.addSpacing(20)
        info_layout.addLayout(action_layout)
        info_layout.addStretch()
        
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
        self.trailers_layout.setContentsMargins(0,0,0,0)
        self.left_column.addWidget(self.trailers_container)
        self.left_column.addSpacing(30)
        
        self.similar_container = QWidget()
        self.similar_layout = QVBoxLayout(self.similar_container)
        self.similar_layout.setContentsMargins(0,0,0,0)
        self.left_column.addWidget(self.similar_container)
        self.left_column.addStretch()
        
        # --- Right Column: Facts Sidebar ---
        self.right_column = QVBoxLayout()
        self.right_column.setAlignment(Qt.AlignTop)
        self.right_column.setContentsMargins(20, 0, 0, 0) # Padding from left col
        
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
        
    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())
                item.layout().deleteLater()
                
    def load_movie(self, movie_data):
        self.movie_data = movie_data
        self.title_label.setText(movie_data.get("title", "Unknown"))
        
        # Clear previous images immediately
        self.poster_label.clear()
        self.backdrop_container.clearPixmap()
        
        self._clear_layout(self.trailers_layout)
        self._clear_layout(self.similar_layout)
        self.facts_label.setText("")
        
        # Fast path: Load poster from cache instantly to prevent UI blocking delay
        poster_path = movie_data.get("poster_path")
        if poster_path:
            cached_poster = ImageLoader.get_cached_image(poster_path)
            if cached_poster:
                self.on_poster_loaded(cached_poster)
                
        # Force the UI to paint the cached image immediately before the blocking API call
        QApplication.processEvents()
        
        # Load extended details (blocking call)
        details = tmdb_api.get_movie_details(movie_data["id"])
        if details:
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
            
            # --- Populate Left Column (Trailers) ---
            trailers = details.get("trailers", [])
            if trailers:
                lbl = QLabel("Videos & Trailers")
                lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: white; margin-bottom: 10px;")
                self.trailers_layout.addWidget(lbl)
                
                trailer_btns_layout = QHBoxLayout()
                trailer_btns_layout.setAlignment(Qt.AlignLeft)
                for t in trailers[:3]: # Max 3 buttons
                    name = t['name']
                    if len(name) > 35:
                        name = name[:32] + "..."
                    btn = QPushButton(f"▶ {name}")
                    btn.setStyleSheet("background-color: rgba(255,255,255,0.1); color: white; border-radius: 6px; padding: 10px; font-size: 13px;")
                    btn.setCursor(Qt.PointingHandCursor)
                    key = t['key']
                    btn.clicked.connect(lambda _, k=key: QDesktopServices.openUrl(QUrl(f"https://www.youtube.com/watch?v={k}")))
                    trailer_btns_layout.addWidget(btn)
                self.trailers_layout.addLayout(trailer_btns_layout)
                
            # --- Populate Left Column (Similar Movies) ---
            similar = details.get("similar", [])
            if similar:
                carousel = HorizontalCarousel(
                    "Similar Movies", 
                    similar, 
                    lambda m: MovieCard(m, self.change_status, self.show_movie_detail)
                )
                self.similar_layout.addWidget(carousel)
                
            # --- Populate Right Column (Facts) ---
            def format_money(amount):
                if not amount: return "-"
                if amount >= 1_000_000_000: return f"${amount/1_000_000_000:.1f}B"
                if amount >= 1_000_000: return f"${amount/1_000_000:.1f}M"
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
            
        else:
            self.meta_label.setText("Details unavailable")
            self.tagline_label.setVisible(False)
            self.credits_label.setVisible(False)
            self.overview_label.setText(movie_data.get("overview", ""))
            
        # Load images
        if movie_data.get("backdrop_path"):
            bd_loader = ImageLoader(movie_data["backdrop_path"])
            bd_loader.signals.finished.connect(self.on_backdrop_loaded)
            QThreadPool.globalInstance().start(bd_loader)
            
        if movie_data.get("poster_path"):
            poster_loader = ImageLoader(movie_data["poster_path"])
            poster_loader.signals.finished.connect(self.on_poster_loaded)
            QThreadPool.globalInstance().start(poster_loader)
            
        self.update_buttons()
        
    def update_buttons(self):
        status = self.movie_data.get("status")
        
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
