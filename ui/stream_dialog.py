from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QFrame
)
from PySide6.QtCore import Qt

class StreamSelectionDialog(QDialog):
    def __init__(self, results, parent=None):
        super().__init__(parent)
        self.results = results
        self.setWindowTitle("Select Stream Options")
        self.setFixedSize(400, 340)
        
        from ui.theme_manager import ThemeManager
        primary = ThemeManager.get_color("primary")
        
        self.setStyleSheet(f"""
            QDialog {{
                background-color: #1A1C23;
                color: white;
            }}
            QLabel {{
                font-size: 14px;
                color: #E2E8F0;
                font-weight: bold;
            }}
            QComboBox {{
                background-color: #2D3748;
                color: white;
                border: 1px solid #4A5568;
                border-radius: 4px;
                padding: 6px;
                font-size: 13px;
                combobox-popup: 0;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: #2D3748;
                color: white;
                selection-background-color: {primary};
                selection-color: #0F172A;
                border: 1px solid #4A5568;
                outline: none;
            }}
            QPushButton {{
                background-color: {primary};
                color: #0F172A;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 14px;
                border: none;
                margin: 2px;
            }}
            QPushButton:hover {{
                margin: 0px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Server Selection
        layout.addWidget(QLabel("1. Select Server"))
        self.server_combo = QComboBox()
        self.server_combo.addItems(list(self.results.keys()))
        self.server_combo.currentTextChanged.connect(self._on_server_changed)
        layout.addWidget(self.server_combo)

        # Audio Selection
        layout.addWidget(QLabel("2. Select Audio Language"))
        self.audio_combo = QComboBox()
        layout.addWidget(self.audio_combo)

        # Subtitle Selection
        layout.addWidget(QLabel("3. Select Subtitles (Optional)"))
        self.subtitle_combo = QComboBox()
        layout.addWidget(self.subtitle_combo)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        
        btn_confirm = QPushButton("Confirm Download")
        btn_confirm.clicked.connect(self.accept)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_confirm)
        layout.addLayout(btn_layout)

        # Trigger initial population
        if self.results:
            self._on_server_changed(list(self.results.keys())[0])

    def _on_server_changed(self, server_name):
        self.audio_combo.clear()
        self.subtitle_combo.clear()
        
        server_data = self.results.get(server_name, {})
        
        # Populate Audio
        audios = server_data.get('audio', [])
        if not audios:
            self.audio_combo.addItem("Default Audio", None)
        else:
            for audio in audios:
                self.audio_combo.addItem(audio['language'], audio['format_id'])
                
        # Populate Subtitles
        subtitles = server_data.get('subtitles', [])
        self.subtitle_combo.addItem("None", None)
        for sub in subtitles:
            self.subtitle_combo.addItem(sub.upper(), sub)

    def get_selection(self):
        server_name = self.server_combo.currentText()
        server_data = self.results.get(server_name, {})
        
        return {
            'm3u8_url': server_data.get('m3u8_url'),
            'embed_url': server_data.get('embed_url'),
            'cookies': server_data.get('cookies', []),
            'headers': server_data.get('headers', {}),
            'audio_id': self.audio_combo.currentData(),
            'subtitle': self.subtitle_combo.currentData()
        }
