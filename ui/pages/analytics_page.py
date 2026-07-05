from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QScrollArea, QFrame, QGridLayout, QSizePolicy, QGraphicsDropShadowEffect)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QVariantAnimation
from PySide6.QtGui import QCursor, QColor
import json
import database

class HoverAnimatedWidget(QWidget):
    clicked = Signal(str, str)
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.bg_color = QColor(255, 255, 255, 0)
        self.hover_color = QColor(255, 255, 255, 10)
        
        self.setObjectName("hoverWidget")
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(150)
        self.anim.valueChanged.connect(self._on_anim_update)
        
        self._on_anim_update(self.bg_color)
        
    def _on_anim_update(self, color):
        alpha_float = color.alpha() / 255.0
        self.setStyleSheet(f"#hoverWidget {{ background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {alpha_float:.3f}); border-radius: 8px; }}")
        
    def enterEvent(self, event):
        self.anim.stop()
        self.anim.setStartValue(self.bg_color)
        self.anim.setEndValue(self.hover_color)
        self.anim.start()
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        self.anim.stop()
        self.anim.setStartValue(self.hover_color)
        self.anim.setEndValue(self.bg_color)
        self.anim.start()
        super().leaveEvent(event)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.category, self.name)

class ClickableBarItem(HoverAnimatedWidget):
    def __init__(self, category, name, value, max_value, gradient_start, gradient_end):
        super().__init__()
        self.category = category
        self.name = name
        self.setFixedHeight(36)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(15)
        
        # Name label
        name_lbl = QLabel(name)
        name_lbl.setFixedWidth(130)
        name_lbl.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: 500; background: transparent;")
        
        # Bar container
        bar_container = QWidget()
        bar_container.setStyleSheet("background: transparent;")
        bar_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar_container_layout = QVBoxLayout(bar_container)
        bar_container_layout.setContentsMargins(0, 8, 0, 8)
        
        # The actual bar with gradient
        self.bar = QFrame()
        grad = f"qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0, stop: 0 {gradient_start}, stop: 1 {gradient_end})"
        self.bar.setStyleSheet(f"background: {grad}; border-radius: 6px;")
        
        percentage = (value / max_value) if max_value > 0 else 0
        
        bar_layout = QHBoxLayout()
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.addWidget(self.bar, int(percentage * 100))
        bar_layout.addStretch(int((1 - percentage) * 100))
        
        bar_container_layout.addLayout(bar_layout)
        
        # Value Pill
        val_lbl = QLabel(str(value))
        val_lbl.setAlignment(Qt.AlignCenter)
        val_lbl.setStyleSheet(f"""
            QLabel {{
                background-color: rgba(255, 255, 255, 0.08);
                color: {gradient_end};
                font-weight: bold;
                font-size: 12px;
                border-radius: 10px;
                padding: 2px 10px;
            }}
        """)
        
        layout.addWidget(name_lbl)
        layout.addWidget(bar_container)
        layout.addWidget(val_lbl)

class VerticalBarItem(HoverAnimatedWidget):
    def __init__(self, category, name, value, max_value, gradient_start, gradient_end):
        super().__init__()
        self.category = category
        self.name = name
        self.setFixedWidth(46)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 10, 4, 10)
        layout.setSpacing(8)
        
        # Value Pill
        val_lbl = QLabel(str(value))
        val_lbl.setAlignment(Qt.AlignCenter)
        val_lbl.setStyleSheet(f"""
            QLabel {{
                background-color: rgba(255, 255, 255, 0.08);
                color: {gradient_start};
                font-weight: bold;
                font-size: 11px;
                border-radius: 8px;
                padding: 2px 0px;
            }}
        """)
        
        bar_container = QWidget()
        bar_container.setStyleSheet("background: transparent;")
        bar_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        
        percentage = (value / max_value) if max_value > 0 else 0
        
        bar_container_layout = QVBoxLayout(bar_container)
        bar_container_layout.setContentsMargins(0, 0, 0, 0)
        bar_container_layout.addStretch(int((1 - percentage) * 100))
        
        self.bar = QFrame()
        grad = f"qlineargradient(x1: 0, y1: 1, x2: 0, y2: 0, stop: 0 {gradient_start}, stop: 1 {gradient_end})"
        self.bar.setStyleSheet(f"background: {grad}; border-radius: 6px;")
        
        # Center horizontally
        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.addStretch()
        h_layout.addWidget(self.bar, stretch=20) # fixed relative width
        h_layout.addStretch()
        
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wrapper.setLayout(h_layout)
        
        bar_container_layout.addWidget(wrapper, int(percentage * 100))
        
        name_lbl = QLabel(name)
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setStyleSheet("color: #A0AEC0; font-size: 12px; font-weight: 500; background: transparent;")
        
        layout.addWidget(val_lbl)
        layout.addWidget(bar_container)
        layout.addWidget(name_lbl)


