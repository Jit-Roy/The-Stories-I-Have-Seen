from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea
from PySide6.QtCore import Qt, QRunnable, QThreadPool, Signal, QObject
import tmdb_api
from ui.movie_card import MovieCard
from ui.components import HorizontalCarousel

# ---------------------------------------------------------------------------
# Worker: fetch one home-page section off the GUI thread
# ---------------------------------------------------------------------------
class _TvSectionSignals(QObject):
    finished = Signal(str, list)   # section_key, results


class _TvSectionWorker(QRunnable):
    def __init__(self, key: str, fetch_fn):
        super().__init__()
        self.key = key
        self.fetch_fn = fetch_fn
        self.signals = _TvSectionSignals()

    def run(self):
        try:
            results = self.fetch_fn()
        except Exception as e:
            print(f"TvSectionWorker ({self.key}) error: {e}")
            results = []
        self.signals.finished.emit(self.key, results)


# ---------------------------------------------------------------------------
# TvPage
# ---------------------------------------------------------------------------
class TvPage(QWidget):
    def __init__(self, change_status_callback, on_movie_click_callback, on_view_all_callback):
        super().__init__()
        self.change_status = change_status_callback
        self.on_movie_click = on_movie_click_callback
        self.on_view_all = on_view_all_callback

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Advanced Filter Bar
        from ui.components import DiscoverFilterBar
        self.filter_bar = DiscoverFilterBar()
        self.filter_bar.signals.filters_applied.connect(self.apply_advanced_filters)
        self.layout.addWidget(self.filter_bar)

        # Main Content Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 20, 0, 0)

        scroll.setWidget(self.content_widget)
        self.layout.addWidget(scroll)

        # Placeholders so sections are inserted in a stable order
        self._section_slots: dict[str, QWidget | None] = {
            "hero": None,
            "trending": None,
            "popular": None,
            "top_rated": None,
            "upcoming": None,
        }

        self.trending_toggle = None
        self.trending_carousel = None

        self._sections_pending = 0
        self.load_home_content()

    def clear_layout(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def load_genres(self, genres):
        self.filter_bar.populate_genres(genres)

    def apply_advanced_filters(self, params):
        fetch_params = params.copy()
        query = fetch_params.get("query")
        title = f"Search Results: '{query}'" if query else "Discover Results"
        self.on_view_all(title, lambda page: tmdb_api.advanced_discover(fetch_params, page=page, media_type="tv"), fetch_params, media_type="tv")

    # ------------------------------------------------------------------
    # Async loading — launch all workers concurrently
    # ------------------------------------------------------------------
    def load_home_content(self):
        self.clear_layout()
        self._section_slots = {"hero": None, "trending": None, "popular": None, "top_rated": None, "upcoming": None}
        self.hero_carousel = None
        self.trending_toggle = None
        self.trending_carousel = None

        for key in ("hero", "trending", "popular", "top_rated", "upcoming"):
            placeholder = QWidget()
            placeholder.setVisible(False)
            self._section_slots[key] = placeholder
            self.content_layout.addWidget(placeholder)
        self.content_layout.addStretch()

        sections = [
            ("trending",  tmdb_api.get_trending_tv),
            ("popular",   tmdb_api.get_popular_tv),
            ("upcoming",  tmdb_api.get_upcoming_tv),
            ("top_rated", tmdb_api.get_top_rated_tv),
            ("genres",    tmdb_api.get_genres),
            ("languages", tmdb_api.get_languages),
            ("countries", tmdb_api.get_countries),
        ]
            
        self._sections_pending = len(sections)

        for key, fn in sections:
            worker = _TvSectionWorker(key, fn)
            worker.signals.finished.connect(self._on_section_loaded)
            from PySide6.QtCore import QThreadPool
            QThreadPool.globalInstance().start(worker)

    def _on_section_loaded(self, key: str, data: list):
        """Called on the main thread as each worker finishes."""
        self._sections_pending -= 1

        if key == "genres":
            if data:
                self.filter_bar.populate_genres(data)
            return
        elif key == "languages":
            if data:
                self.filter_bar.populate_languages(data)
            return
        elif key == "countries":
            if data:
                self.filter_bar.populate_countries(data)
            return

        if not data:
            return

        if key == "trending":
            self._build_trending(data)
        elif key == "popular":
            self._build_popular(data)
        elif key == "top_rated":
            self._build_top_rated(data)
        elif key == "upcoming":
            self._build_upcoming(data)

    # ------------------------------------------------------------------
    # Section builders — swap placeholder with real widget
    # ------------------------------------------------------------------
    def _swap_placeholder(self, key: str, real_widget: QWidget):
        placeholder = self._section_slots.get(key)
        if placeholder is None:
            return
        idx = self.content_layout.indexOf(placeholder)
        if idx == -1:
            return
        self.content_layout.removeWidget(placeholder)
        placeholder.deleteLater()
        self.content_layout.insertWidget(idx, real_widget)
        self._section_slots[key] = real_widget

    def _build_trending(self, trending):
        from ui.components import HeroCarousel, SegmentedToggle

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        self.hero_carousel = HeroCarousel(trending[:3], lambda m: self.on_movie_click(m), self.change_status)
        vbox.addWidget(self.hero_carousel)
        vbox.addSpacing(30)

        self.trending_toggle = SegmentedToggle("Today", "This Week")

        def fetch_trending(page=1):
            window = "day" if self.trending_toggle.current == "Today" else "week"
            return tmdb_api.get_trending_tv(page=page, time_window=window)

        self.trending_carousel = HorizontalCarousel(
            "Trending",
            trending,
            lambda m: MovieCard(m, self.change_status, self.on_movie_click),
            lambda: self.on_view_all(f"Trending {self.trending_toggle.current}", fetch_trending),
            custom_header_widget=self.trending_toggle,
        )

        def on_trending_toggled(opt):
            new_data = fetch_trending(1)
            self.trending_carousel.update_items(new_data)

        self.trending_toggle.toggled.connect(on_trending_toggled)
        vbox.addWidget(self.trending_carousel)

        self._swap_placeholder("hero", container)
        
    def _build_popular(self, popular):
        fetch_fn = tmdb_api.get_popular_tv
        self.popular_carousel = HorizontalCarousel(
            "Popular",
            popular,
            lambda m: MovieCard(m, self.change_status, self.on_movie_click),
            lambda: self.on_view_all("Popular", fetch_fn),
        )
        self._swap_placeholder("popular", self.popular_carousel)

    def _build_top_rated(self, top_rated):
        fetch_fn = tmdb_api.get_top_rated_tv
        self.top_rated_carousel = HorizontalCarousel(
            "Top Rated",
            top_rated,
            lambda m: MovieCard(m, self.change_status, self.on_movie_click),
            lambda: self.on_view_all("Top Rated", fetch_fn),
        )
        self._swap_placeholder("top_rated", self.top_rated_carousel)

    def _build_upcoming(self, upcoming):
        title = "On The Air"
        fetch_fn = tmdb_api.get_upcoming_tv
        self.upcoming_carousel = HorizontalCarousel(
            title,
            upcoming,
            lambda m: MovieCard(m, self.change_status, self.on_movie_click),
            lambda: self.on_view_all(title, fetch_fn),
        )
        self._swap_placeholder("upcoming", self.upcoming_carousel)

    def refresh_carousels(self):
        # Refresh the status of movie cards in all home page carousels
        for carousel_name in ["trending_carousel", "popular_carousel", "top_rated_carousel", "upcoming_carousel"]:
            if hasattr(self, carousel_name):
                carousel = getattr(self, carousel_name)
                if carousel and hasattr(carousel, "refresh_status"):
                    carousel.refresh_status()
