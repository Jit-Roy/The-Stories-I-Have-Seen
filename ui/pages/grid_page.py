from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QScrollArea
from PySide6.QtCore import Qt
from ui.movie_card import MovieCard
from ui.components import FlowLayout, ResizableScrollArea

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
        back_btn.setCursor(Qt.PointingHandCursor)
        from ui.theme_manager import ThemeManager
        primary = ThemeManager.get_color("primary")
        back_btn.setStyleSheet(f"""
            QPushButton {{ background-color: transparent; color: white; font-weight: bold; font-size: 28px; border: none; }}
            QPushButton:hover {{ color: {primary}; }}
        """)
        back_btn.clicked.connect(self.go_back)
        header_layout.addWidget(back_btn)
        
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: white; margin-left: 10px;")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        
        self.layout.addLayout(header_layout)
        
        # ── Filter bar slot ──────────────────────────────────────────────────────
        # We DON'T create a filter bar here. Instead, load_grid() creates a brand
        # new DiscoverFilterBar for every grid context, so there is zero shared
        # state between different grid views.
        self.filter_bar = None          # holds the current bar (or None)
        self._filter_bar_index = 1      # layout index where the bar is inserted
        
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0,0,0,0)
        
        self.flow_container = QWidget()
        self.flow_layout = FlowLayout()
        self.flow_container.setLayout(self.flow_layout)
        self.content_layout.addWidget(self.flow_container)
        
        self.load_more_btn = QPushButton("Load More")
        from ui.theme_manager import ThemeManager
        primary = ThemeManager.get_color("primary")
        primary_light = ThemeManager.lighten_hex(primary, 0.2)
        self.load_more_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {primary}; color: #0F172A; padding: 10px 30px; border-radius: 15px; font-weight: bold; font-size: 16px; margin: 20px 0px; }}
            QPushButton:hover {{ background-color: {primary_light}; }}
        """)
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
        
        from ui.theme_manager import ThemeManager
        ThemeManager.apply_theme_to_widget(self)
        
    def _replace_filter_bar(self, show_filter_bar, initial_params):
        """Destroy the old filter bar (if any) and create a fresh one for this grid context."""
        # Remove and delete the old filter bar
        if self.filter_bar is not None:
            self.layout.removeWidget(self.filter_bar)
            self.filter_bar.hide()
            self.filter_bar.deleteLater()
            self.filter_bar = None

        if not show_filter_bar:
            return

        from ui.components import DiscoverFilterBar
        import tmdb_api

        # Brand new instance — zero memory of any previous search
        bar = DiscoverFilterBar(track_global_state=False)
        bar.populate_genres(tmdb_api.get_genres())
        bar.populate_languages(tmdb_api.get_languages())
        bar.populate_countries(tmdb_api.get_countries())
        bar.set_params(initial_params if initial_params else {})
        bar.signals.filters_applied.connect(self.apply_new_filters)

        # Insert at position 1 (after the header layout)
        self.layout.insertWidget(self._filter_bar_index, bar)
        self.filter_bar = bar

    def clear_grid(self):
        self.flow_layout.clear()
                
    def load_grid(self, title, fetch_func, initial_params=None, card_renderer=None, show_filter_bar=True, media_type="movie"):
        self.current_title = title
        self.initial_params = initial_params
        self.show_filter_bar = show_filter_bar
        self._grid_media_type = media_type          # needed for rebuilding advanced_discover
        self.title_label.setText(title)
        self.clear_grid()
        self.seen_movie_ids = set()
        self.current_page = 1
        self.fetch_func = fetch_func
        self._original_fetch_func = fetch_func  # ── Save original source of truth
        self._current_show_me = None             # ── No filter initially
        self.card_renderer = card_renderer
        self.load_more_btn.show()
        
        # Create a fresh, isolated filter bar for this grid context
        self._replace_filter_bar(show_filter_bar, initial_params)
            
        self.load_next_page()
        
    def apply_new_filters(self, params):
        """
        Two modes:

        1. Discover-based grids (initial_params is set — A24, Marvel, filmography, etc.)
           Rebuild fetch_func using advanced_discover with the FULL new params so that
           date-range, genre, rating AND show_me all work correctly.

        2. Custom-fetch grids (initial_params is None — Similar Movies, Recommendations)
           The underlying API doesn't support generic discover params, so only wrap
           _original_fetch_func with a stateful show_me filter.
        """
        show_me = params.get("show_me")
        self._current_show_me = show_me

        if self.initial_params is not None:
            # ── Discover-based grid ─────────────────────────────────────────
            # advanced_discover handles all three show_me values internally
            # (via its accumulator loop for unseen/unseen_unwishlisted),
            # so we just rebuild with the full emitted params.
            import tmdb_api
            fetch_params   = params.copy()
            media_type     = self._grid_media_type
            self.fetch_func = lambda page, _fp=fetch_params, _mt=media_type: \
                tmdb_api.advanced_discover(_fp, page=page, media_type=_mt)
            # Update _original_fetch_func so subsequent filter changes also work
            self._original_fetch_func = self.fetch_func

        else:
            # ── Custom-fetch grid ────────────────────────────────────────────
            # Restore the original fetch_func, then optionally wrap with
            # a stateful show_me filter.
            self.fetch_func = self._original_fetch_func

            if show_me and show_me != "all":
                original    = self._original_fetch_func
                PAGE_SIZE   = 20
                MAX_FETCHES = 15
                state = {"api_page": 1, "buffer": [], "done": False}

                def filtered_fetch(page, _show_me=show_me, _orig=original, _s=state):
                    if page == 1:
                        _s["api_page"] = 1
                        _s["buffer"]   = []
                        _s["done"]     = False

                    fetches = 0
                    while len(_s["buffer"]) < PAGE_SIZE and not _s["done"] and fetches < MAX_FETCHES:
                        raw = _orig(_s["api_page"])
                        _s["api_page"] += 1
                        fetches += 1

                        if not raw:
                            _s["done"] = True
                            break
                        if len(raw) < PAGE_SIZE:
                            _s["done"] = True

                        if _show_me == "unseen":
                            kept = [m for m in raw if m.get("status") != "watched"]
                        elif _show_me == "unseen_unwishlisted":
                            kept = [m for m in raw if m.get("status") not in ("watched", "watch_later")]
                        else:
                            kept = raw

                        _s["buffer"].extend(kept)

                    out          = _s["buffer"][:PAGE_SIZE]
                    _s["buffer"] = _s["buffer"][PAGE_SIZE:]
                    return out

                self.fetch_func = filtered_fetch

        query = params.get("query")
        if query:
            self.current_title = f"Search Results: '{query}'"
        self.title_label.setText(self.current_title)
        self.clear_grid()
        self.seen_movie_ids = set()
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
            movie_id = movie.get("id")
            if movie_id in getattr(self, "seen_movie_ids", set()):
                continue
            if hasattr(self, "seen_movie_ids"):
                self.seen_movie_ids.add(movie_id)
                
            if getattr(self, 'card_renderer', None):
                self.flow_layout.add_widget(self.card_renderer(movie))
            else:
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
