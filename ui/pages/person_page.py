from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QScrollArea, QFrame, QSizePolicy)
from PySide6.QtCore import Qt, QRunnable, QThreadPool, Signal, QObject
from PySide6.QtGui import QPixmap, QIcon
import requests
import tmdb_api
from ui.movie_card import RoundedImage, ImageLoader, MovieCard
from ui.components import HorizontalCarousel

PERSON_CACHE = {}

class _PersonWorkerSignals(QObject):
    finished = Signal(dict)

class _PersonWorker(QRunnable):
    def __init__(self, person_id):
        super().__init__()
        self.person_id = person_id
        self.signals = _PersonWorkerSignals()

    def run(self):
        try:
            data = tmdb_api.get_person_details(self.person_id)
        except Exception as e:
            print(f"Error fetching person {self.person_id}: {e}")
            data = None
        try:
            self.signals.finished.emit(data or {})
        except RuntimeError:
            pass

class PersonPage(QWidget):
    def __init__(self, go_back_callback, change_status_callback, show_detail_callback, show_grid_callback=None):
        super().__init__()
        self.go_back_callback = go_back_callback
        self.change_status = change_status_callback
        self.show_detail = show_detail_callback
        self.show_grid = show_grid_callback

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Header: Back Button
        header = QFrame()
        header.setFixedHeight(60)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)

        self.back_btn = QPushButton("←")
        self.back_btn.setFixedSize(40, 40)
        self.back_btn.setCursor(Qt.PointingHandCursor)
        from ui.theme_manager import ThemeManager
        primary = ThemeManager.get_color("primary")
        self.back_btn.setStyleSheet(f"""
            QPushButton {{ background-color: transparent; color: white; font-weight: bold; font-size: 28px; border: none; }}
            QPushButton:hover {{ color: {primary}; }}
        """)
        self.back_btn.clicked.connect(self.go_back_callback)
        h_layout.addWidget(self.back_btn)
        h_layout.addStretch()

        self.layout.addWidget(header)

        # Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("border: none; background: transparent;")
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 20)
        self.content_layout.setSpacing(20)

        self.scroll.setWidget(self.content_widget)
        self.layout.addWidget(self.scroll)

        # Placeholder for loading
        self.loading_label = QLabel("Loading profile...")
        self.loading_label.setStyleSheet("color: #A0AEC0; font-size: 16px;")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(self.loading_label)
        
        self.profile_container = None
        self.carousel = None

    def load_person(self, person_id):
        # Clear existing
        if self.profile_container:
            self.content_layout.removeWidget(self.profile_container)
            self.profile_container.deleteLater()
            self.profile_container = None
        if self.carousel:
            self.content_layout.removeWidget(self.carousel)
            self.carousel.deleteLater()
            self.carousel = None
            
        self.loading_label.show()
        
        # Scroll to top
        self.scroll.verticalScrollBar().setValue(0)

        # ── Smart Cache Check ─────────────────────────────────────────
        if person_id in PERSON_CACHE:
            self._on_person_loaded(PERSON_CACHE[person_id])
            return

        worker = _PersonWorker(person_id)
        worker.signals.finished.connect(self._on_person_loaded)
        QThreadPool.globalInstance().start(worker)

    def _on_person_loaded(self, data):
        self.loading_label.hide()
        if not data:
            self.loading_label.setText("Failed to load person details.")
            self.loading_label.show()
            return

        # ── Smart Cache Store ─────────────────────────────────────────
        PERSON_CACHE[data["id"]] = data

        self.profile_container = QWidget()
        p_layout = QHBoxLayout(self.profile_container)
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.setSpacing(30)
        p_layout.setAlignment(Qt.AlignTop)

        # Image
        img_label = QLabel()
        img_label.setFixedSize(200, 300)
        img_label.setStyleSheet("background-color: #1A1C23; border-radius: 12px;")
        img_label.setAlignment(Qt.AlignCenter)
        
        if data.get("profile_path"):
            try:
                # Synchronous fetch for simplicity, though could be async
                r = requests.get(data["profile_path"], timeout=5)
                if r.status_code == 200:
                    pixmap = QPixmap()
                    pixmap.loadFromData(r.content)
                    pixmap = pixmap.scaled(200, 300, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                    img_label.setPixmap(pixmap)
            except:
                img_label.setText("No Image")
        else:
            img_label.setText("No Image")
            
        p_layout.addWidget(img_label)

        # Info
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setAlignment(Qt.AlignTop)

        name_lbl = QLabel(data.get("name", "Unknown"))
        name_lbl.setStyleSheet("font-size: 32px; font-weight: bold; color: white;")
        info_layout.addWidget(name_lbl)

        details_str = []
        if data.get("known_for_department"):
            details_str.append(data.get("known_for_department"))
        if data.get("birthday"):
            details_str.append(f"Born: {data.get('birthday')}")
        if data.get("place_of_birth"):
            details_str.append(data.get("place_of_birth"))
            
        if details_str:
            det_lbl = QLabel(" | ".join(details_str))
            det_lbl.setStyleSheet("font-size: 14px; color: #1AE0A1; font-weight: bold;")
            info_layout.addWidget(det_lbl)
            info_layout.addSpacing(10)

        bio = data.get("biography")
        if bio:
            bio_lbl = QLabel(bio)
            bio_lbl.setWordWrap(True)
            bio_lbl.setStyleSheet("font-size: 14px; color: #A0AEC0; line-height: 1.5;")
            info_layout.addWidget(bio_lbl)

        info_layout.addStretch()
        p_layout.addWidget(info_widget, 1)

        self.content_layout.addWidget(self.profile_container)
        
        credits = data.get("credits", [])
        if credits:
            self.content_layout.addSpacing(20)
            
            def handle_view_all():
                if self.show_grid:
                    self.show_grid(
                        f"Filmography: {data.get('name', 'Unknown')}", 
                        lambda page=1: tmdb_api.get_person_full_credits(data.get("id"), page=page),
                        {"with_cast": str(data.get("id")), "sort_by": "popularity.desc"}
                    )

            self.carousel = HorizontalCarousel(
                "Known For",
                credits[:10],
                lambda m: MovieCard(m, self.change_status, self.show_detail),
                on_view_all=handle_view_all if self.show_grid else None
            )
            self.content_layout.addWidget(self.carousel)
            
        from ui.theme_manager import ThemeManager
        ThemeManager.apply_theme_to_widget(self)
            
    def refresh_status(self):
        if self.carousel and hasattr(self.carousel, "refresh_status"):
            self.carousel.refresh_status()
