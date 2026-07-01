from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QScrollArea
from PySide6.QtCore import Qt
from ui.movie_card import MovieCard
from ui.components import FlowLayout, ResizableScrollArea, DiscoverFilterBar

class GridPage(QWidget):
    def __init__(self, go_back_callback, change_status_callback, on_click_callback):
        super().__init__()
        self.go_back = go_back_callback
        self.change_status = change_status_callback
        self.on_click = on_click_callback
        
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
        
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: white; margin-left: 10px;")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        
        self.layout.addLayout(header_layout)
        
        self.filter_bar = DiscoverFilterBar()
        self.filter_bar.hide()
        self.filter_bar.signals.filters_applied.connect(self.apply_new_filters)
        self.layout.addWidget(self.filter_bar)
        
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0,0,0,0)
        
        self.flow_container = QWidget()
        self.flow_layout = FlowLayout()
        self.flow_container.setLayout(self.flow_layout)
        self.content_layout.addWidget(self.flow_container)
        
        self.load_more_btn = QPushButton("Load More")
        self.load_more_btn.setStyleSheet("background-color: #1AE0A1; color: #0F172A; padding: 10px 30px; border-radius: 15px; font-weight: bold; font-size: 16px; margin: 20px 0px;")
        self.load_more_btn.setCursor(Qt.PointingHandCursor)
        self.load_more_btn.clicked.connect(self.load_next_page)
        self.load_more_btn.hide()
        self.content_layout.addWidget(self.load_more_btn, 0, Qt.AlignCenter)
        self.content_layout.addStretch()
        
        self.scroll = ResizableScrollArea(self.flow_layout)
        self.scroll.setWidget(self.content_widget)
        self.layout.addWidget(self.scroll)
        
        self.current_page = 1
        self.fetch_func = None
        
    def clear_grid(self):
        self.flow_layout.clear()
                
    def load_grid(self, title, fetch_func, initial_params=None):
        self.title_label.setText(title)
        self.clear_grid()
        self.current_page = 1
        self.fetch_func = fetch_func
        self.load_more_btn.show()
        
        if initial_params is not None:
            import tmdb_api
            self.filter_bar.populate_genres(tmdb_api.get_genres())
            self.filter_bar.populate_languages(tmdb_api.get_languages())
            self.filter_bar.populate_countries(tmdb_api.get_countries())
            self.filter_bar.set_params(initial_params)
            self.filter_bar.show()
        else:
            self.filter_bar.hide()
            
        self.load_next_page()
        
    def apply_new_filters(self, params):
        import tmdb_api
        fetch_params = params.copy()
        self.fetch_func = lambda page: tmdb_api.advanced_discover(fetch_params, page=page)
        
        query = fetch_params.get("query")
        if query:
            self.title_label.setText(f"Search Results: '{query}'")
        else:
            self.title_label.setText("Discover Results")
            
        self.clear_grid()
        self.current_page = 1
        self.load_more_btn.show()
        self.load_next_page()
        
    def load_next_page(self):
        if not self.fetch_func: return
        movies = self.fetch_func(self.current_page)
        if not movies:
            self.load_more_btn.hide()
            return
            
        for movie in movies:
            self.flow_layout.add_widget(MovieCard(movie, self.change_status, self.on_click))
            
        self.current_page += 1
        self.flow_layout.reflow(self.scroll.viewport().width())
        
        if len(movies) < 20:
            self.load_more_btn.hide()

    def refresh_status(self):
        # Update UI of all MovieCards in the grid to reflect fresh DB status
        import tmdb_api
        from ui.movie_card import MovieCard
        
        # We need to fetch the latest db status
        db_cache = tmdb_api._get_db_status_map()
        
        # Iterate over widgets in flow_layout
        for i in range(self.flow_layout.count()):
            item = self.flow_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, MovieCard):
                    # Inject the latest status
                    movie_id = widget.movie_data.get("id")
                    widget.movie_data["status"] = db_cache.get(movie_id)
                    widget.update_buttons()
