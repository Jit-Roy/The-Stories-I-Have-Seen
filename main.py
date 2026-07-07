import sys
import os
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
    
    # ==========================================
    # OS-SPECIFIC ICON & TASKBAR INITIALIZATION
    # ==========================================
    if getattr(sys, 'frozen', False):
        # 1. COMPILED WINDOWS EXE MODE
        # No AppUserModelID is set so Windows perfectly inherits the .exe icon at 0ms.
        app = QApplication(sys.argv)
        app.setWindowIcon(QIcon("assets/icons/app_icon.ico"))
    else:
        # 2. RAW PYTHON SCRIPT MODE
        # We must override the default python.exe icon using AppUserModelID
        import ctypes
        myappid = 'JitRoy.TheStoriesIHaveSeen.app.1.0'
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass
            
        app = QApplication(sys.argv)
        app.setWindowIcon(QIcon("assets/icons/app_icon.ico"))
    # ==========================================
    
    # Pre-load themes to ensure SVGs are customized
    from ui.theme_manager import ThemeManager
    ThemeManager.load_theme()
    
    # Base global styles
    app.setStyleSheet("""
        QMainWindow { background-color: #0A0B10; }
        QWidget { font-family: 'Inter', 'Segoe UI', Arial, sans-serif; font-size: 14px; color: #FFFFFF; }
    """)
            
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
