from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QHBoxLayout, QLineEdit, QLabel, QPushButton, QComboBox
from PySide6.QtCore import Qt
import tmdb_api
from ui.movie_card import MovieCard
from ui.components import HorizontalCarousel, HeroBanner

class GenreCard(QWidget):
    def __init__(self, genre):
        super().__init__()
        self.setFixedSize(160, 80)
        self.setStyleSheet("background-color: #1A1C23; border-radius: 12px;")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        lbl = QLabel(genre["name"])
        lbl.setStyleSheet("font-weight: bold; font-size: 14px; color: #E2E8F0;")
        layout.addWidget(lbl)

class HomePage(QWidget):
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
        
        self.load_home_content()
        
        scroll.setWidget(self.content_widget)
        self.layout.addWidget(scroll)
        
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
        self.on_view_all(title, lambda page: tmdb_api.advanced_discover(fetch_params, page=page), fetch_params)
            
    def load_home_content(self):
        self.clear_layout()
        
        trending = tmdb_api.get_trending()
        upcoming = tmdb_api.get_upcoming()
        top_rated = tmdb_api.get_top_rated()
        genres = tmdb_api.get_genres()
        
        if genres:
            self.load_genres(genres)
        
        if trending:
            from ui.components import HeroCarousel
            # Take top 3 trending movies for the carousel
            banner = HeroCarousel(trending[:3], lambda m: self.on_movie_click(m), self.change_status)
            self.content_layout.addWidget(banner)
            self.content_layout.addSpacing(30)
            
            from ui.components import SegmentedToggle
            self.trending_toggle = SegmentedToggle("Today", "This Week")
            
            def fetch_trending(page=1):
                window = "day" if self.trending_toggle.current == "Today" else "week"
                return tmdb_api.get_trending(page=page, time_window=window)
                
            self.trending_carousel = HorizontalCarousel(
                "Trending", 
                trending, 
                lambda m: MovieCard(m, self.change_status, self.on_movie_click), 
                lambda: self.on_view_all(f"Trending {self.trending_toggle.current}", fetch_trending),
                custom_header_widget=self.trending_toggle
            )
            
            def on_trending_toggled(opt):
                new_data = fetch_trending(1)
                self.trending_carousel.update_items(new_data)
                
            self.trending_toggle.toggled.connect(on_trending_toggled)
            self.content_layout.addWidget(self.trending_carousel)
            
        if top_rated:
            self.content_layout.addWidget(HorizontalCarousel("Top Rated", top_rated, lambda m: MovieCard(m, self.change_status, self.on_movie_click), lambda: self.on_view_all("Top Rated", tmdb_api.get_top_rated)))
            
        if upcoming:
            self.content_layout.addWidget(HorizontalCarousel("Upcoming Releases", upcoming, lambda m: MovieCard(m, self.change_status, self.on_movie_click), lambda: self.on_view_all("Upcoming Releases", tmdb_api.get_upcoming)))
            
        self.content_layout.addStretch()
