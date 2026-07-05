from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
import database
from ui.movie_card import MovieCard, SeriesFolderCard
from ui.components import FlowLayout, ResizableScrollArea, SegmentedToggle
from PySide6.QtCore import Qt

class WishlistPage(QWidget):
    def __init__(self, change_status_callback, on_movie_click_callback):
        super().__init__()
        self.change_status = change_status_callback
        self.on_movie_click = on_movie_click_callback
        self.current_series = None
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(10, 10, 10, 10)
        
        self.back_btn = QPushButton("← Back")
        self.back_btn.setStyleSheet("background-color: transparent; color: white; font-weight: bold; font-size: 16px; border: none;")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(lambda: self.set_series_view(None))
        self.back_btn.hide()
        
        self.title_label = QLabel("My Wishlist")
        self.title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: white; margin-left: 10px;")
        
        self.type_toggle = SegmentedToggle("Movies", "TV Series")
        self.type_toggle.toggled.connect(lambda _: self.load_lists())
        
        header_layout.addWidget(self.back_btn)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.type_toggle)
        self.layout.addLayout(header_layout)
        
        self.empty_label = QLabel("Your wishlist is empty. Add movies to watch them later!")
        self.empty_label.setStyleSheet("font-size: 16px; color: #A0AEC0; margin: 20px;")
        self.empty_label.hide()
        self.layout.addWidget(self.empty_label)
        
        self.flow = FlowLayout()
        container = QWidget()
        container.setLayout(self.flow)
        self.scroll = ResizableScrollArea(self.flow)
        self.scroll.setWidget(container)
        self.layout.addWidget(self.scroll)
        
    def set_series_view(self, series_name):
        self.current_series = series_name
        self.back_btn.setVisible(series_name is not None)
        if series_name:
            self.title_label.setText(f"Wishlist: {series_name}")
        else:
            self.title_label.setText("My Wishlist")
        self.load_lists()
        
    def load_lists(self, media_type=None):
        if media_type:
            target = "Movies" if media_type == "movie" else "TV Series"
            self.type_toggle.blockSignals(True)
            self.type_toggle.set_current(target)
            self.type_toggle.blockSignals(False)
            
        self.flow.clear()
        all_movies = database.get_movies("watch_later")
        filter_type = "movie" if self.type_toggle.current == "Movies" else "tv"
        movies = [m for m in all_movies if m.get("media_type", "movie") == filter_type]
        
        if not movies:
            media_text = "movies" if filter_type == "movie" else "TV series"
            self.empty_label.setText(f"Your wishlist is empty. Add {media_text} to watch them later!")
            self.empty_label.show()
            return
        else:
            self.empty_label.hide()
            
        series_groups = {}
        standalone = []
        
        for m in movies:
            s_name = m.get("series_name")
            if s_name:
                if s_name not in series_groups:
                    series_groups[s_name] = []
                series_groups[s_name].append(m)
            else:
                standalone.append(m)
                
        self.pending_items = []
        if self.current_series:
            for m in series_groups.get(self.current_series, []):
                self.pending_items.append(("movie", m))
        else:
            for s_name, s_movies in series_groups.items():
                self.pending_items.append(("folder", (s_name, len(s_movies), filter_type)))
            for m in standalone:
                self.pending_items.append(("movie", m))
                
        from PySide6.QtCore import QTimer
        if hasattr(self, "render_timer") and self.render_timer.isActive():
            self.render_timer.stop()
            
        self.render_timer = QTimer(self)
        self.render_timer.timeout.connect(self._render_chunk)
        self.render_timer.start(5)
        
    def _render_chunk(self):
        if not hasattr(self, "pending_items") or not self.pending_items:
            if hasattr(self, "render_timer"):
                self.render_timer.stop()
            self.flow.reflow(self.scroll.viewport().width() if self.scroll.viewport() else None)
            return
            
        chunk = self.pending_items[:15]
        self.pending_items = self.pending_items[15:]
        
        for item_type, data in chunk:
            if item_type == "movie":
                self.flow.add_widget(MovieCard(data, self.change_status, self.on_movie_click))
            elif item_type == "folder":
                self.flow.add_widget(SeriesFolderCard(data[0], data[1], self.set_series_view, data[2]))
                
        self.flow.reflow(self.scroll.viewport().width() if self.scroll.viewport() else None)

