import sys
import os

if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
import database
import ctypes
from PySide6.QtGui import QIcon


def main():
    if getattr(sys, 'frozen', False):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
    # Global AppData Setup
    import shutil
    app_data_dir = os.path.join(os.getenv('LOCALAPPDATA', os.path.expanduser('~')), 'TheStoriesICarry')
    os.makedirs(app_data_dir, exist_ok=True)
    
    # Copy assets to AppData if they don't exist
    target_assets_dir = os.path.join(app_data_dir, 'assets')
    if not os.path.exists(target_assets_dir):
        source_assets_dir = os.path.join(base_dir, 'assets')
        if os.path.exists(source_assets_dir):
            shutil.copytree(source_assets_dir, target_assets_dir)
            
    # Force copy the app icon to AppData so it can be used for the window icon
    try:
        os.makedirs(os.path.join(app_data_dir, 'assets', 'icons'), exist_ok=True)
        shutil.copy2(os.path.join(base_dir, 'assets', 'icons', 'app_icon.svg'), os.path.join(app_data_dir, 'assets', 'icons', 'app_icon.svg'))
        shutil.copy2(os.path.join(base_dir, 'assets', 'icons', 'app_icon.ico'), os.path.join(app_data_dir, 'assets', 'icons', 'app_icon.ico'))
    except Exception:
        pass
        
    # Set the working directory to AppData so databases, SVGs, and downloads_history all map there
    os.chdir(app_data_dir)
    
    # Initialize the database
    database.init_db()
    
    import ctypes
    from PySide6.QtGui import QIcon
    
    # Setting AppUserModelID globally BEFORE QApplication fixes the Windows 11 
    # taskbar click-to-minimize bug by properly syncing the process HWND group,
    # while retaining the 0ms icon load because it happens before Qt initializes.
    myappid = 'TheStoriesIHaveSeen.app.1.0'
    try:
        # Only set this manually if running from Python. 
        # Setting it in a compiled .exe detaches it from the embedded executable icon!
        if not getattr(sys, 'frozen', False):
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass
        
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("assets/icons/app_icon.ico"))
    
    # Increase maximum threads to ensure parallel image fetching & scaling without blocking
    from PySide6.QtCore import QThreadPool
    QThreadPool.globalInstance().setMaxThreadCount(30)
    
    # Pre-load themes to ensure SVGs are customized
    from ui.theme_manager import ThemeManager
    ThemeManager.load_theme()
    
    # Base global styles
    app.setStyleSheet("""
        QMainWindow { background-color: #0A0B10; }
        QWidget { font-family: 'Inter', 'Segoe UI', Arial, sans-serif; font-size: 14px; color: #FFFFFF; }
    """)
    
    # Pre-fetch static metadata in the background to ensure it's in the lru_cache
    # when the user first opens a Grid view, preventing a UI thread freeze.
    from PySide6.QtCore import QRunnable
    class PrefetchWorker(QRunnable):
        def run(self):
            import tmdb_api
            tmdb_api.get_genres(media_type="movie")
            tmdb_api.get_genres(media_type="tv")
            tmdb_api.get_languages()
            tmdb_api.get_countries()
    QThreadPool.globalInstance().start(PrefetchWorker())
            
    window = MainWindow()
    window.show()
    
    # In raw Python mode, we use a 0-millisecond timer to apply the icon on the exact first 
    # cycle of the Qt event loop. This bypasses the Windows HWND creation race condition 
    # without introducing any visible delay!
    if not getattr(sys, 'frozen', False):
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QIcon
        QTimer.singleShot(0, lambda: window.setWindowIcon(QIcon("assets/icons/app_icon.ico")))
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
