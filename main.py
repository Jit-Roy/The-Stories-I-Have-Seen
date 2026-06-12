import sys
import os
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
import database

def main():
    # Initialize the database
    database.init_db()
    
    import ctypes
    from PySide6.QtGui import QIcon
    
    # Set AppUserModelID so Windows taskbar correctly groups and uses the custom icon
    myappid = 'jitroy.thestoriesihaveseen.app.1.0'
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    app = QApplication(sys.argv)
    
    # Set the runtime window icon
    app.setWindowIcon(QIcon("assets/icons/main_logo.ico"))
    
    # Base global styles
    app.setStyleSheet("""
        QMainWindow { background-color: #0A0B10; }
        QWidget { font-family: 'Inter', 'Segoe UI', Arial, sans-serif; font-size: 14px; color: #FFFFFF; }
    """)
            
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
