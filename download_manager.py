import os
import asyncio
from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool
import threading
import yt_dlp

class WorkerSignals(QObject):
    progress = Signal(int, dict)
    finished = Signal(int, bool, str)

class ProbeWorkerSignals(QObject):
    progress = Signal(int, dict)
    finished = Signal(int, dict, str)

class ProbeWorker(QRunnable):
    def __init__(self, tmdb_id, url):
        super().__init__()
        self.tmdb_id = tmdb_id
        self.url = url
        self.signals = ProbeWorkerSignals()

    def run(self):
        try:
            import sys
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            
            import downloader
            def progress_cb(data):
                self.signals.progress.emit(self.tmdb_id, data)
                
            results, cookies = asyncio.run(downloader.probe_all_servers(self.url, progress_callback=progress_cb))
            self.signals.finished.emit(self.tmdb_id, results, "")
        except Exception as e:
            self.signals.finished.emit(self.tmdb_id, {}, str(e))

class FastProbeWorker(QRunnable):
    def __init__(self, tmdb_id, m3u8_url, embed_url, cookies=None, headers=None):
        super().__init__()
        self.tmdb_id = tmdb_id
        self.m3u8_url = m3u8_url
        self.embed_url = embed_url
        self.cookies = cookies or []
        self.headers = headers or {}
        self.signals = ProbeWorkerSignals()

    def run(self):
        try:
            cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in self.cookies]) if self.cookies else ""
            
            http_headers = {
                'Referer': self.embed_url,
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36'
            }
            
            # Merge sniffed headers if provided (this bypasses strict Cloudflare checks)
            for k, v in self.headers.items():
                if k.startswith(':'):
                    continue
                if k.lower() not in ['accept-encoding', 'host', 'connection']: # exclude browser-specific network headers that yt-dlp manages
                    http_headers[k] = v
                    
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'dump_single_json': True,
                'extract_flat': True,
                'extractor_args': {'generic': {'impersonate': ['chrome']}},
                'http_headers': http_headers
            }
            if cookie_header:
                ydl_opts['http_headers']['Cookie'] = cookie_header
            def progress_cb(msg):
                self.signals.progress.emit(self.tmdb_id, {"type": "log", "message": msg})
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                progress_cb("Probing fast stream...")
                info = ydl.extract_info(self.m3u8_url, download=False)
                
                audio_tracks = []
                subtitles = []
                
                formats = info.get('formats', [info])
                for f in formats:
                    if f.get('vcodec') == 'none' and f.get('acodec') != 'none':
                        audio_tracks.append({
                            'format_id': f.get('format_id', ''),
                            'language': f.get('language') or f.get('format_note') or 'Unknown'
                        })
                
                subs = info.get('subtitles', {})
                for lang, sub_list in subs.items():
                    subtitles.append(lang)
                
                results = {
                    "sniffed_stream": {
                        "m3u8_url": self.m3u8_url,
                        "embed_url": self.embed_url,
                        "cookies": self.cookies,
                        "headers": self.headers,
                        "audio": audio_tracks,
                        "subtitles": subtitles
                    }
                }
                
                self.signals.finished.emit(self.tmdb_id, results, "")
        except Exception as e:
            self.signals.finished.emit(self.tmdb_id, {}, str(e))

class DownloadWorker(QRunnable):
    def __init__(self, tmdb_id, url, page_url, audio_format_id, subtitle_lang, download_path, abort_event=None, filename_prefix=None, cookies=None, headers=None):
        super().__init__()
        self.tmdb_id = tmdb_id
        self.url = url
        self.page_url = page_url
        self.audio_format_id = audio_format_id
        self.subtitle_lang = subtitle_lang
        self.download_path = download_path
        self.abort_event = abort_event
        self.filename_prefix = filename_prefix
        self.cookies = cookies or []
        self.headers = headers or {}
        self.signals = WorkerSignals()

    def run(self):
        try:
            import sys
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                
            import downloader
            def progress_cb(data):
                self.signals.progress.emit(self.tmdb_id, data)

            downloader.download_media(
                url=self.url,
                page_url=self.page_url,
                cookies=self.cookies,
                headers=self.headers,
                progress_callback=progress_cb,
                download_path=self.download_path,
                abort_event=self.abort_event,
                filename_prefix=self.filename_prefix,
                audio_format_id=self.audio_format_id,
                subtitle_lang=self.subtitle_lang
            )
            self.signals.finished.emit(self.tmdb_id, True, "")
        except Exception as e:
            self.signals.finished.emit(self.tmdb_id, False, str(e))

