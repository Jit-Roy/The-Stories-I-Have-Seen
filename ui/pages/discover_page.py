from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel, QPushButton
from PySide6.QtCore import Qt, QRunnable, QThreadPool, Signal, QObject
from PySide6.QtGui import QCursor
import tmdb_api
from ui.movie_card import MovieCard
from ui.components import HorizontalCarousel

POPULAR_STUDIOS = [
    {"id": 41077, "title": "A24", "logo_path": "https://image.tmdb.org/t/p/w500/1ZXsGaFPgrgS6ZZGS37AqD5uU12.png", "media_type": "category", "type": "studio"},
    {"id": 3, "title": "Pixar", "logo_path": "https://image.tmdb.org/t/p/w500/1TjvGVDMYsj6JBxOAkUHpPEwLf7.png", "media_type": "category", "type": "studio"},
    {"id": 10342, "title": "Studio Ghibli", "logo_path": "https://image.tmdb.org/t/p/w500/uFuxPEZRUcBTEiYIxjHJq62Vr77.png", "media_type": "category", "type": "studio"},
    {"id": 420, "title": "Marvel Studios", "logo_path": "https://image.tmdb.org/t/p/w500/hUzeosd33nzE5MCNsZxCGEKTXaQ.png", "media_type": "category", "type": "studio"},
    {"id": 508, "title": "Regency Enterprises", "logo_path": "https://image.tmdb.org/t/p/w500/4sGWXoboEkWPphI6es6rTmqkCBh.png", "media_type": "category", "type": "studio"},
    {"id": 33, "title": "Universal Pictures", "logo_path": "https://image.tmdb.org/t/p/w500/8lvHyhjr8oUKOOy2dKXoALWKdp0.png", "media_type": "category", "type": "studio"},
    {"id": 174, "title": "Warner Bros. Pictures", "logo_path": "https://image.tmdb.org/t/p/w500/zhD3hhtKB5qyv7ZeL4uLpNxgMVU.png", "media_type": "category", "type": "studio"},
    {"id": 4, "title": "Paramount", "logo_path": "https://image.tmdb.org/t/p/w500/jay6WcMgagAklUt7i9Euwj1pzTF.png", "media_type": "category", "type": "studio"},
    {"id": 127928, "title": "20th Century Studios", "logo_path": "https://image.tmdb.org/t/p/w500/h0rjX5vjW5r8yEnUBStFarjcLT4.png", "media_type": "category", "type": "studio"},
    {"id": 2, "title": "Walt Disney Pictures", "logo_path": "https://image.tmdb.org/t/p/w500/wdrCwmRnLFJhEoH8GSfymY85KHT.png", "media_type": "category", "type": "studio"},
    {"id": 5, "title": "Columbia Pictures", "logo_path": "https://image.tmdb.org/t/p/w500/71BqEFAF4V3qjjMPCpLuyJFB9A.png", "media_type": "category", "type": "studio"},
    {"id": 12, "title": "New Line Cinema", "logo_path": "https://image.tmdb.org/t/p/w500/2ycs64eqV5rqKYHyQK0GVoKGvfX.png", "media_type": "category", "type": "studio"},
    {"id": 521, "title": "DreamWorks Animation", "logo_path": "https://image.tmdb.org/t/p/w500/3BPX5VGBov8SDqTV7wC1L1xShAS.png", "media_type": "category", "type": "studio"},
    {"id": 1632, "title": "Lionsgate", "logo_path": "https://image.tmdb.org/t/p/w500/cisLn1YAUuptXVBa0xjq7ST9cH0.png", "media_type": "category", "type": "studio"},
    {"id": 54629, "title": "Legendary Entertainment", "logo_path": "https://image.tmdb.org/t/p/w500/nygX645auQxOiiAH1mrPxIuQRj0.png", "media_type": "category", "type": "studio"},
    {"id": 3172, "title": "Blumhouse Productions", "logo_path": "https://image.tmdb.org/t/p/w500/rzKluDcRkIwHZK2pHsiT667A2Kw.png", "media_type": "category", "type": "studio"},
    {"id": 1, "title": "Lucasfilm", "logo_path": "https://image.tmdb.org/t/p/w500/tlVSws0RvvtPBwViUyOFAO0vcQS.png", "media_type": "category", "type": "studio"},
    {"id": 6704, "title": "Illumination", "logo_path": "https://image.tmdb.org/t/p/w500/fOG2oY4m1YuYTQh4bMqqZkmgOAI.png", "media_type": "category", "type": "studio"},
    {"id": 2251, "title": "Sony Pictures Animation", "logo_path": "https://image.tmdb.org/t/p/w500/5ilV5mH3gxTEU7p5wjxptHvXkyr.png", "media_type": "category", "type": "studio"},
    {"id": 21, "title": "Metro-Goldwyn-Mayer", "logo_path": "https://image.tmdb.org/t/p/w500/usUnaYV6hQnlVAXP6r4HwrlLFPG.png", "media_type": "category", "type": "studio"},
    {"id": 10146, "title": "Focus Features", "logo_path": "https://image.tmdb.org/t/p/w500/xnFIOeq5cKw09kCWqV7foWDe4AA.png", "media_type": "category", "type": "studio"},
    {"id": 14, "title": "Miramax", "logo_path": "https://image.tmdb.org/t/p/w500/m6AHu84oZQxvq7n1rsvMNJIAsMu.png", "media_type": "category", "type": "studio"},
    {"id": 127929, "title": "Searchlight Pictures", "logo_path": "https://image.tmdb.org/t/p/w500/7DLKyL15ETI9645XSr9JcbMV79c.png", "media_type": "category", "type": "studio"},
    {"id": 56, "title": "Amblin Entertainment", "logo_path": "https://image.tmdb.org/t/p/w500/cEaxANEisCqeEoRvODv2dO1I0iI.png", "media_type": "category", "type": "studio"}
]

