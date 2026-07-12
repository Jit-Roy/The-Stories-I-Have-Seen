from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QStackedWidget
from PySide6.QtCore import Qt, QRunnable, QThreadPool, Signal, QObject
import database
import tmdb_api

from ui.pages.discover_page import DiscoverPage
from ui.pages.movies_page import MoviesPage
from ui.pages.tv_page import TvPage
from ui.pages.collection_page import CollectionPage
from ui.pages.wishlist_page import WishlistPage
from ui.pages.detail_page import MovieDetailPage
from ui.pages.grid_page import GridPage
from ui.pages.person_page import PersonPage
from ui.pages.season_page import SeasonPage
from ui.pages.analytics_page import AnalyticsPage
from ui.pages.downloads_page import DownloadsPage
from ui.pages.settings_page import SettingsPage
from ui.theme_manager import ThemeManager


class TabStack(QStackedWidget):
    def __init__(self, tab_index, parent=None):
        super().__init__(parent)
        self.tab_index = tab_index
        self.page_history = []
        self.is_text_search = False
        self.main_page = None
        self.detail_page = None
        self.grid_page = None
        self.person_page = None
        self.season_page = None


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
            media_type = self.movie_data.get("media_type", "movie")
            if media_type == "tv":
                details = tmdb_api.get_tv_details(self.movie_data["id"])
            else:
                details = tmdb_api.get_movie_details(self.movie_data["id"])
            series_name = details.get("series_name") if details else None
            vote_average = details.get("vote_average") if details else self.movie_data.get("vote_average")
            release_date = details.get("release_date") if details else self.movie_data.get("release_date")
            prod_countries = details.get("production_countries") if details else None
        except Exception:
            series_name = None
            vote_average = self.movie_data.get("vote_average")
            release_date = self.movie_data.get("release_date")
            prod_countries = None

        database.add_movie(
            self.movie_data["id"],
            self.movie_data.get("title") or self.movie_data.get("name", "Unknown"),
            self.movie_data.get("poster_path"),
            self.new_status,
            series_name,
            vote_average,
            release_date,
            runtime=details.get("runtime") if details else None,
            genres=details.get("genres") if details else None,
            director=details.get("director") if details else None,
            cast=details.get("cast") if details else None,
            production_companies=details.get("production_companies") if details else None,
            original_language=details.get("original_language") if details else None,
            production_countries=prod_countries,
            media_type=self.movie_data.get("media_type", "movie")
        )
        tmdb_api.invalidate_db_cache()
        try:
            self.signals.finished.emit(self.movie_data, self.new_status)
        except RuntimeError:
            pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("The Stories I Carry")
        self.setMinimumSize(1200, 800)
        
        from PySide6.QtGui import QIcon
        self.setWindowIcon(QIcon("assets/icons/app_icon.ico"))
        
        self.all_detail_pages = []
        self.all_grid_pages = []

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

        self.main_stack = QStackedWidget()
        self._current_main_index = 0
        self.main_stack.currentChanged.connect(self._on_tab_changed)
        self.tab_search_texts = {} 

        self.discover_page = DiscoverPage(self.change_status, self.show_movie_detail, self.show_person_detail, self.show_grid_view)
        self.movies_page = MoviesPage(self.change_status, self.show_movie_detail, self.show_grid_view)
        self.tv_page = TvPage(self.change_status, self.show_movie_detail, self.show_grid_view)
        
        self.collection_page = CollectionPage(self.change_status, self.show_movie_detail)
        self.wishlist_page = WishlistPage(self.change_status, self.show_movie_detail)
        self.analytics_page = AnalyticsPage(self.show_grid_view)
        self.downloads_page = DownloadsPage()
        self.settings_page = SettingsPage()
        self.settings_page.api_key_changed.connect(self._on_api_key_changed)

        self.current_media_type = "movie"

        # Create a TabStack for each main tab
        self.tab_stacks = {}
        # Indices: 0: Discover, 1: Movies, 2: TV, 3: Collection, 4: Wishlist, 5: Analytics, 6: Downloads, 7: Settings
        for idx, main_widget in enumerate([self.discover_page, self.movies_page, self.tv_page, self.collection_page, self.wishlist_page, self.analytics_page, self.downloads_page, self.settings_page]):
            
            t_stack = TabStack(idx)
            t_stack.addWidget(main_widget) # Inner Index 0
            t_stack.main_page = main_widget
            
            # Add dedicated Detail and Grid pages if applicable
            if idx in (0, 1, 2, 3, 4, 5):
                detail = MovieDetailPage(self.go_back_to_previous_page, self.change_status, self.show_movie_detail, self.show_person_detail, self.show_grid_view, self.show_season_detail)
                grid = GridPage(self.go_back_to_previous_page, self.change_status, self.show_movie_detail)
                person = PersonPage(self.go_back_to_previous_page, self.change_status, self.show_movie_detail, self.show_grid_view)
                season = SeasonPage(self.go_back_to_previous_page)
                t_stack.addWidget(detail) # Inner Index 1
                t_stack.addWidget(grid)   # Inner Index 2
                t_stack.addWidget(person) # Inner Index 3
                t_stack.addWidget(season) # Inner Index 4
                t_stack.detail_page = detail
                t_stack.grid_page = grid
                t_stack.person_page = person
                t_stack.season_page = season
                self.all_detail_pages.append(detail)
                self.all_grid_pages.append(grid)
                
            t_stack.currentChanged.connect(self._on_inner_page_changed)
            self.tab_stacks[idx] = t_stack
            self.main_stack.addWidget(t_stack)

        self.center_layout.addWidget(self.main_stack)
        self.layout.addWidget(self.center_area, 1)

        # Load initial data for lists
        self.collection_page.load_lists()
        self.wishlist_page.load_lists()
        
        self.collection_dirty = False
        self.wishlist_dirty = False
        self.analytics_dirty = False
        
        ThemeManager.apply_theme_to_app()

    def _on_api_key_changed(self):
        # Refresh grid pages when the API key is updated
        self.discover_page.load_discover_content()
        self.movies_page.load_content()
        self.tv_page.load_content()

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

        self.logo_icon = QLabel()
        self.logo_icon.setStyleSheet("background-color: transparent; border: none;")
        self.logo_icon.setPixmap(QIcon("assets/icons/main_logo.svg").pixmap(36, 36))

        logo_text = QLabel("The Stories I Carry")
        logo_text.setStyleSheet("font-size: 15px; font-weight: bold; color: white; background-color: transparent; border: none;")

        logo_layout.addWidget(self.logo_icon)
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
        # Removed sub_nav_style to prevent buttons from looking like sub-menus

        self.discover_btn = QPushButton("  Discover")
        self.discover_btn.setStyleSheet(nav_style)
        self.discover_btn.setCheckable(True)
        self.discover_btn.clicked.connect(lambda: self.switch_page(0, self.discover_btn))
        layout.addWidget(self.discover_btn)

        self.movies_btn = QPushButton("  Movies")
        self.movies_btn.setStyleSheet(nav_style)
        self.movies_btn.setCheckable(True)
        self.movies_btn.clicked.connect(lambda: self.switch_page(1, self.movies_btn))
        layout.addWidget(self.movies_btn)

        self.tv_btn = QPushButton("  TV Series")
        self.tv_btn.setStyleSheet(nav_style)
        self.tv_btn.setCheckable(True)
        self.tv_btn.clicked.connect(lambda: self.switch_page(2, self.tv_btn))
        layout.addWidget(self.tv_btn)

        self.col_btn = QPushButton("  Collection")
        self.col_btn.setStyleSheet(nav_style)
        self.col_btn.setCheckable(True)
        self.col_btn.clicked.connect(lambda: self.switch_page(3, self.col_btn))
        layout.addWidget(self.col_btn)

        self.wish_btn = QPushButton("  Wishlist")
        self.wish_btn.setStyleSheet(nav_style)
        self.wish_btn.setCheckable(True)
        self.wish_btn.clicked.connect(lambda: self.switch_page(4, self.wish_btn))
        layout.addWidget(self.wish_btn)

        self.analytics_btn = QPushButton("  Analytics")
        self.analytics_btn.setStyleSheet(nav_style)
        self.analytics_btn.setCheckable(True)
        self.analytics_btn.clicked.connect(lambda: self.switch_page(5, self.analytics_btn))
        layout.addWidget(self.analytics_btn)

        self.downloads_btn = QPushButton("  Downloads")
        self.downloads_btn.setStyleSheet(nav_style)
        self.downloads_btn.setCheckable(True)
        self.downloads_btn.clicked.connect(lambda: self.switch_page(6, self.downloads_btn))
        layout.addWidget(self.downloads_btn)

        self.discover_btn.toggled.connect(self.update_nav_icons)
        self.movies_btn.toggled.connect(self.update_nav_icons)
        self.tv_btn.toggled.connect(self.update_nav_icons)
        self.col_btn.toggled.connect(self.update_nav_icons)
        self.wish_btn.toggled.connect(self.update_nav_icons)
        self.analytics_btn.toggled.connect(self.update_nav_icons)
        self.downloads_btn.toggled.connect(self.update_nav_icons)

        layout.addStretch()
        
        self.settings_btn = QPushButton("  Settings")
        self.settings_btn.setStyleSheet(nav_style)
        self.settings_btn.setCheckable(True)
        self.settings_btn.clicked.connect(lambda: self.switch_page(7, self.settings_btn))
        self.settings_btn.toggled.connect(self.update_nav_icons)
        layout.addWidget(self.settings_btn)

        self.discover_btn.setChecked(True)
        self.update_nav_icons()
        
        self.layout.addWidget(self.left_sidebar)

    def update_nav_icons(self):
        from PySide6.QtGui import QIcon
        self.discover_btn.setIcon(QIcon("assets/icons/discover_active.svg" if self.discover_btn.isChecked() else "assets/icons/discover.svg"))
        self.movies_btn.setIcon(QIcon("assets/icons/movies_active.svg" if self.movies_btn.isChecked() else "assets/icons/movies.svg"))
        self.tv_btn.setIcon(QIcon("assets/icons/tv_active.svg" if self.tv_btn.isChecked() else "assets/icons/tv.svg"))
        self.col_btn.setIcon(QIcon("assets/icons/collection_active.svg" if self.col_btn.isChecked() else "assets/icons/collection.svg"))
        self.wish_btn.setIcon(QIcon("assets/icons/wishlist_active.svg" if self.wish_btn.isChecked() else "assets/icons/wishlist.svg"))
        self.analytics_btn.setIcon(QIcon("assets/icons/analytics_active.svg" if self.analytics_btn.isChecked() else "assets/icons/analytics.svg"))
        self.downloads_btn.setIcon(QIcon("assets/icons/downloads_active.svg" if self.downloads_btn.isChecked() else "assets/icons/downloads.svg"))
        self.settings_btn.setIcon(QIcon("assets/icons/settings_active.svg" if self.settings_btn.isChecked() else "assets/icons/settings.svg"))
        if hasattr(self, 'logo_icon'):
            self.logo_icon.setPixmap(QIcon("assets/icons/main_logo.svg").pixmap(36, 36))
        self.setWindowIcon(QIcon("assets/icons/app_icon.ico"))

        if hasattr(self, 'search_glow'):
            from ui.theme_manager import ThemeManager
            r_str, g_str, b_str = ThemeManager.THEMES[ThemeManager.get_current_theme_name()]["rgba_base"].split(",")
            from PySide6.QtGui import QColor
            self.search_glow.setColor(QColor(int(r_str), int(g_str), int(b_str), 70))
            
        # Update CSS styling for all nav buttons
        from ui.theme_manager import ThemeManager
        primary = ThemeManager.get_color("primary")
        
        nav_style = f"""
            QPushButton {{
                background-color: transparent; color: #A0AEC0; text-align: left;
                padding: 12px 16px; border-radius: 8px; font-size: 14px; font-weight: 500; border: none;
            }}
            QPushButton:hover {{
                color: #FFFFFF; background-color: #1A1C23;
            }}
            QPushButton:checked {{
                color: {primary}; background-color: rgba(255, 255, 255, 0.05); border-left: 3px solid {primary};
                border-top-left-radius: 0px; border-bottom-left-radius: 0px;
            }}
        """
        # Removed sub_nav_style to prevent buttons from looking like sub-menus

        self.discover_btn.setStyleSheet(nav_style)
        self.movies_btn.setStyleSheet(nav_style)
        self.tv_btn.setStyleSheet(nav_style)
        self.col_btn.setStyleSheet(nav_style)
        self.wish_btn.setStyleSheet(nav_style)
        self.analytics_btn.setStyleSheet(nav_style)
        self.downloads_btn.setStyleSheet(nav_style)
        self.settings_btn.setStyleSheet(nav_style)

    def switch_page(self, index, active_btn):
        old_index = self.main_stack.currentIndex()
        if hasattr(self, "search_bar"):
            self.tab_search_texts[old_index] = self.search_bar.text()

        self.main_stack.setCurrentIndex(index)
        self.discover_btn.setChecked(False)
        self.movies_btn.setChecked(False)
        self.tv_btn.setChecked(False)
        self.col_btn.setChecked(False)
        self.wish_btn.setChecked(False)
        self.analytics_btn.setChecked(False)
        self.downloads_btn.setChecked(False)
        self.settings_btn.setChecked(False)
        active_btn.setChecked(True)

        if hasattr(self, "search_bar"):
            if index == 0:
                self.search_bar.setPlaceholderText("Search for a movie, TV show, or actor...")
            elif index == 1:
                self.search_bar.setPlaceholderText("Search for a movie title...")
            elif index == 2:
                self.search_bar.setPlaceholderText("Search for a TV series title...")

        t_stack = self.tab_stacks.get(index)
        if t_stack and t_stack.currentIndex() == 0:
            if index == 3:
                self.collection_page.load_lists()
            elif index == 4:
                self.wishlist_page.load_lists()
            elif index == 5:
                self.analytics_page.load_data()


        # Restore this tab's own saved search text LAST so nothing can overwrite it
        if hasattr(self, "search_bar"):
            self.search_bar.blockSignals(True)
            self.search_bar.setText(self.tab_search_texts.get(index, ""))
            self.search_bar.blockSignals(False)

    def _on_api_key_changed(self):
        """Called when the user saves a new TMDB API Key from the settings page."""
        self.discover_page.load_discover_content()
        self.movies_page.load_home_content()
        self.tv_page.load_home_content()
        self.analytics_dirty = True

    def show_person_detail(self, person_id):
        t_stack = self.main_stack.currentWidget()
        if not isinstance(t_stack, TabStack) or not t_stack.person_page: return
        
        current_index = t_stack.currentIndex()
        state = t_stack.detail_page.movie_data if current_index == 1 else (t_stack.person_page.person_id if current_index == 3 and hasattr(t_stack.person_page, 'person_id') else None)
        t_stack.page_history.append((current_index, state))
        
        t_stack.person_page.person_id = person_id
        t_stack.person_page.load_person(person_id)
        t_stack.setCurrentIndex(3)

    def _get_current_page_state(self, t_stack):
        current_index = t_stack.currentIndex()
        if current_index == 1:
            return t_stack.detail_page.movie_data
        elif current_index == 2:
            fb = getattr(t_stack.grid_page, "filter_bar", None)
            fallback_visibility = fb.isVisible() if fb else False
            show_filter = getattr(t_stack.grid_page, "show_filter_bar", fallback_visibility)
            
            return {
                "title": getattr(t_stack.grid_page, "current_title", t_stack.grid_page.title_label.text()),
                "fetch_func": getattr(t_stack.grid_page, "fetch_func", None),
                "initial_params": getattr(t_stack.grid_page, "initial_params", getattr(t_stack.grid_page, "current_params", None)),
                "card_renderer": getattr(t_stack.grid_page, "card_renderer", None),
                "show_filter_bar": show_filter,
                "media_type": getattr(t_stack.grid_page, "_grid_media_type", getattr(t_stack.grid_page, "media_type", "movie"))
            }
        elif current_index == 3:
            return getattr(t_stack.person_page, "person_id", None)
        elif current_index == 4:
            return {
                "tv_id": getattr(t_stack.season_page, "tv_id", None),
                "tv_name": getattr(t_stack.season_page, "tv_name", ""),
                "season_number": getattr(t_stack.season_page, "season_number", None)
            }
        return None

    def show_season_detail(self, tv_id, tv_name, season_number):
        t_stack = self.main_stack.currentWidget()
        if not isinstance(t_stack, TabStack) or not t_stack.season_page: return
        
        current_index = t_stack.currentIndex()
        state = self._get_current_page_state(t_stack)
        t_stack.page_history.append((current_index, state))
        
        t_stack.season_page.load_season(tv_id, tv_name, season_number)
        t_stack.setCurrentIndex(4)

    def show_movie_detail(self, movie_data):
        t_stack = self.main_stack.currentWidget()
        if not isinstance(t_stack, TabStack) or not t_stack.detail_page: return
        
        current_index = t_stack.currentIndex()
        state = self._get_current_page_state(t_stack)
        t_stack.page_history.append((current_index, state))
        
        # Inject fresh DB status so buttons are correct from the very first render
        tmdb_api.inject_db_status([movie_data])
        t_stack.detail_page.load_movie(movie_data)
        t_stack.setCurrentIndex(1)

    def show_analytics_discovery(self, category, value):
        import tmdb_api
        params = {"sort_by": "popularity.desc"}
        title = f"Discover: {value}"
        
        if category == "Studio Loyalty":
            data = tmdb_api._make_request("/search/company", {"query": value, "page": 1})
            results = data.get("results", [])
            if results:
                params["with_companies"] = results[0]["id"]
            else:
                return # Not found
        elif category == "Cinematic World Map":
            params["with_original_language"] = value.lower()
        elif category == "Top Countries":
            params["with_origin_country"] = value
        elif category == "Rating Distribution":
            params["vote_average.gte"] = value
            params["vote_average.lte"] = str(float(value) + 0.99)
        elif category in ["Top Actors", "Top Directors", "Favorite Actors"]:
            data = tmdb_api._make_request("/search/person", {"query": value, "page": 1})
            results = data.get("results", [])
            if results:
                self.show_person_detail(results[0]["id"])
            return
        elif category == "Top Genres":
            all_genres = tmdb_api.get_genres()
            genre_id = next((g["id"] for g in all_genres if g["name"].lower() == value.lower()), None)
            if genre_id:
                params["with_genres"] = genre_id
            else:
                return
        elif category == "Time Traveler (Decades)":
            year = value.replace("s", "")
            params["primary_release_date.gte"] = f"{year}-01-01"
            params["primary_release_date.lte"] = f"{int(year)+9}-12-31"
            
        fetch_func = lambda page=1: tmdb_api.advanced_discover(params, page=page)
        self.show_grid_view(title, fetch_func, initial_params=params)

    def show_grid_view(self, title, fetch_func, initial_params=None, card_renderer=None, show_filter_bar=True, media_type="movie"):
        t_stack = self.main_stack.currentWidget()
        if not isinstance(t_stack, TabStack) or not t_stack.grid_page:
            # If triggered from somewhere without a grid (like downloads), force switch to Home
            self.switch_page(0, getattr(self, "home_btn", self.discover_btn))
            t_stack = self.tab_stacks[0]
            
        current_index = t_stack.currentIndex()
        state = self._get_current_page_state(t_stack)
        t_stack.page_history.append((current_index, state))
        
        t_stack.is_text_search = initial_params is not None and "query" in initial_params
        t_stack.grid_page.load_grid(title, fetch_func, initial_params, card_renderer, show_filter_bar, media_type)
        t_stack.setCurrentIndex(2)

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
        self.search_bar.setPlaceholderText("Search for a movie, TV show, or actor...")
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
        from ui.theme_manager import ThemeManager
        r_str, g_str, b_str = ThemeManager.THEMES[ThemeManager.get_current_theme_name()]["rgba_base"].split(",")
        self.search_glow.setColor(QColor(int(r_str), int(g_str), int(b_str), 70))
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
        from ui.theme_manager import ThemeManager
        primary = ThemeManager.get_color("primary")
        border = primary if focused else "#1E2030"
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
        t_stack = self.main_stack.currentWidget()
        if getattr(self, "settings_page", None) and t_stack == self.tab_stacks[7]:
            self.switch_page(0, self.discover_btn)
            t_stack = self.tab_stacks[0]
            
        def _do_discover_search():
            query = self.search_bar.text().strip()
            if query:
                import tmdb_api
                from ui.pages.discover_page import PersonCard
                from ui.movie_card import MovieCard
                
                def renderer(item):
                    if item.get("media_type") == "person":
                        return PersonCard(item, lambda p: self.show_person_detail(p["id"]), card_width=160, card_height=280, img_width=160, img_height=240)
                    return MovieCard(item, self.change_status, self.show_movie_detail)
                    
                self.show_grid_view(f"Search Results for '{query}'", lambda page: tmdb_api.search_multi(query, page), {"query": query}, renderer, media_type="multi")

        # Hitting Enter in the search bar acts exactly like clicking "Discover"
        if t_stack.currentIndex() == 2 and getattr(t_stack, "is_text_search", False):
            fb = getattr(t_stack.grid_page, "filter_bar", None)
            query = self.search_bar.text().strip()
            if not query:
                # Search bar was cleared — go back to the Discover home page
                self.go_back_to_previous_page()
            elif fb is not None and fb.isVisible():
                fb._apply()
            elif t_stack.tab_index == 0:
                _do_discover_search()
        elif t_stack.tab_index == 0:
            _do_discover_search()
        elif t_stack.tab_index == 1:
            self.movies_page.filter_bar._apply()
        elif t_stack.tab_index == 2:
            self.tv_page.filter_bar._apply()
        else:
            # Not on home page and not on a search grid, let's switch to discover and search
            self.switch_page(0, self.discover_btn)
            _do_discover_search()

    def go_back_to_previous_page(self):
        t_stack = self.main_stack.currentWidget()
        if not isinstance(t_stack, TabStack) or not t_stack.page_history:
            return

        prev_index, state = t_stack.page_history.pop()

        if prev_index == 0:
            if t_stack.tab_index == 3:
                self.collection_page.load_lists()
            elif t_stack.tab_index == 4:
                self.wishlist_page.load_lists()
            elif t_stack.tab_index == 5:
                self.analytics_page.load_data()

        elif prev_index == 1 and state and t_stack.detail_page:
            current_id = getattr(t_stack.detail_page, "movie_data", {}).get("id")
            if current_id != state.get("id"):
                t_stack.detail_page.load_movie(state)
                
        elif prev_index == 2 and isinstance(state, dict):
            current_title = getattr(t_stack.grid_page, "current_title", "")
            current_params = getattr(t_stack.grid_page, "initial_params", None)
            if current_title != state.get("title") or current_params != state.get("initial_params"):
                t_stack.grid_page.load_grid(
                    state.get("title", ""),
                    state.get("fetch_func"),
                    state.get("initial_params"),
                    state.get("card_renderer"),
                    state.get("show_filter_bar", True),
                    state.get("media_type", "movie")
                )
                
        elif prev_index == 3 and state and t_stack.person_page:
            current_person_id = getattr(t_stack.person_page, "person_id", None)
            if current_person_id != state:
                t_stack.person_page.person_id = state
                t_stack.person_page.load_person(state)
                
        elif prev_index == 4 and state and t_stack.season_page:
            current_tv_id = getattr(t_stack.season_page, "tv_id", None)
            current_season = getattr(t_stack.season_page, "season_number", None)
            if current_tv_id != state.get("tv_id") or current_season != state.get("season_number"):
                t_stack.season_page.load_season(state.get("tv_id"), state.get("tv_name"), state.get("season_number"))

        t_stack.setCurrentIndex(prev_index)

    def _on_tab_changed(self, index):
        self._current_main_index = index
        
        t_stack = self.main_stack.widget(index)
        if isinstance(t_stack, TabStack):
            self._update_search_visibility(t_stack)
                
            if t_stack.currentIndex() == 0:
                if index == 3 and getattr(self, "collection_dirty", False):
                    self.collection_page.load_lists()
                    self.collection_dirty = False
                elif index == 4 and getattr(self, "wishlist_dirty", False):
                    self.wishlist_page.load_lists()
                    self.wishlist_dirty = False
                elif index == 5 and getattr(self, "analytics_dirty", False):
                    self.analytics_page.load_data()
                    self.analytics_dirty = False
        else:
            if hasattr(self, "search_wrapper"):
                self.search_wrapper.setVisible(False)

    def _on_inner_page_changed(self, inner_index):
        t_stack = self.sender()
        if t_stack == self.main_stack.currentWidget():
            self._update_search_visibility(t_stack)
            
    def _update_search_visibility(self, t_stack):
        if not hasattr(self, "search_wrapper"): return
        inner_index = t_stack.currentIndex()
        if inner_index == 0 and t_stack.tab_index in (0, 1, 2):
            self.search_wrapper.setVisible(True)
        elif inner_index == 2 and getattr(t_stack, "is_text_search", False):
            fb = getattr(t_stack.grid_page, "filter_bar", None)
            if fb is not None:
                self.search_wrapper.setVisible(fb.isVisible())
            else:
                self.search_wrapper.setVisible(True)
        else:
            self.search_wrapper.setVisible(False)

    # ------------------------------------------------------------------
    # change_status — non-blocking; uses cached details when available
    # ------------------------------------------------------------------
    def change_status(self, movie_data, new_status):
        if new_status == "remove":
            database.remove_movie(movie_data["id"], movie_data.get("media_type", "movie"))
            movie_data["status"] = None
            tmdb_api.invalidate_db_cache()
            self._post_status_update(movie_data, new_status)
            return

        # Optimistic UI update so buttons feel instant
        movie_data["status"] = new_status
        for detail_page in getattr(self, 'all_detail_pages', []):
            if detail_page.movie_data and detail_page.movie_data.get("id") == movie_data["id"]:
                detail_page.update_buttons()

        # If we already have the details from any open detail page, use them directly
        cached_details = None
        for detail_page in getattr(self, 'all_detail_pages', []):
            if detail_page._last_details and detail_page._last_details.get("id") == movie_data["id"]:
                cached_details = detail_page._last_details
                break

        if cached_details:
            # Synchronous DB write (very fast, local SQLite)
            database.add_movie(
                movie_data["id"],
                movie_data.get("title") or movie_data.get("name", "Unknown"),
                movie_data.get("poster_path"),
                new_status,
                cached_details.get("series_name"),
                cached_details.get("vote_average") or movie_data.get("vote_average"),
                cached_details.get("release_date") or movie_data.get("release_date"),
                runtime=cached_details.get("runtime"),
                genres=cached_details.get("genres"),
                director=cached_details.get("director"),
                cast=cached_details.get("cast"),
                production_companies=cached_details.get("production_companies"),
                original_language=cached_details.get("original_language"),
                production_countries=cached_details.get("production_countries"),
                media_type=movie_data.get("media_type", "movie")
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
        self.collection_dirty = True
        self.wishlist_dirty = True
        self.analytics_dirty = True
        
        t_stack = self.main_stack.currentWidget()
        if isinstance(t_stack, TabStack) and t_stack.currentIndex() == 0:
            from PySide6.QtCore import QTimer
            current_idx = t_stack.tab_index
            if current_idx == 3:
                QTimer.singleShot(50, self.collection_page.load_lists)
                self.collection_dirty = False
            elif current_idx == 4:
                QTimer.singleShot(50, self.wishlist_page.load_lists)
                self.wishlist_dirty = False
            elif current_idx == 5:
                QTimer.singleShot(50, self.analytics_page.load_data)
                self.analytics_dirty = False
                
        for detail_page in getattr(self, 'all_detail_pages', []):
            if detail_page.movie_data and detail_page.movie_data.get("id") == movie_data["id"]:
                detail_page.update_buttons()
                
        for grid_page in getattr(self, 'all_grid_pages', []):
            grid_page.refresh_status()
            
        # Keep the hero banner buttons in sync no matter where the change came from
        if hasattr(self, "home_page"):
            if hasattr(self.home_page, "hero_carousel") and self.home_page.hero_carousel is not None:
                self.home_page.hero_carousel.refresh_status()
            self.home_page.refresh_carousels()
