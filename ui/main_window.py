from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QStackedWidget
from PySide6.QtCore import Qt
import database
import tmdb_api

from ui.pages.home_page import HomePage
from ui.pages.collection_page import CollectionPage
from ui.pages.wishlist_page import WishlistPage
from ui.pages.detail_page import MovieDetailPage
from ui.pages.grid_page import GridPage

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FrameVault")
        self.setMinimumSize(1200, 800)
        self.previous_page_index = 0
        
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
        
        self.home_page = HomePage(self.change_status, self.show_movie_detail, self.show_grid_view)
        self.collection_page = CollectionPage(self.change_status, self.show_movie_detail)
        self.wishlist_page = WishlistPage(self.change_status, self.show_movie_detail)
        self.detail_page = MovieDetailPage(self.go_back_to_previous_page, self.change_status, self.show_movie_detail)
        self.grid_page = GridPage(self.go_back_to_previous_page, self.change_status, self.show_movie_detail)
        
        self.stack.addWidget(self.home_page)      # 0
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
        self.left_sidebar.setStyleSheet("background-color: #11131A; border-right: 1px solid #1E202B;")
        self.left_sidebar.setFixedWidth(240)
        layout = QVBoxLayout(self.left_sidebar)
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(20, 30, 20, 20)
        
        logo = QLabel("🎬 FrameVault\nYour Cinema Universe")
        logo.setStyleSheet("font-size: 16px; font-weight: bold; color: white; border: none;")
        layout.addWidget(logo)
        layout.addSpacing(30)
        
        nav_style = """
            QPushButton {
                background-color: transparent; color: #A0AEC0; text-align: left;
                padding: 12px 16px; border-radius: 8px; font-size: 14px; font-weight: 500; border: none;
            }
            QPushButton:hover {
                color: #FFFFFF; background-color: #1A1C23;
            }
            QPushButton:checked {
                color: #FFFFFF; background-color: #032541; border-left: 3px solid #1AE0A1;
                border-top-left-radius: 0px; border-bottom-left-radius: 0px;
            }
        """
        
        self.home_btn = QPushButton("🏠 Home")
        self.home_btn.setStyleSheet(nav_style)
        self.home_btn.setCheckable(True)
        self.home_btn.setChecked(True)
        self.home_btn.clicked.connect(lambda: self.switch_page(0, self.home_btn))
        layout.addWidget(self.home_btn)
        
        self.col_btn = QPushButton("📚 Collection")
        self.col_btn.setStyleSheet(nav_style)
        self.col_btn.setCheckable(True)
        self.col_btn.clicked.connect(lambda: self.switch_page(1, self.col_btn))
        layout.addWidget(self.col_btn)
        
        self.wish_btn = QPushButton("🔖 Wishlist")
        self.wish_btn.setStyleSheet(nav_style)
        self.wish_btn.setCheckable(True)
        self.wish_btn.clicked.connect(lambda: self.switch_page(2, self.wish_btn))
        layout.addWidget(self.wish_btn)
        
        layout.addStretch()
        self.layout.addWidget(self.left_sidebar)
        
    def switch_page(self, index, active_btn):
        self.stack.setCurrentIndex(index)
        self.previous_page_index = index
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
        self.previous_page_index = self.stack.currentIndex()
        self.detail_page.load_movie(movie_data)
        self.stack.setCurrentIndex(3)
        
    def show_grid_view(self, title, fetch_func, initial_params=None):
        self.previous_page_index = self.stack.currentIndex()
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
        # We don't want to go back to detail or grid if we are escaping it
        if self.previous_page_index in [3, 4]:
            self.previous_page_index = 0
            self.home_btn.setChecked(True)
            
        if self.previous_page_index == 0:
            import ui.components as components
            self.home_page.filter_bar.set_params(components.GLOBAL_FILTER_STATE)
            
        self.stack.setCurrentIndex(self.previous_page_index)

    def change_status(self, movie_data, new_status):
        if new_status == "remove":
            database.remove_movie(movie_data["id"])
            movie_data["status"] = None
        else:
            details = tmdb_api.get_movie_details(movie_data["id"])
            series_name = details.get("series_name") if details else None
            vote_average = details.get("vote_average") if details else movie_data.get("vote_average")
            release_date = details.get("release_date") if details else movie_data.get("release_date")
            
            database.add_movie(
                movie_data["id"], 
                movie_data["title"], 
                movie_data["poster_path"], 
                new_status,
                series_name,
                vote_average,
                release_date
            )
            # Update the dictionary so buttons reflect current state instantly
            movie_data["status"] = new_status
        
        self.collection_page.load_lists()
        self.wishlist_page.load_lists()
        if self.stack.currentIndex() == 3:
            # Refresh detail page buttons if we are on it
            self.detail_page.update_buttons()