POPULAR_KEYWORDS = [
    {"id": 310, "title": "Cyberpunk", "poster_path": "https://image.tmdb.org/t/p/w500/gajva2L0rPYkEWjzgFlBXCAVBE5.jpg", "media_type": "category", "type": "keyword"},
    {"id": 4379, "title": "Time Travel", "poster_path": "https://image.tmdb.org/t/p/w500/vN5B5WgYscRGcQpVhHl6p9DDTP0.jpg", "media_type": "category", "type": "keyword"},
    {"id": 161176, "title": "Space Opera", "poster_path": "https://image.tmdb.org/t/p/w500/6FfCtAuVAW8XJjZ7eWeLibRLWTw.jpg", "media_type": "category", "type": "keyword"},
    {"id": 10683, "title": "Coming of Age", "poster_path": "https://image.tmdb.org/t/p/w500/gl66K7zRdtNYGrxyS2YDUP5ASZd.jpg", "media_type": "category", "type": "keyword"},
    {"id": 9715, "title": "Superhero", "poster_path": "https://image.tmdb.org/t/p/w500/kjdJntyBeEvqm9w97QGBdxPptzj.jpg", "media_type": "category", "type": "keyword"},
    {"id": 359337, "title": "Post-Apocalyptic", "poster_path": "https://image.tmdb.org/t/p/w500/hA2ple9q4qnwxp3hKVNhroipsir.jpg", "media_type": "category", "type": "keyword"},
    {"id": 10714, "title": "Serial Killer", "poster_path": "https://image.tmdb.org/t/p/w500/191nKfP0ehp3uIvWqgPbFmI4lv9.jpg", "media_type": "category", "type": "keyword"},
    {"id": 779, "title": "Martial Arts", "poster_path": "https://image.tmdb.org/t/p/w500/m3Low6jJrKXHSYFpXNkmYsG1Q6I.jpg", "media_type": "category", "type": "keyword"},
    {"id": 12377, "title": "Zombies", "poster_path": "https://image.tmdb.org/t/p/w500/vNVFt6dtcqnI7hqa6LFBUibuFiw.jpg", "media_type": "category", "type": "keyword"},
    {"id": 3133, "title": "Vampires", "poster_path": "https://image.tmdb.org/t/p/w500/2162lAT2MP36MyJd2sttmj5du5T.jpg", "media_type": "category", "type": "keyword"},
]

