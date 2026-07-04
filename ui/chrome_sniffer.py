import os
import sys
import subprocess
import asyncio
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, 
    QLabel, QWidget
)
from PySide6.QtCore import Qt, Signal, QThread
from playwright.async_api import async_playwright

class ChromeSnifferThread(QThread):
    stream_found = Signal(str, dict)
    log_msg = Signal(str)
    
    preview_requested = Signal(str)
    cookies_fetched = Signal(list)
    
    def __init__(self, movie_url):
        super().__init__()
        self.movie_url = movie_url
        self.is_running = True
        self.chrome_proc = None
        self.loop = None
        self.context = None

    def run(self):
        # We need to run the async playwright code inside this thread
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # Connect the preview request signal to our async method
        self.preview_requested.connect(self._handle_preview_request)
        
        try:
            self.loop.run_until_complete(self._sniff_loop())
        finally:
            self.loop.close()
            
    def _handle_preview_request(self, stream_url):
        if self.loop and self.context:
            asyncio.run_coroutine_threadsafe(self._open_preview_tab(stream_url), self.loop)
            
    def fetch_cookies(self):
        if self.loop and self.context:
            asyncio.run_coroutine_threadsafe(self._do_fetch_cookies(), self.loop)
            
    async def _do_fetch_cookies(self):
        try:
            cookies = await self.context.cookies()
            self.cookies_fetched.emit(cookies)
        except Exception as e:
            self.log_msg.emit(f"Cookie fetch error: {e}")
            self.cookies_fetched.emit([])

    async def _open_preview_tab(self, stream_url):
        try:
            self.log_msg.emit("Opening preview tab in Chrome...")
            page = await self.context.new_page()
            
            # Create a fake URL on vidsrc.sbs to bypass CORS and Referer restrictions
            fake_url = "https://vidsrc.sbs/preview_player"
            
            async def route_handler(route):
                html = f'''<!DOCTYPE html>
<html>
<head>
    <title>Stream Preview</title>
    <link rel="stylesheet" href="https://cdn.plyr.io/3.7.8/plyr.css" />
    <script src="https://cdn.jsdelivr.net/npm/hls.js@1"></script>
    <script src="https://cdn.plyr.io/3.7.8/plyr.polyfilled.js"></script>
    <style>
        body {{ background: black; margin: 0; padding: 0; overflow: hidden; display: flex; align-items: center; justify-content: center; height: 100vh; width: 100vw; }}
        video {{ width: 100%; height: 100%; }}
        :root {{ --plyr-color-main: #1AE0A1; }}
    </style>
</head>
<body>
    <video id="player" controls crossorigin playsinline></video>
    <script>
      const video = document.getElementById('player');
      const videoSrc = '{stream_url}';
      
      const defaultOptions = {{
          controls: ['play-large', 'play', 'progress', 'current-time', 'duration', 'mute', 'volume', 'captions', 'settings', 'pip', 'airplay', 'fullscreen'],
          seekTime: 10,
          keyboard: {{ focused: true, global: true }}
      }};

        const player = new Plyr(video, defaultOptions);
      if (Hls.isSupported()) {{
        const hls = new Hls({{
            debug: false,
            enableWorker: true,
            xhrSetup: function(xhr, url) {{
                xhr.withCredentials = true;
            }}
        }});
        hls.loadSource(videoSrc);
        hls.attachMedia(video);
        hls.on(Hls.Events.MANIFEST_PARSED, function() {{ 
            player.play(); 
        }});
      }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
        video.src = videoSrc;
        video.addEventListener('loadedmetadata', function() {{ player.play(); }});
      }}
    </script>
</body>
</html>'''
                await route.fulfill(content_type="text/html", body=html)

            # Only intercept our specific fake player URL
            await page.route(fake_url, route_handler)
            await page.goto(fake_url)
            
        except Exception as e:
            self.log_msg.emit(f"Preview Error: {{str(e)}}")

    async def _sniff_loop(self):
        chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
        if not os.path.exists(chrome_path):
            chrome_path = r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
            if not os.path.exists(chrome_path):
                self.log_msg.emit("Error: Could not find Google Chrome installed.")
                return

        user_data_dir = os.path.join(os.getcwd(), 'chrome_debug_profile')
        
        self.log_msg.emit("Launching Chrome...")
        self.chrome_proc = subprocess.Popen([
            chrome_path, 
            '--remote-debugging-port=9222', 
            f'--user-data-dir={user_data_dir}',
            '--disable-web-security',
            'about:blank'
        ])

        # Give chrome a few seconds to start the debugging port
        await asyncio.sleep(2)
        
        if not self.is_running:
            return

        async with async_playwright() as p:
            try:
                self.log_msg.emit("Connecting to Chrome Debugger...")
                browser = await p.chromium.connect_over_cdp('http://localhost:9222')
                contexts = browser.contexts
                
                if not contexts:
                    self.log_msg.emit("Error: No browser contexts found.")
                    return
                    
                self.context = contexts[0]
                pages = self.context.pages
                
                if not pages:
                    # Sometimes the page takes a second to be registered in CDP
                    await asyncio.sleep(2)
                    pages = self.context.pages
                    if not pages:
                        self.log_msg.emit("Error: No pages found.")
                        return
                
                # Get the first page
                page = pages[0]
                self.log_msg.emit(f"Connected! Loading {self.movie_url}...")

                async def on_response(response):
                    url = response.url
                    if response.status < 200 or response.status >= 300:
                        return
                        
                    headers = response.headers
                    content_type = headers.get('content-type', '').lower()
                    
                    is_hls = 'mpegurl' in content_type or 'application/x-mpegurl' in content_type
                    is_mp4 = 'video/mp4' in content_type
                    
                    if is_hls or is_mp4:
                        # Don't capture tiny fragments (like a 2-second .mp4 chunk or tiny ad playlist)
                        if is_mp4:
                            pass
                            
                        req_headers = await response.request.all_headers()
                        self.stream_found.emit(url, req_headers)
                    elif '.m3u8' in url:
                        # Fallback for some sites that might not set the correct content-type but end in .m3u8
                        req_headers = await response.request.all_headers()
                        self.stream_found.emit(url, req_headers)

                page.on('response', on_response)
                
                # Handle page reloads/navigations gracefully
                async def on_framenavigated(frame):
                    if frame == page.main_frame:
                        self.log_msg.emit("Page refreshed. Re-attaching sniffer...")
                        
                page.on('framenavigated', on_framenavigated)
                
                # Handle new tabs/windows (like if a hard refresh creates a new page context)
                def on_page(new_page):
                    # We don't want to attach sniffer to our own preview tab
                    if new_page.url == "https://vidsrc.sbs/preview_player": return
                    self.log_msg.emit("New page detected, attaching sniffer...")
                    new_page.on('response', on_response)
                
                self.context.on('page', on_page)

                # Safely navigate to the target page without blocking the sniffer loop
                async def safe_goto():
                    try:
                        await page.goto(self.movie_url, wait_until="domcontentloaded", timeout=15000)
                    except Exception as e:
                        self.log_msg.emit(f"Page load timeout/error (ignored): {str(e)}")
                
                asyncio.create_task(safe_goto())
                
                # Keep listening until stopped
                while self.is_running:
                    # Check if the page was closed by the user
                    if page.is_closed():
                        self.log_msg.emit("Chrome window closed by user.")
                        break
                    await asyncio.sleep(0.5)
                    
                self.log_msg.emit("Closing connection...")
                await browser.close()
                
            except Exception as e:
                self.log_msg.emit(f"Sniffer Error: {str(e)}")
            finally:
                if self.chrome_proc:
                    try:
                        self.chrome_proc.terminate()
                    except:
                        pass

    def stop(self):
        self.is_running = False
        if self.chrome_proc:
            try:
                self.chrome_proc.terminate()
            except:
                pass


