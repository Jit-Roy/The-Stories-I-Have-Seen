from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, 
                               QLineEdit, QPushButton, QHBoxLayout, 
                               QSpacerItem, QSizePolicy, QFrame, QFileDialog)
from PySide6.QtCore import Qt, QTimer, Signal
import tmdb_api
from ui.theme_manager import ThemeManager
from download_manager import DownloadManager
import database
import os

class SettingsPage(QWidget):
    api_key_changed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        primary = ThemeManager.get_color("primary")
        primary_hover = ThemeManager.get_color("primary_hover")

        self.setStyleSheet(f"""
            QWidget#settingsPage {{
                background-color: #0B0D14;
            }}
            QLabel {{
                color: #FFFFFF;
                font-family: 'Segoe UI', Arial, sans-serif;
            }}
            QLineEdit {{
                background-color: #1A1C23;
                border: 1px solid #2D3243;
                border-radius: 8px;
                padding: 12px;
                color: #FFFFFF;
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border: 1px solid {primary};
            }}
            QLineEdit[readOnly="true"] {{
                background-color: transparent;
                border: 1px solid transparent;
                color: #A0AEC0;
            }}
            QPushButton {{
                font-weight: bold;
                font-size: 14px;
                border-radius: 8px;
                padding: 10px 20px;
                border: none;
            }}
            QPushButton#saveBtn {{
                background-color: {primary};
                color: #0B0D14;
            }}
            QPushButton#saveBtn:hover {{
                font-size: 15px;
                background-color: {primary_hover};
            }}
            QPushButton#editBtn {{
                background-color: rgba(255, 255, 255, 0.05);
                color: #FFFFFF;
                border: 1px solid #2D3243;
            }}
            QPushButton#editBtn:hover {{
                background-color: rgba(255, 255, 255, 0.1);
            }}
            QPushButton#cancelBtn {{
                background-color: transparent;
                color: #A0AEC0;
            }}
            QPushButton#cancelBtn:hover {{
                color: #FFFFFF;
                background-color: rgba(255, 255, 255, 0.05);
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        # Title
        title_label = QLabel("Settings")
        title_label.setStyleSheet("font-size: 28px; font-weight: bold; margin-bottom: 20px;")
        layout.addWidget(title_label)

        # Card container for API Key
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(16)

        section_title = QLabel("TMDB API Configuration")
        section_title.setStyleSheet(f"font-size: 18px; font-weight: 600; color: {primary};")
        card_layout.addWidget(section_title)

        desc = QLabel("Enter your TMDB API Key below. This is required for fetching movie details, posters, and search results.")
        desc.setStyleSheet("color: #A0AEC0; font-size: 13px;")
        desc.setWordWrap(True)
        card_layout.addWidget(desc)

        self.api_input = QLineEdit()
        self.api_input.setPlaceholderText("Enter TMDB API Key...")
        
        # Initial State: Read-only and masked
        self.api_input.setReadOnly(True)
        self.api_input.setEchoMode(QLineEdit.Password)
        
        # Pre-fill with current key
        self.current_key = tmdb_api.get_api_key() or ""
        self.api_input.setText(self.current_key)
            
        card_layout.addWidget(self.api_input)

        # Buttons
        btn_layout = QHBoxLayout()
        
        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setObjectName("editBtn")
        self.edit_btn.setCursor(Qt.PointingHandCursor)
        self.edit_btn.clicked.connect(self._on_edit_clicked)
        
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("saveBtn")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self._on_save_clicked)
        self.save_btn.hide()
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        self.cancel_btn.hide()
        
        self.status_msg = QLabel("")
        self.status_msg.setStyleSheet(f"color: {primary}; font-weight: 500;")
        self.status_msg.hide()

        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.status_msg)
        btn_layout.addStretch()

        card_layout.addLayout(btn_layout)
        layout.addWidget(card)
        
        # Download Directory Card
        dl_card = QFrame()
        dl_card.setStyleSheet("QFrame { background-color: transparent; border: none; }")
        dl_card_layout = QVBoxLayout(dl_card)
        dl_card_layout.setContentsMargins(24, 24, 24, 24)
        dl_card_layout.setSpacing(16)
        
        dl_title = QLabel("Download Directory")
        dl_title.setStyleSheet(f"font-size: 18px; font-weight: 600; color: {primary};")
        dl_card_layout.addWidget(dl_title)
        
        dl_desc = QLabel("Select the target folder where your movies and TV series downloads should be saved.")
        dl_desc.setStyleSheet("color: #A0AEC0; font-size: 13px;")
        dl_desc.setWordWrap(True)
        dl_card_layout.addWidget(dl_desc)
        
        dl_input_layout = QHBoxLayout()
        self.dl_input = QLineEdit()
        self.dl_input.setReadOnly(True)
        self.dl_input.setText(DownloadManager().download_path)
        
        self.dl_browse_btn = QPushButton("Browse")
        self.dl_browse_btn.setObjectName("editBtn")
        self.dl_browse_btn.setCursor(Qt.PointingHandCursor)
        self.dl_browse_btn.clicked.connect(self._on_browse_clicked)
        
        dl_input_layout.addWidget(self.dl_input)
        dl_input_layout.addWidget(self.dl_browse_btn)
        
        dl_card_layout.addLayout(dl_input_layout)
        layout.addWidget(dl_card)
        
        # Appearance Card
        appearance_card = QFrame()
        appearance_card.setStyleSheet("QFrame { background-color: transparent; border: none; }")
        app_card_layout = QVBoxLayout(appearance_card)
        app_card_layout.setContentsMargins(24, 24, 24, 24)
        app_card_layout.setSpacing(16)
        
        app_title = QLabel("Appearance")
        app_title.setStyleSheet(f"font-size: 18px; font-weight: 600; color: {primary};")
        app_card_layout.addWidget(app_title)
        
        app_desc = QLabel("Select your preferred accent color theme. Changes are applied instantly across the entire application.")
        app_desc.setStyleSheet("color: #A0AEC0; font-size: 13px;")
        app_desc.setWordWrap(True)
        app_card_layout.addWidget(app_desc)
        
        themes_layout = QHBoxLayout()
        themes_layout.setSpacing(15)
        
        self.theme_btns = {}
        for theme_name, colors in ThemeManager.THEMES.items():
            btn = QPushButton()
            btn.setFixedSize(40, 40)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(theme_name)
            self.theme_btns[theme_name] = btn
            btn.clicked.connect(lambda checked=False, t=theme_name: self._change_theme(t))
            themes_layout.addWidget(btn)
            
        themes_layout.addStretch()
        app_card_layout.addLayout(themes_layout)
        layout.addWidget(appearance_card)

        layout.addStretch()
        
        self._update_theme_buttons()
        ThemeManager.apply_theme_to_widget(self)

    def _update_theme_buttons(self):
        current = ThemeManager.get_current_theme_name()
        for theme_name, btn in self.theme_btns.items():
            primary = ThemeManager.THEMES[theme_name]["primary"]
            
            if theme_name == current:
                btn.setText("✓")
                btn.setStyleSheet(f"""
                    /* NOTHEME */
                    QPushButton {{
                        background-color: {primary};
                        border-radius: 20px;
                        color: #0B0D14; /* Dark contrast for the checkmark */
                        font-weight: bold;
                        font-size: 20px;
                        border: none;
                        padding: 0px;
                    }}
                """)
            else:
                btn.setText("")
                btn.setStyleSheet(f"""
                    /* NOTHEME */
                    QPushButton {{
                        background-color: {primary};
                        border-radius: 20px;
                        border: none;
                        padding: 0px;
                    }}
                """)

    def _change_theme(self, theme_name):
        ThemeManager.set_theme(theme_name)
        self._update_theme_buttons()

    def _set_edit_mode(self, editing):
        self.api_input.setReadOnly(not editing)
        self.api_input.setEchoMode(QLineEdit.Normal if editing else QLineEdit.Password)
        
        self.edit_btn.setVisible(not editing)
        self.save_btn.setVisible(editing)
        self.cancel_btn.setVisible(editing)
        
        if editing:
            self.api_input.setFocus()
            self.status_msg.hide()
            # Force style re-evaluation for the readOnly state
            self.api_input.style().unpolish(self.api_input)
            self.api_input.style().polish(self.api_input)
        else:
            self.api_input.style().unpolish(self.api_input)
            self.api_input.style().polish(self.api_input)

    def _on_edit_clicked(self):
        self._set_edit_mode(True)

    def _on_cancel_clicked(self):
        self.api_input.setText(self.current_key)
        self._set_edit_mode(False)

    def _on_save_clicked(self):
        new_key = self.api_input.text().strip()
        if new_key:
            tmdb_api.set_api_key(new_key)
            self.current_key = new_key
            self._set_edit_mode(False)
            
            self.status_msg.setText("✓ Saved successfully!")
            self.status_msg.setStyleSheet(f"color: {ThemeManager.get_color('primary')}; font-weight: 500;")
            
            # Emit signal to let MainWindow know it needs to refresh the app
            self.api_key_changed.emit()
        else:
            self.status_msg.setText("Error: API Key cannot be empty.")
            self.status_msg.setStyleSheet("color: #E53E3E; font-weight: 500;")
            
        self.status_msg.show()
        QTimer.singleShot(3000, self.status_msg.hide)

    def _on_browse_clicked(self):
        current_dir = self.dl_input.text()
        if not os.path.exists(current_dir):
            current_dir = os.path.expanduser("~")
            
        dir_path = QFileDialog.getExistingDirectory(self, "Select Download Directory", current_dir)
        if dir_path:
            # Fix path separators to match OS
            dir_path = os.path.normpath(dir_path)
            self.dl_input.setText(dir_path)
            DownloadManager().set_download_path(dir_path)
