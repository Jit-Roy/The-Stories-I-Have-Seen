from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
import database
from ui.movie_card import MovieCard, SeriesFolderCard
from ui.components import FlowLayout, ResizableScrollArea
from PySide6.QtCore import Qt

class CollectionPage(QWidget):
    def __init__(self, change_status_callback, on_movie_click_callback):
        super().__init__()
        self.change_status = change_status_callback
        self.on_movie_click = on_movie_click_callback
        self.current_series = None
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(10, 10, 10, 10)
        
        self.back_btn = QPushButton("←")
        self.back_btn.setFixedSize(40, 40)
        self.back_btn.setStyleSheet("background-color: transparent; color: white; font-weight: bold; font-size: 28px; border: none;")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(lambda: self.set_series_view(None))
        self.back_btn.hide()
        
        self.title_label = QLabel("My Collection")
        self.title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: white; margin-left: 10px;")
        
        header_layout.addWidget(self.back_btn)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        self.layout.addLayout(header_layout)
        
        self.empty_label = QLabel("Your collection is empty. Discover movies and mark them as watched!")
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
            self.title_label.setText(f"Collection: {series_name}")
        else:
            self.title_label.setText("My Collection")
        self.load_lists()
        
    def load_lists(self):
        self.flow.clear()
        movies = database.get_movies("watched")
        
        if not movies:
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
                
        if self.current_series:
            for m in series_groups.get(self.current_series, []):
                self.flow.add_widget(MovieCard(m, self.change_status, self.on_movie_click))
        else:
            for s_name, s_movies in series_groups.items():
                folder = SeriesFolderCard(s_name, len(s_movies), self.set_series_view)
                self.flow.add_widget(folder)
            for m in standalone:
                self.flow.add_widget(MovieCard(m, self.change_status, self.on_movie_click))
                
        self.flow.reflow(self.scroll.viewport().width() if self.scroll.viewport() else None)