class AnalyticsPage(QWidget):
    def __init__(self, show_grid_view):
        super().__init__()
        self.show_grid_view = show_grid_view
        self.setStyleSheet("background-color: transparent;")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header_lbl = QLabel("Analytics & Discovery")
        header_lbl.setStyleSheet("font-size: 28px; font-weight: bold; color: white; padding-bottom: 20px;")
        main_layout.addWidget(header_lbl)
        
        # Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        main_layout.addWidget(self.scroll)
        self.load_data()
        
    def load_data(self):
        if self.scroll.widget():
            self.scroll.widget().deleteLater()
            
        content = QWidget()
        content.setStyleSheet("background-color: transparent;")
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setSpacing(30)
        self.content_layout.setContentsMargins(0, 0, 20, 40)
        
        self.scroll.setWidget(content)
            
        movies = database.get_movies()
        watched = [m for m in movies if m.get("status") == "watched"]
        
        watched_movies_count = sum(1 for m in watched if m.get("media_type", "movie") == "movie")
        watched_tv_count = sum(1 for m in watched if m.get("media_type") == "tv")
        
        wishlist_movies_count = sum(1 for m in movies if m.get("status") == "watch_later" and m.get("media_type", "movie") == "movie")
        wishlist_tv_count = sum(1 for m in movies if m.get("status") == "watch_later" and m.get("media_type") == "tv")
        
        if not watched and wishlist_movies_count == 0 and wishlist_tv_count == 0:
            self._render_empty_state()
            return
            
        # 1. Main Stats "Hero" Card
        total_mins = sum((m.get("runtime") or 0) for m in watched)
        hours = total_mins // 60
        
        stats_frame = QFrame()
        stats_frame.setStyleSheet("""
            QFrame {
                background: transparent;
                border: none;
            }
        """)
        
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(40, 30, 40, 30)
        
        def create_stat_widget(title_text, val_text, color):
            w = QWidget()
            w.setStyleSheet("background: transparent; border: none;")
            l = QVBoxLayout(w)
            l.setContentsMargins(0, 0, 0, 0)
            
            t = QLabel(title_text)
            t.setStyleSheet("color: #A0AEC0; font-size: 13px; text-transform: uppercase; font-weight: 700; letter-spacing: 1px;")
            
            v = QLabel(val_text)
            v.setStyleSheet(f"color: {color}; font-size: 36px; font-weight: 800;")
            
            l.addWidget(t)
            l.addWidget(v)
            return w
            
        stats_layout.addWidget(create_stat_widget("Total Time Watched", f"{hours:,} Hours", "#1AE0A1"))
        stats_layout.addStretch()
        stats_layout.addWidget(create_stat_widget("Movies Watched", f"{watched_movies_count:,}", "#00C6FF"))
        stats_layout.addStretch()
        stats_layout.addWidget(create_stat_widget("TV Watched", f"{watched_tv_count:,}", "#8E2DE2"))
        stats_layout.addStretch()
        stats_layout.addWidget(create_stat_widget("Wishlist Movies", f"{wishlist_movies_count:,}", "#FF3366"))
        stats_layout.addStretch()
        stats_layout.addWidget(create_stat_widget("Wishlist TV", f"{wishlist_tv_count:,}", "#F5AF19"))
        
        self.content_layout.addWidget(stats_frame)
        
        # Setup Grid for Charts
        charts_layout = QGridLayout()
        charts_layout.setSpacing(25)
        self.content_layout.addLayout(charts_layout)
        
        # 2. Studio Loyalty
        studios = {}
        for m in watched:
            comps = m.get("production_companies")
            if comps:
                for c in comps:
                    studios[c] = studios.get(c, 0) + 1
                    
        self._build_horizontal_card(
            charts_layout, 0, 0, "Studio Loyalty", studios, "#FF3366", "#FF6B8B"
        )
        
        # 3. Cinematic World Map (Languages)
        languages = {}
        for m in watched:
            lang = m.get("original_language")
            if lang:
                languages[lang] = languages.get(lang, 0) + 1
                
        self._build_horizontal_card(
            charts_layout, 0, 1, "Cinematic World Map", languages, "#00C6FF", "#0072FF"
        )
        
        # 4. Top Countries
        countries = {}
        for m in watched:
            prod_countries = m.get("production_countries")
            if prod_countries:
                for c in prod_countries:
                    countries[c] = countries.get(c, 0) + 1
                    
        # Will place at bottom (Row 3, Col 0)
        
        # 5. Top Actors
        actors = {}
        for m in watched:
            cast = m.get("cast")
            if cast:
                for a in cast:
                    actors[a] = actors.get(a, 0) + 1
                    
        self._build_horizontal_card(
            charts_layout, 1, 0, "Top Actors", actors, "#FF512F", "#F09819"
        )
        
        # 6. Top Directors
        directors = {}
        for m in watched:
            d = m.get("director")
            if d and d != "Unknown":
                directors[d] = directors.get(d, 0) + 1
                
        self._build_horizontal_card(
            charts_layout, 1, 1, "Top Directors", directors, "#8E2DE2", "#4A00E0"
        )
        
        # 7. Top Genres
        genres = {}
        for m in watched:
            g_list = m.get("genres")
            if g_list:
                for g in g_list:
                    genres[g] = genres.get(g, 0) + 1
                    
        self._build_horizontal_card(
            charts_layout, 2, 0, "Top Genres", genres, "#11998E", "#38EF7D"
        )
        
        # 8. Rating Distribution
        ratings = {i: 0 for i in range(11)}
        for m in watched:
            r = m.get("vote_average")
            if r is not None:
                r_rounded = int(round(r))
                if 0 <= r_rounded <= 10:
                    ratings[r_rounded] += 1
                    
        self._build_rating_card(charts_layout, 2, 1, ratings)
        
        # Finally, place Top Countries at the bottom
        self._build_horizontal_card(
            charts_layout, 3, 0, "Top Countries", countries, "#FF0099", "#493240"
        )
        
        # 9. Release Decade Breakdown
        decades = {}
        for m in watched:
            release_date = m.get("release_date")
            if release_date and len(release_date) >= 4:
                try:
                    year = int(release_date[:4])
                    decade = year - (year % 10)
                    decade_str = f"{decade}s"
                    decades[decade_str] = decades.get(decade_str, 0) + 1
                except ValueError:
                    pass
                    
        self._build_horizontal_card(
            charts_layout, 3, 1, "Time Traveler (Decades)", decades, "#F5AF19", "#F12711"
        )

    def _build_horizontal_card(self, grid, row, col, title, data_dict, grad_start, grad_end):
        top_items = sorted(data_dict.items(), key=lambda x: x[1], reverse=True)[:10]
        card, layout = self.create_card(title)
        
        if top_items:
            max_val = top_items[0][1]
            for name, count in top_items:
                bar = ClickableBarItem(title, name, count, max_val, grad_start, grad_end)
                bar.clicked.connect(self.on_chart_clicked)
                layout.addWidget(bar)
        else:
            self._add_empty_label(layout)
            
        grid.addWidget(card, row, col)
        
    def _build_rating_card(self, grid, row, col, ratings):
        card, layout = self.create_card("Rating Distribution")
        
        h_layout = QHBoxLayout()
        h_layout.setAlignment(Qt.AlignCenter)
        
        max_rtg = max(ratings.values()) if ratings else 0
        if max_rtg > 0:
            for i in range(11):
                count = ratings[i]
                bar = VerticalBarItem("Rating Distribution", str(i), count, max_rtg, "#F2C94C", "#F2994A")
                bar.clicked.connect(self.on_chart_clicked)
                h_layout.addWidget(bar)
            layout.addLayout(h_layout)
        else:
            self._add_empty_label(layout)
            
        grid.addWidget(card, row, col)

    def _add_empty_label(self, layout):
        lbl = QLabel("Not enough data collected yet.")
        lbl.setStyleSheet("color: #4A5070; font-size: 14px; font-style: italic; background: transparent; border: none;")
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)

    def create_card(self, title_text):
        card = QFrame()
        card.setFixedHeight(480)  # Fixed height for all cards
        card.setStyleSheet("""
            QFrame {
                background: transparent;
                border: none;
            }
        """)
        
        wrapper = QVBoxLayout(card)
        wrapper.setContentsMargins(24, 24, 24, 24)
        wrapper.setSpacing(15)
        
        title = QLabel(title_text)
        title.setStyleSheet("color: #FFFFFF; font-size: 17px; font-weight: 700; background: transparent; border: none;")
        wrapper.addWidget(title)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent; 
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: #11131A;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #2A2D3E;
                min-height: 20px;
                border-radius: 3px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        content = QWidget()
        content.setStyleSheet("background: transparent; border: none;")
        scroll.setWidget(content)
        
        wrapper.addWidget(scroll)
        
        # Use content as the parent for the returned layout
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 10, 0) # Right margin for scrollbar
        layout.setAlignment(Qt.AlignTop)
        
        return card, layout

    def _render_empty_state(self):
        empty = QLabel("Your collection is empty.\nWatch some movies to generate beautiful analytics!")
        empty.setAlignment(Qt.AlignCenter)
        empty.setStyleSheet("color: #4A5070; font-size: 18px; font-weight: 500;")
        self.content_layout.addWidget(empty)
        self.content_layout.addStretch()

    def on_chart_clicked(self, category, value):
        from ui.main_window import MainWindow
        win = self.window()
        if isinstance(win, MainWindow):
            win.show_analytics_discovery(category, value)
