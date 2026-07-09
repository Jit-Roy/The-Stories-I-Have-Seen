import database
from PySide6.QtWidgets import QApplication

class ThemeManager:
    THEMES = {
        "Neon Green": {"primary": "#1AE0A1", "secondary": "#14B885", "complementary": "#FF2A6C", "rgba_base": "26, 224, 161"},
        "Cyberpunk Pink": {"primary": "#FF2A6D", "secondary": "#D1225B", "complementary": "#00D2FE", "rgba_base": "255, 42, 109"},
        "Ocean Blue": {"primary": "#00D2FF", "secondary": "#009EE0", "complementary": "#FFD701", "rgba_base": "0, 210, 255"},
        "Gold": {"primary": "#FFD700", "secondary": "#E6C200", "complementary": "#B53472", "rgba_base": "255, 215, 0"},
        "Amethyst Purple": {"primary": "#B53471", "secondary": "#833471", "complementary": "#1AE0A2", "rgba_base": "181, 52, 113"}
    }
    
    DEFAULT_THEME = "Neon Green"
    _current_theme_name = DEFAULT_THEME
    
    @classmethod
    def get_current_theme_name(cls):
        return cls._current_theme_name
        
    @classmethod
    def load_theme(cls):
        theme_name = database.get_setting("theme", cls.DEFAULT_THEME)
        if theme_name not in cls.THEMES:
            theme_name = cls.DEFAULT_THEME
        cls._current_theme_name = theme_name
        cls.apply_theme_to_svgs()
        from PySide6.QtGui import QPixmapCache
        QPixmapCache.clear()
        return theme_name

    @classmethod
    def set_theme(cls, theme_name):
        if theme_name in cls.THEMES:
            cls._current_theme_name = theme_name
            database.set_setting("theme", theme_name)
            cls.apply_theme_to_app()
            
    @classmethod
    def format_style(cls, stylesheet):
        """Replaces any existing theme colors in a string with the current theme colors."""
        if "/* NOTHEME */" in stylesheet:
            return stylesheet
            
        target_theme = cls.THEMES[cls._current_theme_name]
        new_ss = stylesheet
        for name, colors in cls.THEMES.items():
            if name == cls._current_theme_name:
                continue
            new_ss = new_ss.replace(colors["primary"], target_theme["primary"])
            new_ss = new_ss.replace(colors["secondary"], target_theme["secondary"])
            
            # Use strict replace for complementary to avoid overriding primary colors if they match
            if "/* COMPLEMENTARY */" in new_ss:
                new_ss = new_ss.replace(colors["complementary"], target_theme["complementary"])
                new_ss = new_ss.replace(colors["complementary"].lower(), target_theme["complementary"].lower())

            new_ss = new_ss.replace(f"rgba({colors['rgba_base']}", f"rgba({target_theme['rgba_base']}")
            new_ss = new_ss.replace(colors["primary"].lower(), target_theme["primary"].lower())
            new_ss = new_ss.replace(colors["secondary"].lower(), target_theme["secondary"].lower())
        return new_ss
            
    @classmethod
    def apply_theme_to_widget(cls, widget):
        """Recursively apply the theme to a widget and all its children."""
        if not widget:
            return
            
        ss = widget.styleSheet()
        if ss:
            new_ss = cls.format_style(ss)
            if new_ss != ss:
                widget.setStyleSheet(new_ss)
                
        for child in widget.children():
            if hasattr(child, "styleSheet"):
                cls.apply_theme_to_widget(child)

    @classmethod
    def apply_theme_to_app(cls):
        from PySide6.QtGui import QPixmapCache
        
        # 1. Update SVGs on disk first
        cls.apply_theme_to_svgs()
        
        # 2. Clear icon cache so reloads fetch the new SVG colors
        QPixmapCache.clear()
        
        app = QApplication.instance()
        if app:
            for widget in app.topLevelWidgets():
                cls.apply_theme_to_widget(widget)
                # Force refresh of icons on MainWindow
                if hasattr(widget, "update_nav_icons"):
                    widget.update_nav_icons()

    @classmethod
    def apply_theme_to_svgs(cls):
        import os
        import sys
        base_dir = os.getcwd()
            
        icons_dir = os.path.join(base_dir, "assets", "icons")
        if not os.path.exists(icons_dir):
            return
            
        target_theme = cls.THEMES[cls._current_theme_name]
        
        for filename in os.listdir(icons_dir):
            if filename.endswith(".svg"):
                filepath = os.path.join(icons_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                    new_content = content
                    for name, colors in cls.THEMES.items():
                        if name == cls._current_theme_name:
                            continue
                        new_content = new_content.replace(colors["primary"], target_theme["primary"])
                        new_content = new_content.replace(colors["primary"].lower(), target_theme["primary"].lower())
                        new_content = new_content.replace(colors["secondary"], target_theme["secondary"])
                        new_content = new_content.replace(colors["secondary"].lower(), target_theme["secondary"].lower())
                        new_content = new_content.replace(colors["complementary"], target_theme["complementary"])
                        new_content = new_content.replace(colors["complementary"].lower(), target_theme["complementary"].lower())
                        
                    if new_content != content:
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(new_content)
                except Exception as e:
                    print(f"Error updating SVG {filename}: {e}")

    @classmethod
    def get_color(cls, key="primary"):
        return cls.THEMES.get(cls._current_theme_name, cls.THEMES[cls.DEFAULT_THEME])[key]

    @classmethod
    def lighten_hex(cls, hex_color, factor=0.2):
        """Lightens a hex color (e.g. '#FF0000') by the given factor (0.0 to 1.0)."""
        if not hex_color.startswith('#'):
            return hex_color
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))
        return f"#{r:02X}{g:02X}{b:02X}"