class ChromeSnifferDialog(QDialog):
    def __init__(self, movie_id, parent=None):
        super().__init__(parent)
        self.movie_id = movie_id
        self.selected_m3u8 = None
        self.embed_url = f"https://vidsrc.sbs/embed/movie/{self.movie_id}"
        self.stream_headers = {}
        
        self.setWindowTitle("Chrome Stream Sniffer")
        self.resize(600, 300)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background-color: #0F172A;
            }
            QLabel {
                color: white;
                font-size: 14px;
            }
            QComboBox {
                background-color: #1E293B;
                color: white;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton {
                background-color: #1AE0A1;
                color: #0F172A;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #14B885;
            }
            QPushButton:disabled {
                background-color: #334155;
                color: #94A3B8;
            }
            #statusLabel {
                color: #14B885;
                font-style: italic;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(25, 25, 25, 25)

        lbl_inst = QLabel("Chrome is opening. Please play the video in the Chrome window.\nAs soon as the video starts, the detected streams will appear below.")
        lbl_inst.setWordWrap(True)
        layout.addWidget(lbl_inst)

        self.lbl_status = QLabel("Status: Starting up...")
        self.lbl_status.setObjectName("statusLabel")
        layout.addWidget(self.lbl_status)

        self.combo_streams = QComboBox()
        self.combo_streams.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self.combo_streams)
        
        layout.addStretch()

        btn_layout = QHBoxLayout()
        self.btn_preview = QPushButton("▶ Preview")
        self.btn_preview.setEnabled(False)
        self.btn_preview.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6; color: white; border-radius: 4px; padding: 8px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2563EB; }
            QPushButton:disabled { background-color: #334155; color: #94A3B8; }
        """)
        self.btn_preview.clicked.connect(self._on_preview)

        self.btn_proceed = QPushButton("Download Selected Stream")
        self.btn_proceed.setEnabled(False)
        self.btn_proceed.clicked.connect(self._on_proceed)
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("background-color: #EF4444; color: white; border-radius: 4px; padding: 8px 16px; font-weight: bold;")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_preview)
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(self.btn_proceed)
        layout.addLayout(btn_layout)

        # Start the sniffer thread
        self.thread = ChromeSnifferThread(self.embed_url)
        self.thread.stream_found.connect(self._on_stream_found)
        self.thread.log_msg.connect(self._on_log)
        self.thread.cookies_fetched.connect(self._on_cookies_fetched)
        self.thread.start()

    def _on_log(self, msg):
        self.lbl_status.setText(f"Status: {msg}")

    def _on_stream_found(self, url, headers):
        # Avoid exact duplicates
        for i in range(self.combo_streams.count()):
            if self.combo_streams.itemText(i) == url:
                return
                
        self.stream_headers[url] = headers
        self.combo_streams.addItem(url)
        self.combo_streams.setCurrentIndex(self.combo_streams.count() - 1)
        self.lbl_status.setText(f"Status: Sniffed {self.combo_streams.count()} streams!")

    def _on_combo_changed(self, index):
        if index >= 0:
            self.btn_proceed.setEnabled(True)
            self.btn_preview.setEnabled(True)
        else:
            self.btn_proceed.setEnabled(False)
            self.btn_preview.setEnabled(False)

    def _on_preview(self):
        current_text = self.combo_streams.currentText()
        if not current_text: return
        
        # Instead of ffplay, tell the Playwright thread to open a new tab 
        # with our hls.js player, completely bypassing CORS natively!
        self.thread.preview_requested.emit(current_text)

    def _on_proceed(self):
        current_text = self.combo_streams.currentText()
        if current_text:
            self.selected_m3u8 = current_text
            self.btn_proceed.setText("Fetching cookies...")
            self.btn_proceed.setEnabled(False)
            self.thread.fetch_cookies()

    def _on_cookies_fetched(self, cookies):
        self.sniffed_cookies = cookies
        self.accept()

    def get_selection(self):
        return {
            'm3u8_url': self.selected_m3u8,
            'embed_url': self.embed_url,
            'cookies': getattr(self, 'sniffed_cookies', []),
            'headers': self.stream_headers.get(self.selected_m3u8, {})
        }

    def closeEvent(self, event):
        self.thread.stop()
        self.thread.wait(2000)
        super().closeEvent(event)

    def reject(self):
        self.thread.stop()
        self.thread.wait(2000)
        super().reject()