class DownloadManager(QObject):
    _instance = None
    progress_updated = Signal(int, dict)
    status_updated = Signal(int, str)
    download_finished = Signal(int, bool, str)
    download_started = Signal(int, dict)
    probe_finished = Signal(int, dict, str)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DownloadManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self._initialized = True
        self.active_downloads = {} # tmdb_id -> { "movie_data": ..., "status": ... }
        self.abort_events = {}
        self.download_path = os.path.join(os.getcwd(), "Downloads")
        self.history_file = os.path.join(os.getcwd(), "downloads_history.json")
        os.makedirs(self.download_path, exist_ok=True)
        self.load_history()

    def load_history(self):
        import json
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
                for k, v in history.items():
                    self.active_downloads[int(k)] = {
                        "movie_data": v.get("movie_data", {}),
                        "status": v.get("status", "Unknown"),
                        "percent": v.get("percent", 0.0)
                    }
                    if self.active_downloads[int(k)]["status"] not in ("Completed", "Download Failed", "Error") and not self.active_downloads[int(k)]["status"].startswith("Error"):
                        self.active_downloads[int(k)]["status"] = "Paused"
            except Exception as e:
                print(f"Error loading download history: {e}")

    def save_history(self):
        import json
        history = {}
        for k, v in self.active_downloads.items():
            history[str(k)] = {
                "movie_data": v.get("movie_data", {}),
                "status": v.get("status", "Unknown"),
                "percent": v.get("percent", 0.0)
            }
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=4)
        except Exception as e:
            print(f"Error saving download history: {e}")

    def start_probe(self, movie_data):
        tmdb_id = movie_data["id"]
        url = f"https://vidsrc.sbs/movie/{tmdb_id}"
        
        if tmdb_id not in self.active_downloads:
            self.active_downloads[tmdb_id] = {
                "movie_data": movie_data,
                "status": "Probing servers...",
                "percent": 0.0,
                "speed": 0,
                "eta": 0,
            }
        else:
            self.active_downloads[tmdb_id]["status"] = "Probing servers..."
            
        self.status_updated.emit(tmdb_id, "Probing servers...")
        
        worker = ProbeWorker(tmdb_id, url)
        worker.signals.progress.connect(self._on_worker_progress)
        worker.signals.finished.connect(self._on_probe_finished)
        QThreadPool.globalInstance().start(worker)

    def _on_probe_finished(self, tmdb_id, results, error_msg):
        if not error_msg and results:
            self.active_downloads[tmdb_id]["status"] = "Pending selection..."
            self.status_updated.emit(tmdb_id, "Pending selection...")
        else:
            self.active_downloads[tmdb_id]["status"] = f"Probe Error: {error_msg}"
            self.status_updated.emit(tmdb_id, self.active_downloads[tmdb_id]["status"])
        self.probe_finished.emit(tmdb_id, results, error_msg)

    def start_fast_probe(self, movie_data, m3u8_url, embed_url, cookies=None, headers=None):
        tmdb_id = movie_data.get("id")
        if tmdb_id not in self.active_downloads:
            self.active_downloads[tmdb_id] = {}
        self.active_downloads[tmdb_id].update({
            "movie_data": movie_data,
            "status": "Pending selection..."
        })
        worker = FastProbeWorker(tmdb_id, m3u8_url, embed_url, cookies, headers)
        worker.signals.progress.connect(self._on_worker_progress)
        worker.signals.finished.connect(self._on_probe_finished)
        QThreadPool.globalInstance().start(worker)

    def start_download(self, item, m3u8_url=None, page_url=None, audio_format_id=None, subtitle_lang=None, cookies=None, headers=None):
        url = m3u8_url
        if not url:
            print("[!] start_download called without m3u8_url!")
            return
        tmdb_id = item.get("id")
        
        if tmdb_id not in self.active_downloads:
            self.active_downloads[tmdb_id] = {}
            
        self.active_downloads[tmdb_id].update({
            "movie_data": item,
            "status": "Initializing...", 
            "percent": 0, 
            "ETA": "Calculating...", 
            "speed": "0 KiB/s"
        })
        
        abort_event = threading.Event()
        self.abort_events[tmdb_id] = abort_event
        
        prefix = f"{item.get('title', 'Unknown')} ({item.get('year', '')})"
        prefix = prefix.replace(":", " -").replace("/", "-").replace("\\", "-")
        
        worker = DownloadWorker(tmdb_id, url, page_url, audio_format_id, subtitle_lang, self.download_path, abort_event, filename_prefix=prefix, cookies=cookies, headers=headers)
        
        self.active_downloads[tmdb_id].update({
            "status": "Initializing...",
            "worker": worker,
            "abort_event": abort_event
        })
        
        worker.signals.progress.connect(self._on_worker_progress)
        worker.signals.finished.connect(self._on_worker_finished)
        QThreadPool.globalInstance().start(worker)
        self.download_started.emit(tmdb_id, self.active_downloads[tmdb_id])
        self.status_updated.emit(tmdb_id, "Initializing...")
        self.save_history()

    def pause_download(self, tmdb_id):
        if tmdb_id in self.active_downloads:
            dl_info = self.active_downloads[tmdb_id]
            abort_event = dl_info.get("abort_event")
            if abort_event:
                abort_event.set()
                dl_info["status"] = "Pausing..."
                self.status_updated.emit(tmdb_id, "Pausing...")
                self.save_history()

    def resume_download(self, tmdb_id):
        # We can't actually resume because we don't save the m3u8_url in history yet.
        # But for now, we'll just set status.
        if tmdb_id in self.active_downloads:
            dl_info = self.active_downloads[tmdb_id]
            dl_info["status"] = "Error: Restart required"
            self.status_updated.emit(tmdb_id, "Error: Restart required")

    def _on_worker_progress(self, tmdb_id, data):
        if tmdb_id not in self.active_downloads:
            return
        
        dl_info = self.active_downloads[tmdb_id]
        if data["type"] == "log":
            msg = data["message"]
            if "Probing" in msg:
                dl_info["status"] = "Probing..."
            elif "Downloading:" in msg or "started..." in msg:
                dl_info["status"] = "Downloading..."
            elif "completed successfully" in msg:
                dl_info["status"] = "Finalizing..."
            self.status_updated.emit(tmdb_id, dl_info["status"])
        elif data["type"] == "progress":
            dl_info["status"] = "Downloading..."
            dl_info["percent"] = data.get("percent") or dl_info.get("percent", 0.0)
            dl_info["speed"] = data.get("speed") or dl_info.get("speed", 0)
            dl_info["eta"] = data.get("eta") or dl_info.get("eta", 0)
            self.progress_updated.emit(tmdb_id, dl_info)

    def _on_worker_finished(self, tmdb_id, success, error_msg):
        if tmdb_id in self.active_downloads:
            dl_info = self.active_downloads[tmdb_id]
            if not success and "Download was paused" in str(error_msg):
                dl_info["status"] = "Paused"
                self.status_updated.emit(tmdb_id, "Paused")
                self.save_history()
                return
                
            dl_info["status"] = "Completed" if success else f"Error: {error_msg}"
            if not success:
                import traceback
                with open("download_error.log", "w") as f:
                    f.write(f"Download Error for {tmdb_id}:\n{error_msg}\n")
            if success:
                dl_info["percent"] = 100.0
                import glob
                prefix = f"movie_{tmdb_id}"
                for p in glob.glob(os.path.join(self.download_path, f"{prefix}*.part*")) + glob.glob(os.path.join(self.download_path, f"{prefix}*.ytdl*")):
                    try:
                        os.remove(p)
                    except:
                        pass
                        
            self.status_updated.emit(tmdb_id, dl_info["status"])
            self.download_finished.emit(tmdb_id, success, error_msg or "")
            self.save_history()
