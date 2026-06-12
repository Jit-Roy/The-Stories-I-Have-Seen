from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QStackedWidget
from PySide6.QtCore import Qt, QRunnable, QThreadPool, Signal, QObject
import database
import tmdb_api

from ui.pages.home_page import HomePage
from ui.pages.collection_page import CollectionPage
from ui.pages.wishlist_page import WishlistPage
from ui.pages.detail_page import MovieDetailPage
from ui.pages.grid_page import GridPage


# ---------------------------------------------------------------------------
# Worker: fetch details + write DB off the GUI thread
# ---------------------------------------------------------------------------
class _StatusWorkerSignals(QObject):
    finished = Signal(object, str)   # movie_data dict, new_status


class _StatusWorker(QRunnable):
    """Used when change_status is triggered from a carousel card (no cached details)."""
    def __init__(self, movie_data, new_status):
        super().__init__()
        self.movie_data = movie_data
        self.new_status = new_status
        self.signals = _StatusWorkerSignals()

    def run(self):
        try:
            details = tmdb_api.get_movie_details(self.movie_data["id"])
            series_name = details.get("series_name") if details else None
            vote_average = details.get("vote_average") if details else self.movie_data.get("vote_average")
            release_date = details.get("release_date") if details else self.movie_data.get("release_date")
        except Exception:
            series_name = None
            vote_average = self.movie_data.get("vote_average")
            release_date = self.movie_data.get("release_date")

        database.add_movie(
            self.movie_data["id"],
            self.movie_data["title"],
            self.movie_data["poster_path"],
            self.new_status,
            series_name,
            vote_average,
            release_date,
        )
        tmdb_api.invalidate_db_cache()
        self.signals.finished.emit(self.movie_data, self.new_status)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("The Stories I Carry")
        self.setMinimumSize(1200, 800)
        self.page_history = []

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QHBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.setup_left_sidebar()

        self.center_area = QWidget()
        self.center_layout = QVBoxLayout(self.center_area)
        self.center_layout.setContentsMargins(30, 20, 30, 20)

        self.setup_top_nav()

        self.stack = QStackedWidget()
        self.stack.currentChanged.connect(self._on_page_changed)

        self.home_page = HomePage(self.change_status, self.show_movie_detail, self.show_grid_view)
        self.collection_page = CollectionPage(self.change_status, self.show_movie_detail)
        self.wishlist_page = WishlistPage(self.change_status, self.show_movie_detail)
        self.detail_page = MovieDetailPage(self.go_back_to_previous_page, self.change_status, self.show_movie_detail)
        self.grid_page = GridPage(self.go_back_to_previous_page, self.change_status, self.show_movie_detail)

        self.stack.addWidget(self.home_page)       # 0
        self.stack.addWidget(self.collection_page) # 1
        self.stack.addWidget(self.wishlist_page)   # 2
        self.stack.addWidget(self.detail_page)     # 3
        self.stack.addWidget(self.grid_page)       # 4

        self.center_layout.addWidget(self.stack)
        self.layout.addWidget(self.center_area, 1)

        # Load initial data for lists
        self.collection_page.load_lists()
        self.wishlist_page.load_lists()

    def setup_left_sidebar(self):
        self.left_sidebar = QWidget()
        self.left_sidebar.setObjectName("leftSidebar")
        self.left_sidebar.setStyleSheet("#leftSidebar { background-color: #11131A; border-right: 1px solid #1E202B; }")
        self.left_sidebar.setFixedWidth(255)
        layout = QVBoxLayout(self.left_sidebar)
        layout.setAlignment(Qt.AlignTop)
        # Reduced right margin to 10 to give the title text more room
        layout.setContentsMargins(20, 30, 10, 20)

        logo_container = QWidget()
        logo_layout = QHBoxLayout(logo_container)
        logo_layout.setContentsMargins(0, 0, 0, 10)
        logo_layout.setAlignment(Qt.AlignLeft)

        from PySide6.QtGui import QIcon

        logo_icon = QLabel()
        logo_icon.setStyleSheet("background-color: transparent; border: none;")
        logo_icon.setPixmap(QIcon("assets/icons/main_logo.svg").pixmap(36, 36))

        logo_text = QLabel("The Stories I Carry")
        logo_text.setStyleSheet("font-size: 15px; font-weight: bold; color: white; background-color: transparent; border: none;")

        logo_layout.addWidget(logo_icon)
        logo_layout.addSpacing(6)
        logo_layout.addWidget(logo_text)
        logo_layout.addStretch()

        layout.addWidget(logo_container)
        layout.addSpacing(30)

        from PySide6.QtGui import QIcon

        nav_style = """
            QPushButton {
                background-color: transparent; color: #A0AEC0; text-align: left;
                padding: 12px 16px; border-radius: 8px; font-size: 14px; font-weight: 500; border: none;
            }
            QPushButton:hover {
                color: #FFFFFF; background-color: #1A1C23;
            }
            QPushButton:checked {
                color: #1AE0A1; background-color: rgba(255, 255, 255, 0.05); border-left: 3px solid #1AE0A1;
                border-top-left-radius: 0px; border-bottom-left-radius: 0px;
            }
        """

        self.home_btn = QPushButton("  Home")
        self.home_btn.setStyleSheet(nav_style)
        self.home_btn.setCheckable(True)
        self.home_btn.clicked.connect(lambda: self.switch_page(0, self.home_btn))
        layout.addWidget(self.home_btn)

        self.col_btn = QPushButton("  Collection")
        self.col_btn.setStyleSheet(nav_style)
        self.col_btn.setCheckable(True)
        self.col_btn.clicked.connect(lambda: self.switch_page(1, self.col_btn))
        layout.addWidget(self.col_btn)

        self.wish_btn = QPushButton("  Wishlist")
        self.wish_btn.setStyleSheet(nav_style)
        self.wish_btn.setCheckable(True)
        self.wish_btn.clicked.connect(lambda: self.switch_page(2, self.wish_btn))
        layout.addWidget(self.wish_btn)

        self.home_btn.toggled.connect(self.update_nav_icons)
        self.col_btn.toggled.connect(self.update_nav_icons)
        self.wish_btn.toggled.connect(self.update_nav_icons)

        self.home_btn.setChecked(True)
        self.update_nav_icons()

        layout.addStretch()
        self.layout.addWidget(self.left_sidebar)

    def update_nav_icons(self):
        from PySide6.QtGui import QIcon
        self.home_btn.setIcon(QIcon("assets/icons/home_active.svg" if self.home_btn.isChecked() else "assets/icons/home.svg"))
        self.col_btn.setIcon(QIcon("assets/icons/collection_active.svg" if self.col_btn.isChecked() else "assets/icons/collection.svg"))
        self.wish_btn.setIcon(QIcon("assets/icons/wishlist_active.svg" if self.wish_btn.isChecked() else "assets/icons/wishlist.svg"))

    def switch_page(self, index, active_btn):
        self.stack.setCurrentIndex(index)
        self.page_history.clear()
        self.home_btn.setChecked(False)
        self.col_btn.setChecked(False)
        self.wish_btn.setChecked(False)
        active_btn.setChecked(True)
        if index == 1:
            self.collection_page.load_lists()
        elif index == 2:
            self.wishlist_page.load_lists()
        elif index == 0:
            import ui.components as components
            self.home_page.filter_bar.set_params(components.GLOBAL_FILTER_STATE)

    def show_movie_detail(self, movie_data):
        current_index = self.stack.currentIndex()
        state = self.detail_page.movie_data if current_index == 3 else None
        self.page_history.append((current_index, state))
        # Inject fresh DB status so buttons are correct from the very first render
        tmdb_api.inject_db_status([movie_data])
        self.detail_page.load_movie(movie_data)
        self.stack.setCurrentIndex(3)

    def show_grid_view(self, title, fetch_func, initial_params=None):
        current_index = self.stack.currentIndex()
        state = self.detail_page.movie_data if current_index == 3 else None
        self.page_history.append((current_index, state))
        self.grid_page.load_grid(title, fetch_func, initial_params)
        self.stack.setCurrentIndex(4)

    def setup_top_nav(self):
        from PySide6.QtWidgets import (
            QLineEdit, QHBoxLayout, QLabel, QFrame, QGraphicsDropShadowEffect
        )
        from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QByteArray
        from PySide6.QtGui import QColor, QPixmap, QPainter, QShortcut, QKeySequence
        from PySide6.QtSvg import QSvgRenderer

        # ── Wrapper frame ──────────────────────────────────────────────────────
        self.search_wrapper = QFrame()
        self.search_wrapper.setObjectName("search_wrapper")
        self.search_wrapper.setFixedHeight(48)

        wrapper_layout = QHBoxLayout(self.search_wrapper)
        wrapper_layout.setContentsMargins(16, 0, 16, 0)
        wrapper_layout.setSpacing(12)

        # ── SVG search icon ────────────────────────────────────────────────────
        icon_svg = b"""<svg width="16" height="16" viewBox="0 0 16 16" fill="none"
            xmlns="http://www.w3.org/2000/svg">
            <circle cx="6.5" cy="6.5" r="5" stroke="#4A5070" stroke-width="1.5"/>
            <path d="M11 11L14 14" stroke="#4A5070" stroke-width="1.5"
                stroke-linecap="round"/>
        </svg>"""
        renderer = QSvgRenderer(QByteArray(icon_svg))
        icon_pix = QPixmap(16, 16)
        icon_pix.fill(Qt.transparent)
        p = QPainter(icon_pix)
        renderer.render(p)
        p.end()

        icon_label = QLabel()
        icon_label.setPixmap(icon_pix)
        icon_label.setFixedSize(20, 20)
        icon_label.setAlignment(Qt.AlignCenter)

        # ── Thin vertical divider ──────────────────────────────────────────────
        divider = QFrame()
        divider.setFrameShape(QFrame.VLine)
        divider.setFixedSize(1, 18)
        divider.setStyleSheet("background: #252836; border: none;")

        # ── Input ──────────────────────────────────────────────────────────────
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search movies, actors, keywords…")
        self.search_bar.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #DDE0FF;
                font-size: 14px;
                letter-spacing: 0.1px;
            }
        """)
        self.search_bar.returnPressed.connect(self.perform_search)
        self.search_bar.installEventFilter(self)

        wrapper_layout.addWidget(icon_label)
        wrapper_layout.addWidget(divider)
        wrapper_layout.addWidget(self.search_bar, 1)

        # ── Glow effect + animation ────────────────────────────────────────────
        self.search_glow = QGraphicsDropShadowEffect()
        self.search_glow.setBlurRadius(0)
        self.search_glow.setColor(QColor(26, 224, 161, 70))
        self.search_glow.setOffset(0, 0)
        self.search_wrapper.setGraphicsEffect(self.search_glow)

        self._glow_anim = QPropertyAnimation(self.search_glow, b"blurRadius")
        self._glow_anim.setDuration(220)
        self._glow_anim.setEasingCurve(QEasingCurve.OutCubic)

        # ── Ctrl+K shortcut ────────────────────────────────────────────────────
        QShortcut(QKeySequence("Ctrl+K"), self).activated.connect(
            self.search_bar.setFocus
        )

        self._set_search_style(focused=False)

        self.center_layout.addWidget(self.search_wrapper)
        self.center_layout.addSpacing(5)

    def _set_search_style(self, focused: bool):
        border = "#1AE0A1" if focused else "#1E2030"
        bg     = "#0B0D16" if focused else "#0D0F18"
        self.search_wrapper.setStyleSheet(f"""
            QFrame#search_wrapper {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 24px;
            }}
        """)
        self._glow_anim.stop()
        self._glow_anim.setStartValue(self.search_glow.blurRadius())
        self._glow_anim.setEndValue(26.0 if focused else 0.0)
        self._glow_anim.start()

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj is self.search_bar:
            if event.type() == QEvent.Type.FocusIn:
                self._set_search_style(focused=True)
            elif event.type() == QEvent.Type.FocusOut:
                self._set_search_style(focused=False)
        return super().eventFilter(obj, event)

    def perform_search(self):
        # Hitting Enter in the search bar acts exactly like clicking "Discover"
        if self.stack.currentIndex() == 4:
            self.grid_page.filter_bar._apply()
        else:
            self.home_page.filter_bar._apply()

    def go_back_to_previous_page(self):
        if not self.page_history:
            self.home_btn.setChecked(True)
            self.stack.setCurrentIndex(0)
            return

        prev_index, state = self.page_history.pop()

        self.home_btn.setChecked(False)
        self.col_btn.setChecked(False)
        self.wish_btn.setChecked(False)

        if prev_index == 0:
            self.home_btn.setChecked(True)
            import ui.components as components
            self.home_page.filter_bar.set_params(components.GLOBAL_FILTER_STATE)
        elif prev_index == 1:
            self.col_btn.setChecked(True)
            self.collection_page.load_lists()
        elif prev_index == 2:
            self.wish_btn.setChecked(True)
            self.wishlist_page.load_lists()
        elif prev_index == 3 and state:
            self.detail_page.load_movie(state)

        self.stack.setCurrentIndex(prev_index)

    def _on_page_changed(self, index):
        if hasattr(self, "search_wrapper"):
            if index == 0:
                self.search_wrapper.setVisible(True)
            elif index == 4:
                # Only show search bar if GridPage is in 'Discover' mode (filter_bar is visible)
                self.search_wrapper.setVisible(self.grid_page.filter_bar.isVisible())
            else:
                self.search_wrapper.setVisible(False)

    # ------------------------------------------------------------------
    # change_status — non-blocking; uses cached details when available
    # ------------------------------------------------------------------
    def change_status(self, movie_data, new_status):
        if new_status == "remove":
            database.remove_movie(movie_data["id"])
            movie_data["status"] = None
            tmdb_api.invalidate_db_cache()
            self._post_status_update(movie_data, new_status)
            return

        # Optimistic UI update so buttons feel instant
        movie_data["status"] = new_status
        if self.stack.currentIndex() == 3:
            self.detail_page.update_buttons()

        # If we already have the details from the open detail page, use them directly
        cached_details = (
            self.detail_page._last_details
            if self.stack.currentIndex() == 3
            and self.detail_page._last_details is not None
            and self.detail_page._last_details.get("id") == movie_data["id"]
            else None
        )

        if cached_details:
            # Synchronous DB write (very fast, local SQLite)
            database.add_movie(
                movie_data["id"],
                movie_data["title"],
                movie_data["poster_path"],
                new_status,
                cached_details.get("series_name"),
                cached_details.get("vote_average") or movie_data.get("vote_average"),
                cached_details.get("release_date") or movie_data.get("release_date"),
            )
            tmdb_api.invalidate_db_cache()
            self._post_status_update(movie_data, new_status)
        else:
            # Triggered from a carousel card — fetch details asynchronously
            worker = _StatusWorker(movie_data, new_status)
            worker.signals.finished.connect(self._post_status_update)
            QThreadPool.globalInstance().start(worker)

    def _post_status_update(self, movie_data, new_status):
        """Refresh dependent views after a status change."""
        self.collection_page.load_lists()
        self.wishlist_page.load_lists()
        if self.stack.currentIndex() == 3:
            self.detail_page.update_buttons()
        # Keep the hero banner buttons in sync no matter where the change came from
        if hasattr(self.home_page, "hero_carousel") and self.home_page.hero_carousel is not None:
            self.home_page.hero_carousel.refresh_status()