class CategoryCard(QWidget):
    _color_index = 0
    
    def __init__(self, data, on_click):
        super().__init__()
        self.data = data
        self.on_click = on_click
        self.setFixedSize(160, 240)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        
        from ui.movie_card import RoundedImage, ImageLoader
        self.img = RoundedImage()
        self.img.setFixedSize(160, 240)
        
        colors = ["#FF5A5F", "#087E8B", "#3C3B3D", "#F5D491", "#C43302"]
        c = colors[CategoryCard._color_index % len(colors)]
        CategoryCard._color_index += 1
        
        self.img.setStyleSheet(f"background-color: {c}; border-radius: 12px;")
        
        if data.get("poster_path"):
            url = data["poster_path"]
            cached = ImageLoader.get_cached_image(url)
            if cached:
                self._apply_image(cached)
            else:
                loader = ImageLoader(url)
                loader.signals.finished.connect(self._apply_image)
                QThreadPool.globalInstance().start(loader)
        elif data.get("logo_path"):
            url = data["logo_path"]
            cached = ImageLoader.get_cached_image(url)
            if cached:
                self._apply_logo(cached)
            else:
                loader = ImageLoader(url)
                loader.signals.finished.connect(self._apply_logo)
                QThreadPool.globalInstance().start(loader)
                
        # Overlay gradient for text readability
        self.overlay = QWidget(self.img)
        self.overlay.setFixedSize(160, 240)
        self.overlay.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(0,0,0,0), stop:0.5 rgba(0,0,0,0.3), stop:1 rgba(0,0,0,0.8));
                border-radius: 12px;
            }
        """)
        
        # Add Title text inside overlay
        lbl = QLabel(data["title"], self.overlay)
        lbl.setStyleSheet("color: white; font-weight: bold; font-size: 16px; background: transparent;")
        lbl.setAlignment(Qt.AlignBottom | Qt.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setGeometry(10, 10, 140, 210) # X, Y, Width, Height

        # Hover highlight overlay (hidden by default)
        self.hover_overlay = QWidget(self.img)
        self.hover_overlay.setFixedSize(160, 240)
        self.hover_overlay.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(0,0,0,0.6), stop:0.25 rgba(0,0,0,0), stop:0.75 rgba(0,0,0,0), stop:1 rgba(0,0,0,0.6));
                border-radius: 12px;
            }
        """)
        self.hover_overlay.hide()
        self.hover_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hover_overlay.raise_()

        layout.addWidget(self.img)

    def _apply_image(self, image_data):
        if not image_data: return
        from PySide6.QtGui import QImage, QPixmap
        img = QImage()
        if img.loadFromData(image_data):
            dpr = self.devicePixelRatioF()
            pixmap = QPixmap(img).scaled(int(160 * dpr), int(240 * dpr), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            pixmap.setDevicePixelRatio(dpr)
            self.img.setPixmap(pixmap)
            
    def _apply_logo(self, image_data):
        if not image_data: return
        from PySide6.QtGui import QImage, QPixmap, QPainter
        img = QImage()
        if img.loadFromData(image_data):
            dpr = self.devicePixelRatioF()
            # Scale logo down to fit inside a 120x120 box
            logo_pix = QPixmap(img).scaled(int(120 * dpr), int(120 * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_pix.setDevicePixelRatio(dpr)
            
            # Create a 160x240 transparent image
            final_img = QImage(int(160 * dpr), int(240 * dpr), QImage.Format_ARGB32_Premultiplied)
            final_img.setDevicePixelRatio(dpr)
            final_img.fill(Qt.transparent)
            
            p = QPainter(final_img)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            
            # Center the logo in the 160x240 space
            x = int((160 - logo_pix.width() / dpr) / 2)
            # Offset y slightly up so it's not covered by the text at the bottom
            y = int((240 - logo_pix.height() / dpr) / 2) - 20
            p.drawPixmap(x, y, logo_pix)
            p.end()
            
            self.img.setPixmap(QPixmap(final_img))

    def enterEvent(self, event):
        self.hover_overlay.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover_overlay.hide()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.on_click(self.data)


class PersonCard(QWidget):
    def __init__(self, data, on_click, card_width=120, card_height=230, img_width=120, img_height=180):
        super().__init__()
        self.data = data
        self.on_click = on_click
        self.img_width = img_width
        self.img_height = img_height
        self.setFixedSize(card_width, card_height)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setAlignment(Qt.AlignCenter)
        
        from ui.movie_card import RoundedImage, ImageLoader
        self.img = RoundedImage()
        self.img.setFixedSize(img_width, img_height)
        self.img.setStyleSheet("background-color: #1A1C23; border-radius: 8px;") 
        if data.get("profile_path"):
            url = data["profile_path"]
            cached = ImageLoader.get_cached_image(url)
            if cached:
                self._apply_image(cached)
            else:
                loader = ImageLoader(url)
                loader.signals.finished.connect(self._apply_image)
                QThreadPool.globalInstance().start(loader)

        # Hover highlight overlay on the photo (hidden by default)
        self.hover_overlay = QWidget(self.img)
        self.hover_overlay.setFixedSize(img_width, img_height)
        self.hover_overlay.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(0,0,0,0.6), stop:0.25 rgba(0,0,0,0), stop:0.75 rgba(0,0,0,0), stop:1 rgba(0,0,0,0.6));
                border-radius: 8px;
            }
        """)
        self.hover_overlay.hide()
        self.hover_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
            
        name = QLabel(data["name"])
        name.setStyleSheet("color: white; font-weight: bold; font-size: 12px;")
        name.setWordWrap(True)
        name.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(self.img)
        layout.addWidget(name)
        layout.addStretch()

    def _apply_image(self, image_data):
        if not image_data: return
        from PySide6.QtGui import QImage, QPixmap
        img = QImage()
        if img.loadFromData(image_data):
            dpr = self.devicePixelRatioF()
            pixmap = QPixmap(img).scaled(int(self.img_width * dpr), int(self.img_height * dpr), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            pixmap.setDevicePixelRatio(dpr)
            self.img.setPixmap(pixmap)

    def enterEvent(self, event):
        self.hover_overlay.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover_overlay.hide()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.on_click(self.data)


class _DiscoverSectionSignals(QObject):
    finished = Signal(str, list)

class _DiscoverSectionWorker(QRunnable):
    def __init__(self, key: str, fetch_fn):
        super().__init__()
        self.key = key
        self.fetch_fn = fetch_fn
        self.signals = _DiscoverSectionSignals()

    def run(self):
        try:
            results = self.fetch_fn()
        except Exception as e:
            print(f"DiscoverSectionWorker ({self.key}) error: {e}")
            results = []
        self.signals.finished.emit(self.key, results)


class DiscoverPage(QWidget):
    def __init__(self, change_status_callback, on_movie_click_callback, on_person_click_callback, on_view_all_callback):
        super().__init__()
        self.change_status = change_status_callback
        self.on_movie_click = on_movie_click_callback
        self.on_person_click = on_person_click_callback
        self.on_view_all = on_view_all_callback

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

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

        self.load_discover_content()

    def clear_layout(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def on_category_clicked(self, category):
        # We trigger a grid view using on_view_all
        title = category["title"]
        cat_type = category["type"]
        cat_id = category["id"]
        
        if cat_type == "studio":
            params = {"with_companies": str(cat_id), "sort_by": "popularity.desc"}
            fetch_fn = lambda page: tmdb_api.advanced_discover(params, page=page, media_type="movie")
            self.on_view_all(f"{title} Movies", fetch_fn, params)
        elif cat_type == "keyword":
            params = {"with_keywords": str(cat_id), "sort_by": "popularity.desc"}
            fetch_fn = lambda page: tmdb_api.advanced_discover(params, page=page, media_type="movie")
            self.on_view_all(f"'{title}' Movies", fetch_fn, params)

    def _build_hardcoded_carousel(self, title, data, renderer):
        from ui.components import HorizontalCarousel
        def fetch_all(page=1):
            return data if page == 1 else []
            
        car = HorizontalCarousel(
            title,
            data[:10],
            renderer,
            lambda: self.on_view_all(title, fetch_all, None, renderer)
        )
        return car

    def load_discover_content(self):
        self.clear_layout()
        
        # 1. Studios
        studios_car = self._build_hardcoded_carousel("Iconic Studios", POPULAR_STUDIOS, lambda d: CategoryCard(d, self.on_category_clicked))
        self.content_layout.addWidget(studios_car)
        
        # 2. Keywords
        keywords_car = self._build_hardcoded_carousel("Trending Themes", POPULAR_KEYWORDS, lambda d: CategoryCard(d, self.on_category_clicked))
        self.content_layout.addWidget(keywords_car)

        # 3. Trending People Placeholder
        self.people_placeholder = QWidget()
        self.content_layout.addWidget(self.people_placeholder)
        
        self.content_layout.addStretch()

        # Fetch trending people
        worker = _DiscoverSectionWorker("people", tmdb_api.get_trending_people)
        worker.signals.finished.connect(self._on_people_loaded)
        QThreadPool.globalInstance().start(worker)

    def _on_people_loaded(self, key, data):
        if not data:
            return
            
        from ui.components import HorizontalCarousel
        import tmdb_api
        
        renderer = lambda d: PersonCard(d, lambda p: self.on_person_click(p["id"]))
        
        people_car = HorizontalCarousel(
            "Trending People",
            data[:10],
            renderer,
            lambda: self.on_view_all("Trending People", tmdb_api.get_trending_people, None, renderer)
        )
            
        idx = self.content_layout.indexOf(self.people_placeholder)
        if idx != -1:
            self.content_layout.removeWidget(self.people_placeholder)
            self.people_placeholder.deleteLater()
            self.content_layout.insertWidget(idx, people_car)

    def refresh_carousels(self):
        # Category cards don't have status, but if we add anything, we can refresh it here
        pass
