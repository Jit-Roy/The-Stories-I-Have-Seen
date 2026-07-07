import sys
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import asyncio
import os
import time
import shutil
import tempfile
from urllib.parse import urlparse
import yt_dlp
from playwright.async_api import async_playwright
from curl_cffi import requests as cffi_requests
from maximizer import maximize_hls

class DownloadPausedException(Exception):
    pass
AD_DOMAINS = [
    'adtng.com', 'doubleclick.net', 'googlesyndication.com',
    'adnxs.com', 'rubiconproject.com', 'pubmatic.com', 'openx.net',
    'spotxchange.com', 'springserve.com', 'trafficjunky.com', 'trafficjunky.net',
    'exoclick.com', 'juicyads.com', 'trafficstars.com', 'plugrush.com',
    'adsystem', 'adserver', 'ad-delivery', 'imasdk.googleapis.com'
]

def trigger_download(url, metadata_type, captured_urls, media_found):
    if any(d in url.lower() for d in AD_DOMAINS):
        print(f"[!] Oracle ignored known ad stream: {url[:60]}...")
        return
    if url in captured_urls:
        return
    captured_urls.add(url)
    print(f"\n[+] ORACLE CAPTURE [{metadata_type}]: {url}")
    # Only signal 'found' for real downloadable HTTP(S) URLs.
    # blob: and mse:// are browser-internal pseudo-URLs that yt-dlp cannot
    # reach. If we set media_found for them we exit the pipeline in 5s
    # before the real player (iframe) has had a chance to load.
    if url.startswith('http'):
        media_found.set()


def make_oracle_layer_b(captured_urls, media_found):
    """ Factory: returns a Layer B response handler bound to the given state. """
    async def oracle_layer_b(response):
        """ Layer B: CDP Network Observer with Magic Bytes """
        url = response.url
        if not url.startswith("http"):
            return
            
        ct = response.headers.get('content-type', '').lower()
        if ('video' in ct or 'mpeg' in ct or 'application/x-mpegurl' in ct or '.mp4' in url or '.m3u8' in url or 'blob' in url):
            print(f"[DEBUG] {ct} -> {url[:100]}")

        media_ct = any(t in ct for t in [
            'video/', 'audio/', 'application/x-mpegurl',
            'application/vnd.apple.mpegurl', 'application/dash+xml', 'video/mp2t'
        ])
        # Removed '.json' — too many API/ad responses end in .json and cause false positives
        media_ext = any(url.lower().split('?')[0].endswith(e)
                        for e in ['.m3u8', '.mpd', '.mp4', '.ts', '.m4s', '.webm'])

        if media_ct or media_ext or '/media/hls/' in url.lower() or 'manifest' in url.lower():
            trigger_download(url, f"Layer B - ContentType/Ext ({ct})", captured_urls, media_found)
            return

        # Magic byte scan for obfuscated URLs / wrong content-types
        if 'octet-stream' in ct or not ct:
            try:
                body = await response.body()
                prefix = body[:16]
                if (prefix[4:8] == b'ftyp'           # MP4
                    or prefix[:7] == b'#EXTM3U'      # HLS manifest
                    or prefix[0] == 0x47             # MPEG-TS sync byte
                    or prefix[:4] == b'\x1a\x45\xdf\xa3'):  # WebM/MKV
                    trigger_download(url, "Layer B - Magic Bytes", captured_urls, media_found)
            except Exception:
                pass
    return oracle_layer_b

async def oracle_layer_d_and_a_poll(page, captured_urls, media_found):
    """ Layer D: Video Element Query and Layer A: Polling __captures """
    while not media_found.is_set():
        try:
            captures = await page.evaluate("() => window.__captures || []")
            for cap in captures:
                url = cap.get('url')
                if url:
                    trigger_download(url, f"Layer A - JS Hook ({cap.get('type')})", captured_urls, media_found)
            
            await page.evaluate("() => { window.__captures = []; }")

            sources = await page.evaluate("""() =>
                [...document.querySelectorAll('video, audio')]
                .filter(v => v.duration > 0 || v.currentTime > 0)
                .map(v => ({ src: v.src, currentSrc: v.currentSrc }))
            """)

            for src in sources:
                url = src.get('currentSrc') or src.get('src')
                if url:
                    trigger_download(url, "Layer D - Video Element", captured_urls, media_found)
        except Exception:
            pass
        await asyncio.sleep(2)

# ── 1. NAVIGATION GUARD ───────────────────────────────────────────────────────

async def install_navigation_guard(context, target_url: str):
    """
    Intercepts ALL document navigations. Aborts any that leave the allowed domains.
    Returns the 'allowed_hosts' set so callers can add new domains dynamically
    when navigating to embed player pages.
    """
    target_host = urlparse(target_url).netloc
    allowed_hosts = {target_host}  # mutable — callers can add embed domains

    async def combined_route_handler(route, request):
        url  = request.url
        host = urlparse(url).netloc

        # Only block TOP-LEVEL navigations away from allowed domains.
        # Sub-frame (iframe) navigations to player domains MUST be allowed.
        if request.resource_type == 'document' and host and host not in allowed_hosts:
            try:
                is_main_frame = request.frame and request.frame.parent_frame is None
            except Exception:
                is_main_frame = True
            if is_main_frame:
                print(f"[Guard] Blocked top-level redirect -> {url[:80]}")
                await route.abort()
                return
            else:
                print(f"[Guard] Allowed iframe embed -> {host}")

        await route.continue_()

    await context.route('**/*', combined_route_handler)
    print(f"[-] Navigation guard active for: {target_host}")
    return allowed_hosts  # caller holds a reference; add to it to expand allowlist

# ── 2. POPUNDER / POPUP HANDLER ─────────────────────────────────────────────

def setup_popunder_blocker(context, main_page):
    async def on_new_page(new_page):
        if new_page == main_page:
            return
        await asyncio.sleep(0.3)
        try:
            await new_page.close()
            print("[~] Closed popunder tab.")
        except Exception:
            pass

    context.on('page', lambda p: asyncio.create_task(on_new_page(p)))
    print("[-] Popunder blocker active.")

# ── 3. UNIVERSAL GATE CLEARER (BEHAVIORAL) ──────────────────────────────────

async def clear_gates(page, target_url: str, depth: int = 0) -> None:
    """
    Detects full-screen gate overlays and clicks the correct button
    using behavioral signals only. Recurses to handle stacked gates.
    """
    if depth > 4:
        return

    # ── Step 1: Known consent library shortcuts ───────────────────────────
    CONSENT_LIB_SELECTORS = [
        '#onetrust-accept-btn-handler',           # OneTrust
        '#CybotCookiebotDialogBodyButtonAccept',  # Cookiebot
        '.cc-accept',                             # Cookie Consent
        '[aria-label="Accept cookies"]',          # Generic aria
        '[data-testid="cookie-accept"]',          # Common test ID
        '.qc-cmp2-summary-buttons button:first-child',  # Quantcast
    ]

    for sel in CONSENT_LIB_SELECTORS:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=400):
                await btn.click()
                print(f"[Gate] Consent library button clicked: {sel}")
                await asyncio.sleep(1.5)
        except Exception:
            pass

    # ── Step 2: Detect full-viewport overlay ──────────────────────────────
    gate = await page.evaluate(f"""() => {{
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const targetHost = '{urlparse(target_url).netloc}';

        // A gate is a high-z-index element covering most of the viewport
        const overlays = [...document.querySelectorAll('*')].filter(el => {{
            const s  = window.getComputedStyle(el);
            const r  = el.getBoundingClientRect();
            const z  = parseInt(s.zIndex) || 0;
            return (
                z > 50
                && r.width  >= vw * 0.4
                && r.height >= vh * 0.4
                && s.display     !== 'none'
                && s.visibility  !== 'hidden'
                && parseFloat(s.opacity) > 0.05
            );
        }});

        if (!overlays.length) return null;

        // Pick the topmost overlay
        const gate = overlays.reduce((a, b) =>
            (parseInt(getComputedStyle(a).zIndex) || 0) >=
            (parseInt(getComputedStyle(b).zIndex) || 0) ? a : b
        );

        // Collect all clickable descendants
        const POSITIVE = /enter|confirm|agree|yes|adult|accept|allow|continue|proceed|ok|18|verify|access/i;
        const NEGATIVE = /exit|leave|no\\b|under|decline|cancel|deny|refuse|reject|close|skip/i;

        const clickables = [
            ...gate.querySelectorAll('a, button, [role="button"], input[type="submit"]')
        ]
        .filter(el => {{
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        }})
        .map((el, domOrder) => {{
            const rect   = el.getBoundingClientRect();
            const cls    = (el.className || '').toLowerCase();
            const id     = (el.id || '').toLowerCase();
            const vocab  = cls + ' ' + id;
            const href   = el.getAttribute('href') || '';

            // Destination analysis
            let destScore = 1;   // default: unknown, neutral
            if (!href || href === '#' || href.startsWith('javascript')) {{
                destScore = 3;   // onclick only = closes modal = very safe
            }} else {{
                try {{
                    const destHost = new URL(href, location.href).hostname;
                    destScore = (destHost === targetHost || destHost === '') ? 2 : -5;
                }} catch(e) {{ destScore = 1; }}
            }}

            const positiveVocab = POSITIVE.test(vocab) ? 4 : 0;
            const negativeVocab = NEGATIVE.test(vocab) ? -8 : 0;
            const domOrderScore = Math.max(0, 3 - domOrder);  // first = +3
            const areaScore     = Math.min(2, (rect.width * rect.height) / 10000);

            return {{
                tag:    el.tagName,
                cls,
                id,
                href,
                destScore,
                positiveVocab,
                negativeVocab,
                domOrderScore,
                areaScore,
                totalScore: destScore + positiveVocab + negativeVocab
                           + domOrderScore + areaScore,
                cx: Math.round(rect.left + rect.width  / 2),
                cy: Math.round(rect.top  + rect.height / 2),
            }};
        }});

        return {{ found: true, clickables }};
    }}""")

    if not gate or not gate.get('found'):
        return

    clickables = gate.get('clickables', [])
    if not clickables:
        return

    print(f"\n[Gate] Overlay detected with {len(clickables)} candidate(s):")
    for c in clickables:
        print(f"  score={c['totalScore']:+.1f}  tag={c['tag']}  "
              f"cls='{c['cls'][:40]}'  dest={c['destScore']}")

    # Sort by score, pick best
    ranked = sorted(clickables, key=lambda c: c['totalScore'], reverse=True)
    best   = ranked[0]

    # Safety threshold: if the best candidate still looks like an exit button, abort
    if best['totalScore'] < -3:
        print(f"[Gate] Best candidate score too low ({best['totalScore']:.1f}) "
              f"- all buttons look like exits. Skipping.")
        return

    print(f"[Gate] Clicking best candidate (score={best['totalScore']:+.1f}) "
          f"at ({best['cx']}, {best['cy']})")

    await page.mouse.click(best['cx'], best['cy'])
    await asyncio.sleep(2)

    # Recurse
    await clear_gates(page, target_url, depth + 1)

# ── 4. FAKE PLAY BUTTON FILTER ──────────────────────────────────────────────

async def is_fake_play_button(page, x: float, y: float, target_url: str) -> bool:
    """
    Checks the element at (x, y) before clicking.
    Returns True if it's likely a fake play button (ad link).
    """
    target_host = urlparse(target_url).netloc

    result = await page.evaluate(f"""(x, y) => {{
        const el = document.elementFromPoint(x, y);
        if (!el) return {{ fake: false, reason: 'no element' }};

        const tag  = el.tagName;
        const href = el.getAttribute('href') || el.closest('a')?.getAttribute('href') || '';
        const cls  = (el.className || '').toLowerCase();

        // External link = fake
        if (href) {{
            try {{
                const h = new URL(href, location.href).hostname;
                if (h && h !== '{target_host}') {{
                    return {{ fake: true, reason: 'external href: ' + h }};
                }}
            }} catch(e) {{}}
        }}

        // Opens in new tab = fake (real players never do this)
        const target = el.getAttribute('target') || el.closest('a')?.getAttribute('target');
        if (target === '_blank') {{
            return {{ fake: true, reason: 'opens in new tab' }};
        }}

        // Inside a video container = real
        const inVideoContainer = !!el.closest('video, [class*="player"], [id*="player"]');
        if (inVideoContainer) {{
            return {{ fake: false, reason: 'inside player container' }};
        }}

        return {{ fake: false, reason: 'no fake signals detected' }};
    }}""", x, y)

    if result.get('fake'):
        print(f"[FakePlay Filter] Blocked click at ({x:.0f},{y:.0f}): {result['reason']}")
        return True
    return False

async def click_watch_now(page) -> None:
    """
    Click the primary 'Watch Now' / play CTA button on the landing page.

    On sites like vidsrc.sbs, the video player iframe is dynamically injected
    ONLY after the user presses this button.  Without this click the page just
    shows movie metadata and no stream is ever loaded, so the Oracle captures
    nothing useful.

    Strategy:
    1. Try the known vidsrc.sbs button ID (#watchNowBtn) directly via JS click
       (bypasses scroll/visibility issues that plague Playwright locator).
    2. Fallback: try Playwright selectors (button, anchor with watch text).
    3. Fallback: JS heuristic scan of all clickable elements.
    After a successful click, wait for an iframe to appear and log its src.
    """

    # ── Priority 1: Direct JS click on known IDs (most reliable) ────────────
    clicked = await page.evaluate("""() => {
        // vidsrc.sbs uses id="watchNowBtn"; try known IDs first
        const ids = ['watchNowBtn', 'watch-now', 'watch_now', 'playBtn', 'play-btn'];
        for (const id of ids) {
            const el = document.getElementById(id);
            if (el) { el.click(); return 'id:' + id; }
        }
        return null;
    }""")
    if clicked:
        print(f"[Watch] JS-clicked element with {clicked}")
        await asyncio.sleep(4)
        await _log_injected_iframe(page)
        return

    # ── Priority 2: Playwright locators ─────────────────────────────────────
    WATCH_SELECTORS = [
        'button:has-text("Watch Now")',
        'a:has-text("Watch Now")',
        'button:has-text("Watch")',
        'a:has-text("Watch")',
        '[class*="watch-now"]',
        '[class*="watchnow"]',
        '[data-action="watch"]',
    ]
    for sel in WATCH_SELECTORS:
        try:
            btn = page.locator(sel).first
            # scroll into view then check visibility (element might be below fold)
            await btn.scroll_into_view_if_needed(timeout=800)
            if await btn.is_visible(timeout=600):
                href = await btn.get_attribute('href') or ''
                if href.startswith('http') and 'vidsrc' not in href:
                    continue  # external link — skip (would navigate away)
                await btn.click()
                print(f"[Watch] Playwright-clicked via selector: {sel}")
                await asyncio.sleep(4)
                await _log_injected_iframe(page)
                return
        except Exception:
            pass

    # ── Priority 3: Pure JS heuristic scan ──────────────────────────────────
    try:
        found = await page.evaluate("""() => {
            const WATCH_RE = /watch|play now|stream/i;
            const candidates = [...document.querySelectorAll('a, button, [role="button"]')]
                .filter(el => {
                    const r = el.getBoundingClientRect();
                    // Allow off-screen (height 0) since we'll scroll
                    if (r.width < 10) return false;
                    const text = (el.innerText || el.textContent || '').trim();
                    const href = el.getAttribute('href') || '';
                    return WATCH_RE.test(text) && !href.startsWith('http');
                });
            if (!candidates.length) return null;
            const el = candidates[0];
            el.scrollIntoView({ behavior: 'instant', block: 'center' });
            const r = el.getBoundingClientRect();
            return { cx: r.left + r.width / 2, cy: r.top + r.height / 2,
                     text: (el.innerText || '').trim().slice(0, 40) };
        }""")
        if found:
            await asyncio.sleep(0.3)  # let scroll settle
            print(f"[Watch] JS-heuristic click on '{found['text']}' "
                  f"at ({found['cx']:.0f}, {found['cy']:.0f})")
            await page.mouse.click(found['cx'], found['cy'])
            await asyncio.sleep(4)
            await _log_injected_iframe(page)
        else:
            print("[Watch] No 'Watch Now' button found — player may already be embedded.")
    except Exception as e:
        print(f"[Watch] Heuristic click failed: {e}")


async def _log_injected_iframe(page) -> None:
    """After clicking Watch Now, log any newly injected player iframes."""
    try:
        iframes = await page.evaluate("""() =>
            [...document.querySelectorAll('iframe')]
                .filter(f => {
                    const r = f.getBoundingClientRect();
                    return r.width > 200 && r.height > 100;
                })
                .map(f => f.src || f.getAttribute('data-src') || '')
                .filter(Boolean)
        """)
        if iframes:
            print(f"[Watch] Player iframe(s) detected after click:")
            for src in iframes:
                print(f"  → {src}")
        else:
            print("[Watch] No player iframe visible yet after click.")
    except Exception:
        pass




async def remove_overlays(page):

    await page.evaluate("""() => {
        // Target video OR iframe (since videos are often iframed)
        const media = [...document.querySelectorAll('video, iframe')].find(el => {
            const r = el.getBoundingClientRect();
            return r.width > 200 && r.height > 150;
        });
        if (!media) return;
        const rect = media.getBoundingClientRect();
        const els = document.elementsFromPoint(rect.left + rect.width/2, rect.top + rect.height/2);
        for (const el of els) {
            if (el === media || media.contains(el)) break;
            const s = window.getComputedStyle(el);
            // Remove transparent/invisible clickjacking divs
            if (s.opacity < 0.1 || s.visibility === 'hidden' || s.backgroundColor === 'rgba(0, 0, 0, 0)') {
                el.remove();
            }
        }
    }""")

async def auto_player_loop(page, target_url, media_found, duration=20):
    print("[-] Auto-player active...")
    deadline = time.time() + duration

    PLAY_JS = """() => {
        const results = [];
        let isPlaying = false;
        const tryPlay = (root) => {
            const videos = [...root.querySelectorAll('video')];
            for (const v of videos) {
                const src = v.src || v.currentSrc || '';
                
                // Fast-forward known ads to skip them instantly
                if (src && /adtng|trafficjunky|doubleclick|adnxs/i.test(src)) {
                    if (v.duration > 0 && v.currentTime < v.duration - 1) {
                        v.currentTime = v.duration - 0.1;
                    }
                }
                
                const r = v.getBoundingClientRect();
                if (!v.paused && v.currentTime > 0 && r.width > 200) {
                    isPlaying = true;
                } else {
                    v.muted = true;
                    v.play().catch(() => {});
                    if (src && !/adtng|trafficjunky|doubleclick|adnxs/i.test(src)) {
                        results.push(src);
                    }
                }
            }
        };

        tryPlay(document);

        document.querySelectorAll('*').forEach(el => {
            if (el.shadowRoot) tryPlay(el.shadowRoot);
        });

        return { results, isPlaying };
    }"""

    while time.time() < deadline and not media_found.is_set():  # noqa: E501
        try:
            is_playing = False
            res = await page.evaluate(PLAY_JS)
            if res:
                if res.get('results'):
                    print(f"[~] Auto-player triggered on main frame: {res['results']}")
                is_playing = res.get('isPlaying', False)

            for frame in page.frames:
                if frame == page.main_frame: continue
                try:
                    f_res = await frame.evaluate(PLAY_JS)
                    if f_res:
                        if f_res.get('results'):
                            print(f"[~] Auto-player triggered in iframe ({frame.url[:60]}): {f_res['results']}")
                        if f_res.get('isPlaying'):
                            is_playing = True
                except Exception:
                    pass

            video_box = await page.evaluate("""() => {
                const v = [...document.querySelectorAll('video, iframe')]
                           .find(v => {
                               if (v.offsetParent === null) return false;
                               const r = v.getBoundingClientRect();
                               return r.width > 200 && r.height > 150;
                           });
                if (!v) return null;
                const r = v.getBoundingClientRect();
                return { x: r.left + r.width/2, y: r.top + r.height/2, tag: v.tagName };
            }""")

            if video_box and not is_playing:
                print(f"[~] Auto-clicker targeting: {video_box['tag']} at ({video_box['x']:.0f}, {video_box['y']:.0f})")
                # Try clicking anyway to clear ad overlays, navigation guard will protect us
                await page.mouse.click(video_box['x'], video_box['y'])

        except Exception:
            pass

        await asyncio.sleep(2)

async def _extract_vidzee_embed_urls(page, page_url: str) -> list:
    """
    Read the VidZeeData JS object that vidsrc.sbs injects into every movie/TV page.
    This object contains all configured video server embed URL templates.

    Returns a prioritised list of fully-resolved embed URLs, ready to navigate to.
    Falls back to [] if VidZeeData is not found (e.g. on non-VidZee sites).
    """
    from urllib.parse import urlparse
    import re

    # Extract TMDB ID from the page URL (e.g. /movie/1339713/ or /movie/1339713)
    tmdb_match = re.search(r'/(?:movie|tv)/(\d+)(?:/|$)', page_url)
    if not tmdb_match:
        print("[VidZee] Could not extract TMDB ID from URL.")
        return []
    tmdb_id = tmdb_match.group(1)
    media_type = 'tv' if '/tv/' in page_url else 'movie'

    try:
        vz_data = await page.evaluate("""() => {
            if (!window.VidZeeData) return null;
            return {
                servers: window.VidZeeData.servers || [],
                mediaType: window.VidZeeData.mediaType || null,
                tmdbId: window.VidZeeData.tmdbId || null,
            };
        }""")
    except Exception as e:
        print(f"[VidZee] Failed to evaluate VidZeeData: {e}")
        return []

    if not vz_data:
        print("[VidZee] VidZeeData not present on this page.")
        return []

    servers = vz_data.get('servers') or []
    # servers can be a list or a dict keyed by position
    if isinstance(servers, dict):
        servers = list(servers.values())

    print(f"[VidZee] Found {len(servers)} server(s) in VidZeeData.")

    embed_urls = []
    for srv in servers:
        use_v2 = srv.get('use_v2') in (True, '1', 1)
        if media_type == 'movie':
            tpl = (srv.get('movie_url_v2') or srv.get('movie_url') if use_v2
                   else srv.get('movie_url'))
        else:
            tpl = (srv.get('tv_url_v2') or srv.get('tv_url') if use_v2
                   else srv.get('tv_url'))
        if not tpl:
            continue
        embed_url = (tpl
                     .replace('{tmdb_id}', tmdb_id)
                     .replace('{season}', '1')
                     .replace('{episode}', '1'))
        if embed_url and embed_url.startswith('http'):
            embed_urls.append(embed_url)

    return embed_urls



async def probe_all_servers(url, progress_callback=None):
    import json
    import subprocess
    def log(msg):
        print(msg)
        if progress_callback:
            progress_callback({"type": "log", "message": msg})

    log(f"[*] Probing all servers for: {url}")
    captured_urls = set()
    media_found = asyncio.Event()
    browser_cookies = []
    
    server_results = {}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--autoplay-policy=no-user-gesture-required',
                '--disable-features=PreloadMediaEngagementData',
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-infobars',
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800},
            locale='en-US',
            timezone_id='America/New_York',
        )

        allowed_hosts = await install_navigation_guard(context, url)
        
        await context.add_init_script(r'''
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true });
            if (!window.chrome) {
                window.chrome = {
                    runtime: { onMessage: { addListener: () => {}, removeListener: () => {} }, connect: () => ({}), sendMessage: () => {} },
                    loadTimes: () => ({}), csi: () => ({}), app: {}
                };
            }
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            const originalQuery = window.navigator.permissions ? window.navigator.permissions.query.bind(navigator.permissions) : null;
            if (originalQuery) {
                navigator.permissions.query = (parameters) => parameters.name === 'notifications' ? Promise.resolve({ state: Notification.permission }) : originalQuery(parameters);
            }
        ''')

        await context.add_init_script(r'''
            window.__captures = [];
            const _create = URL.createObjectURL;
            URL.createObjectURL = function(obj) {
                const url = _create.call(this, obj);
                window.__captures.push({ type: 'blob', url, mime: obj.type || '' });
                return url;
            };
            if (window.MediaSource) {
                const _addSB = MediaSource.prototype.addSourceBuffer;
                MediaSource.prototype.addSourceBuffer = function(mime) {
                    const sb = _addSB.call(this, mime);
                    window.__captures.push({ type: 'mse_mime', url: 'mse://' + mime, mime });
                    return sb;
                };
            }
            const desc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
            if (desc) {
                Object.defineProperty(HTMLMediaElement.prototype, 'src', {
                    set(v) {
                        if (v) window.__captures.push({ type: 'video_src', url: v });
                        desc.set.call(this, v);
                    }
                });
            }
            const _fetch = window.fetch;
            window.fetch = function(input, init) {
                const url = typeof input === 'string' ? input : (input ? input.url : '');
                if (url && /\.(m3u8|mpd|mp4|ts|m4s|webm)(?:[\?#]|$)/i.test(url)) {
                    window.__captures.push({ type: 'fetch', url });
                }
                return _fetch.call(this, input, init);
            };
        ''')

        context.on('response', make_oracle_layer_b(captured_urls, media_found))

        page = await context.new_page()
        setup_popunder_blocker(context, page)
        
        polling_task = asyncio.create_task(oracle_layer_d_and_a_poll(page, captured_urls, media_found))
        autoplay_task = None
        
        try:
            log(f"[-] Loading {url}...")
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            
            embed_urls = await _extract_vidzee_embed_urls(page, url)
            
            if embed_urls:
                log(f"[+] Extracted {len(embed_urls)} embed URL(s) from VidZeeData.")
                
                await page.evaluate('''() => {
                    if (!window.__vzEchoListenerAdded) {
                        window.addEventListener('message', function(evt) {
                            if (typeof evt.data === 'string' && evt.data.indexOf('vz_sb_echo_') === 0) {
                                if (evt.source) evt.source.postMessage(evt.data, '*');
                            }
                        });
                        window.__vzEchoListenerAdded = true;
                    }
                }''')
                
                for embed_url in embed_urls:
                    server_name = urlparse(embed_url).netloc
                    log(f"\n[-] Probing server: {server_name}")
                    
                    captured_urls.clear()
                    media_found.clear()
                    
                    try:
                        await page.evaluate(f'''() => {{
                            document.querySelectorAll('iframe[data-oracle-player]').forEach(f => f.remove());
                            const iframe = document.createElement('iframe');
                            iframe.src = '{embed_url}';
                            iframe.setAttribute('data-oracle-player', '1');
                            iframe.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:9999;border:none;';
                            iframe.allow = 'autoplay; fullscreen; picture-in-picture';
                            iframe.setAttribute('sandbox', 'allow-forms allow-pointer-lock allow-same-origin allow-scripts allow-top-navigation');
                            document.body.appendChild(iframe);
                        }}''')
                        
                        await asyncio.sleep(3)
                        
                        autoplay_task = asyncio.create_task(auto_player_loop(page, embed_url, media_found, duration=10))
                        
                        try:
                            await asyncio.wait_for(media_found.wait(), timeout=10.0)
                            await asyncio.sleep(2)
                        except asyncio.TimeoutError:
                            log(f"[!] No stream detected for {server_name}")
                            autoplay_task.cancel()
                            continue
                            
                        autoplay_task.cancel()
                        
                        # Find the first m3u8 in captured urls
                        m3u8_url = next((u for u in captured_urls if '.m3u8' in u.lower()), None)
                        if not m3u8_url:
                            log(f"[!] No m3u8 found for {server_name}, skipping format extraction.")
                            continue
                            
                        # Use yt-dlp -J to extract info
                        log(f"[-] Extracting languages and subtitles for {server_name}...")
                        current_cookies = await context.cookies()
                        cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in current_cookies])
                        
                        cmd = [
                            'yt-dlp', '-J', m3u8_url,
                            '--extractor-args', 'generic:impersonate',
                            '--add-header', f'Referer:{embed_url}',
                            '--add-header', f'User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
                            '--add-header', f'Cookie:{cookie_header}',
                            '--no-warnings'
                        ]
                        
                        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
                        if process.returncode == 0:
                            try:
                                info = json.loads(process.stdout)
                                
                                # Parse audio
                                audio_tracks = []
                                formats = info.get('formats', [])
                                for f in formats:
                                    if f.get('vcodec') == 'none':
                                        track_info = {
                                            'format_id': f.get('format_id'),
                                            'language': f.get('language') or f.get('format_note') or 'Unknown'
                                        }
                                        if track_info not in audio_tracks:
                                            audio_tracks.append(track_info)
                                            
                                # Parse subtitles
                                subtitles = list(info.get('subtitles', {}).keys())
                                
                                server_results[server_name] = {
                                    'm3u8_url': m3u8_url,
                                    'embed_url': embed_url,
                                    'audio': audio_tracks,
                                    'subtitles': subtitles
                                }
                                log(f"[+] {server_name} - Found {len(audio_tracks)} audio track(s), {len(subtitles)} subtitle(s)")
                                
                            except json.JSONDecodeError:
                                log(f"[!] Failed to parse yt-dlp JSON output for {server_name}")
                        else:
                            log(f"[!] yt-dlp failed for {server_name}")
                            
                    except Exception as e:
                        log(f"[!] Exception probing {server_name}: {e}")
            else:
                log("[!] No embed URLs found. Cannot probe multi-server.")
                
        except Exception as e:
            log(f"[!] Probe error: {e}")
        finally:
            polling_task.cancel()
            if autoplay_task: autoplay_task.cancel()
            try:
                browser_cookies = await context.cookies()
            except:
                pass
            await browser.close()
            log("[*] Browser closed.")
            
    return server_results, browser_cookies

async def intercept_media(url, download_path="Downloads", progress_callback=None, abort_event=None, filename_prefix=None):
    def log(msg):
        print(msg)
        if progress_callback:
            progress_callback({"type": "log", "message": msg})
            
    log(f"[*] Starting FULLY AUTOMATED Oracle & Driver for: {url}")
    
    # Fresh state per call — prevents stale captures from previous runs
    captured_urls = set()
    media_found = asyncio.Event()
    browser_cookies = []  # will be populated before browser closes
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--autoplay-policy=no-user-gesture-required',
                '--disable-features=PreloadMediaEngagementData',
                # ── Stealth: mask automation fingerprints ──────────────────
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-infobars',
            ]
        )
        context = await browser.new_context(
            # Match a real, recent Chrome build so UA checks pass
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800},
            locale='en-US',
            timezone_id='America/New_York',
        )

        allowed_hosts = await install_navigation_guard(context, url)
        
        # ── Stealth init script: mask webdriver fingerprints ──────────────
        # content-shield.js detects navigator.webdriver and CDP/devtools
        # presence. We must patch these BEFORE any page JS runs.
        await context.add_init_script(r"""
            // 1. Remove the webdriver property (Playwright sets it to true)
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
                configurable: true,
            });

            // 2. Restore chrome runtime object that headless Chrome is missing
            if (!window.chrome) {
                window.chrome = {
                    runtime: {
                        onMessage: { addListener: () => {}, removeListener: () => {} },
                        connect: () => ({}),
                        sendMessage: () => {},
                    },
                    loadTimes: () => ({}),
                    csi: () => ({}),
                    app: {},
                };
            }

            // 3. Spoof plugins array (automation shows 0 plugins)
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });

            // 4. Spoof languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });

            // 5. Remove automation-specific property from permission query
            const originalQuery = window.navigator.permissions
                ? window.navigator.permissions.query.bind(navigator.permissions) : null;
            if (originalQuery) {
                navigator.permissions.query = (parameters) =>
                    parameters.name === 'notifications'
                        ? Promise.resolve({ state: Notification.permission })
                        : originalQuery(parameters);
            }
        """);

        await context.add_init_script(r"""
            window.__captures = [];

            const _create = URL.createObjectURL;
            URL.createObjectURL = function(obj) {
                const url = _create.call(this, obj);
                window.__captures.push({ type: 'blob', url, mime: obj.type || '' });
                return url;
            };

            if (window.MediaSource) {
                const _addSB = MediaSource.prototype.addSourceBuffer;
                MediaSource.prototype.addSourceBuffer = function(mime) {
                    const sb = _addSB.call(this, mime);
                    window.__captures.push({ type: 'mse_mime', url: 'mse://' + mime, mime });
                    return sb;
                };
            }

            const desc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
            if (desc) {
                Object.defineProperty(HTMLMediaElement.prototype, 'src', {
                    set(v) {
                        if (v) window.__captures.push({ type: 'video_src', url: v });
                        desc.set.call(this, v);
                    }
                });
            }

            const _fetch = window.fetch;
            window.fetch = function(input, init) {
                const url = typeof input === 'string' ? input : (input ? input.url : '');
                if (url && /\.(m3u8|mpd|mp4|ts|m4s|webm)(?:[\?#]|$)/i.test(url)) {
                    window.__captures.push({ type: 'fetch', url });
                }
                return _fetch.call(this, input, init);
            };
        """)

        context.on('response', make_oracle_layer_b(captured_urls, media_found))

        page = await context.new_page()
        setup_popunder_blocker(context, page)
        
        polling_task = asyncio.create_task(oracle_layer_d_and_a_poll(page, captured_urls, media_found))
        autoplay_task = None
        
        try:
            log(f"[-] Loading {url}...")
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            
            # ── Phase 1: Extract embed player URLs from VidZeeData ────────────
            # vidsrc.sbs exposes all player server configs in window.VidZeeData.
            # We read these directly to get the embed URL without needing to
            # click "Watch Now" (which fails in Playwright due to content-shield).
            embed_urls = await _extract_vidzee_embed_urls(page, url)
            
            active_embed_url = None
            if embed_urls:
                log(f"[+] Extracted {len(embed_urls)} embed URL(s) from VidZeeData:")
                for eu in embed_urls:
                    print(f"    -> {eu}")
                
                # NEW STRATEGY: Instead of navigating to embed URLs (which fail
                # because players require being inside vidsrc.sbs as parent),
                # we inject the player iframe DIRECTLY into the vidsrc.sbs page.
                # This perfectly replicates what Watch Now button does, including
                # the postMessage vz_sb_echo_* handshake from the parent page.
                
                # First, set up the vz_sb_echo postMessage listener that the 
                # players use to verify they're inside the correct parent
                await page.evaluate("""() => {
                    // This is what vidsrc.sbs main.js does for sandbox validation
                    if (!window.__vzEchoListenerAdded) {
                        window.addEventListener('message', function(evt) {
                            if (typeof evt.data === 'string' && evt.data.indexOf('vz_sb_echo_') === 0) {
                                if (evt.source) evt.source.postMessage(evt.data, '*');
                            }
                        });
                        window.__vzEchoListenerAdded = true;
                    }
                }""")
                
                for embed_url in embed_urls:
                    print(f"\n[-] Injecting player iframe for: {embed_url}")
                    try:
                        # Inject the iframe into the current vidsrc.sbs page context
                        await page.evaluate(f"""() => {{
                            // Remove any existing player iframes
                            document.querySelectorAll('iframe[data-oracle-player]').forEach(f => f.remove());
                            
                            const iframe = document.createElement('iframe');
                            iframe.src = '{embed_url}';
                            iframe.setAttribute('data-oracle-player', '1');
                            iframe.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:9999;border:none;';
                            iframe.allow = 'autoplay; fullscreen; picture-in-picture';
                            iframe.setAttribute('sandbox', 
                                'allow-forms allow-pointer-lock allow-same-origin allow-scripts allow-top-navigation'
                            );
                            document.body.appendChild(iframe);
                        }}""")
                        
                        # Give the iframe time to load the player
                        await asyncio.sleep(5)
                        
                        # Log the iframe state
                        await _log_injected_iframe(page)
                        
                        # Run auto-player on ALL frames (including the new iframe)
                        autoplay_task = asyncio.create_task(
                            auto_player_loop(page, embed_url, media_found, duration=25)
                        )
                        
                        log(f"[-] Waiting up to 40s for stream from iframe player...")
                        try:
                            await asyncio.wait_for(media_found.wait(), timeout=40.0)
                            await asyncio.sleep(5)
                            active_embed_url = embed_url
                            break  # Got a stream!
                        except asyncio.TimeoutError:
                            log(f"[!] No stream from {embed_url[:60]} -- trying next server.")
                            autoplay_task.cancel()
                            autoplay_task = None
                    except Exception as inject_err:
                        print(f"[!] Iframe injection failed for {embed_url}: {inject_err}")
                        continue

            else:
                # Fallback: no VidZeeData found — try the original flow
                print("[!] VidZeeData not found -- falling back to Watch Now click flow.")
                await clear_gates(page, url)
                await click_watch_now(page)
                await remove_overlays(page)
                autoplay_task = asyncio.create_task(auto_player_loop(page, url, media_found, duration=30))
                log("[-] Waiting up to 45s for Oracle to intercept the streams...")
                try:
                    await asyncio.wait_for(media_found.wait(), timeout=45.0)
                    await asyncio.sleep(5)
                    active_embed_url = url
                except asyncio.TimeoutError:
                    log("[!] Oracle timed out. No streams found.")

                
        except Exception as e:
            print(f"[!] Error during automation: {e}")
        finally:
            polling_task.cancel()
            if autoplay_task: autoplay_task.cancel()
            # ── Extract cookies BEFORE closing the browser ──────────────────
            try:
                raw_cookies = await context.cookies()
                browser_cookies.extend(raw_cookies)
                print(f"[-] Harvested {len(raw_cookies)} session cookies from browser.")
            except Exception as ce:
                print(f"[!] Could not harvest cookies: {ce}")
            await browser.close()
            print("[*] Browser closed.")
            
    log(f"\n[*] ORACLE FINISHED. Captured {len(captured_urls)} unique streams.")
    
    # Prioritize manifests over individual chunks!
    best_url = None
    
    def has_ext(u, exts):
        base = u.lower().split('?')[0]
        return any(base.endswith(e) for e in exts)
        
    def is_manifest(u):
        return has_ext(u, ['.m3u8', '.mpd', 'master.json', 'playlist.json']) or '/media/hls/' in u.lower() or 'manifest' in u.lower() or 'm3u8' in u.lower()

    # Blob/MSE URLs are browser-only — yt-dlp cannot reach them. Exclude from all lists.
    real_urls = [cu for cu in captured_urls
                 if not cu.startswith('blob:') and not cu.startswith('mse://')]

    # 1. Look for manifests first
    manifests = [cu for cu in real_urls if is_manifest(cu)]
    # 2. Look for full MP4/MKV files (without byte ranges)
    full_files = [cu for cu in real_urls if has_ext(cu, ['.mp4', '.mkv']) and "range=" not in cu]
    # 3. Look for fragmented chunks (fallback, usually unplayable alone)
    fragments = [cu for cu in real_urls if has_ext(cu, ['.mp4', '.mkv'])]

    blob_urls = [cu for cu in captured_urls if cu.startswith('blob:')]
    mse_urls  = [cu for cu in captured_urls if cu.startswith('mse://')]

    referer_url = active_embed_url if active_embed_url else url

    if manifests:
        best_url = await maximize_hls(manifests, referer_url, cookies=browser_cookies)
    elif full_files:
        best_url = full_files[-1]
        print("\n[+] Found a full video file!")
    elif fragments:
        best_url = fragments[-1]
        print("\n[!] WARNING: Only intercepted a fragmented chunk (range request). This may not be playable on its own!")

    if best_url:
        print(f"\n[*] Selected URL: {best_url}")
        if ".php?" in best_url:
            download_raw(best_url, referer_url, cookies=browser_cookies, progress_callback=progress_callback, download_path=download_path, abort_event=abort_event, filename_prefix=filename_prefix)
        else:
            download_media(best_url, referer_url, cookies=browser_cookies, progress_callback=progress_callback, download_path=download_path, abort_event=abort_event, filename_prefix=filename_prefix)
    elif real_urls:
        # Last-resort: any real HTTP URL we captured
        last_url = real_urls[-1]
        print(f"\n[*] Selected URL (last-resort): {last_url}")
        if ".php?" in last_url:
            download_raw(last_url, referer_url, cookies=browser_cookies, progress_callback=progress_callback, download_path=download_path, abort_event=abort_event, filename_prefix=filename_prefix)
        else:
            download_media(last_url, referer_url, cookies=browser_cookies, progress_callback=progress_callback, download_path=download_path, abort_event=abort_event, filename_prefix=filename_prefix)
    elif blob_urls:
        print(f"\n[!] Only blob: URLs captured ({len(blob_urls)}). These are browser-only MSE streams.")
        print("    The player likely uses MediaSource Extensions (MSE). The 'Watch Now' button")
        print("    may not have been clicked, or the stream is served via MSE with no direct URL.")
        for b in blob_urls:
            print(f"    {b}")
    elif mse_urls:
        print(f"\n[!] Only MSE mime captures: {mse_urls}")

def _cookies_to_jar(cookies: list) -> dict:
    """Convert Playwright cookie dicts to a format curl_cffi can use."""
    return {c['name']: c['value'] for c in cookies}


def _write_netscape_cookies(cookies: list, path: str) -> None:
    """
    Write cookies in Netscape format so yt-dlp can use them via --cookies.
    This is the only reliable way to pass session cookies to yt-dlp.
    """
    lines = ["# Netscape HTTP Cookie File\n"]
    for c in cookies:
        domain    = c.get('domain', '')
        http_only = str(c.get('httpOnly', False)).upper()
        path_val  = c.get('path', '/')
        secure    = str(c.get('secure', False)).upper()
        raw_exp   = c.get('expires', 0) or 0
        # Playwright returns -1 for session cookies (no expiry set).
        # Netscape cookie format requires a valid Unix timestamp; yt-dlp rejects -1.
        # Use a far-future date (year 2099) for session cookies so yt-dlp accepts them.
        expires   = int(raw_exp) if raw_exp > 0 else 4070908800  # 2099-01-01
        name      = c.get('name', '')
        value     = c.get('value', '')
        # Netscape format: domain \t flag \t path \t secure \t expires \t name \t value
        flag = 'TRUE' if domain.startswith('.') else 'FALSE'
        lines.append(f"{domain}\t{flag}\t{path_val}\tFALSE\t{expires}\t{name}\t{value}\n")
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines)


def download_raw(url, page_url, cookies=None, progress_callback=None, download_path=None, abort_event=None, filename_prefix=None):

    def log(msg):
        print(msg)
        if progress_callback:
            progress_callback({"type": "log", "message": msg})

    """
    Download a direct video file using curl_cffi with harvested browser cookies.
    Cookies are critical — the CDN binds tokens to the original session.
    """
    log(f"[-] Raw HTTP downloading (bypassing yt-dlp): {url}")
    
    base_name = filename_prefix or f"video_{int(time.time())}"
    out_filename = f"{base_name}.mp4"
    if download_path:
        os.makedirs(download_path, exist_ok=True)
        out_filename = os.path.join(download_path, out_filename)
        
    cookie_jar = _cookies_to_jar(cookies or [])
    try:
        # Check if we should resume
        mode = 'wb'
        initial_pos = 0
        headers = {
            'Referer': page_url,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36'
        }
        
        if os.path.exists(out_filename):
            initial_pos = os.path.getsize(out_filename)
            # We don't know total length yet, so we just attempt range request
            if initial_pos > 0:
                mode = 'ab'
                headers['Range'] = f"bytes={initial_pos}-"
                log(f"[+] Resuming raw download from {initial_pos} bytes...")
                
        with cffi_requests.get(
            url,
            headers=headers,
            cookies=cookie_jar,
            impersonate="chrome",
            allow_redirects=True,
            stream=True,
            timeout=60,
        ) as response:
            if response.status_code not in (200, 206):
                response.raise_for_status()
                
            total_length = int(response.headers.get('content-length', 0)) + initial_pos
            downloaded = initial_pos
            log(f"[+] Download started... saving to {out_filename}")
            with open(out_filename, mode) as out_file:
                for chunk in response.iter_content(chunk_size=1024 * 64):
                    if abort_event and abort_event.is_set():
                        raise DownloadPausedException("Download was paused.")
                    if chunk:
                        out_file.write(chunk)
                        downloaded += len(chunk)
                        if total_length > initial_pos and progress_callback:
                            percent = (downloaded / total_length) * 100
                            progress_callback({"type": "progress", "percent": percent})
        log(f"\n[+] Raw Download completed successfully! File saved as {out_filename}")
    except Exception as e:
        print(f"\n[!] Raw download failed: {e}")

def download_media(url, page_url=None, cookies=None, headers=None, progress_callback=None, download_path=None, abort_event=None, filename_prefix=None, audio_format_id=None, subtitle_lang=None):
    from yt_dlp.utils import check_executable
    if not check_executable('ffmpeg'):
        raise Exception("FFmpeg is missing! FFmpeg is REQUIRED to merge the video and audio tracks for this stream. Please install FFmpeg and add it to your system PATH.")

    def log(msg):
        print(msg)
        if progress_callback:
            progress_callback({"type": "log", "message": msg})

    # Monkey-patch yt-dlp to allow ANY file extension since streaming sites obfuscate them
    try:
        import yt_dlp.utils._utils
        if hasattr(yt_dlp.utils._utils, '_UnsafeExtensionError'):
            yt_dlp.utils._utils._UnsafeExtensionError.sanitize_extension = classmethod(lambda cls, ext, **kwargs: ext)
    except Exception:
        pass

    try:
        cookie_header = ""
        if cookies:
            cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            print(f"[-] Added {len(cookies)} session cookies to HTTP headers")

        base_name = filename_prefix or 'video_%(epoch)s'
        if download_path:
            os.makedirs(download_path, exist_ok=True)
            outtmpl = os.path.join(download_path, f'{base_name}.%(ext)s')
        else:
            outtmpl = f'{base_name}.%(ext)s'

        if audio_format_id:
            format_str = f'bestvideo+{audio_format_id}/bestvideo+bestaudio/best'
        else:
            format_str = 'bestvideo+bestaudio/best'

        http_headers = {
            'Referer': page_url,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
        }
        if cookie_header:
            http_headers['Cookie'] = cookie_header
            
        if headers:
            for k, v in headers.items():
                if k.startswith(':'):
                    continue
                if k.lower() not in ['accept-encoding', 'host', 'connection', 'cookie']:
                    http_headers[k] = v

        ydl_opts = {
            'outtmpl': outtmpl,
            'quiet': False,
            'no_warnings': True,
            'format': format_str,
            'hls_prefer_native': True,
            'enable_file_urls': True,
            'concurrent_fragment_downloads': 5,
            'retries': 30,
            'fragment_retries': 30,
            'file_access_retries': 30,
            'socket_timeout': 60,
            'extractor_args': {'generic': {'impersonate': ['chrome']}},
            'http_headers': http_headers,
        }

        if subtitle_lang:
            ydl_opts['writesubtitles'] = True
            ydl_opts['subtitleslangs'] = [subtitle_lang]
            ydl_opts['embedsubtitles'] = True
            ydl_opts['compat_opts'] = set(['no-live-chat']) # just to safely modify
    
        
        try:
            from tqdm import tqdm
            pbar = None
            def yt_dlp_tqdm_hook(d):
                if abort_event and abort_event.is_set():
                    raise DownloadPausedException("Download was paused.")
                    
                nonlocal pbar
                if d['status'] == 'downloading':
                    # Send progress to callback
                    if progress_callback:
                        total = d.get('total_bytes') or d.get('total_bytes_estimate')
                        if total and d.get('downloaded_bytes'):
                            percent = (d['downloaded_bytes'] / total) * 100
                            speed = d.get('speed', 0)
                            eta = d.get('eta', 0)
                            progress_callback({
                                "type": "progress", 
                                "percent": percent,
                                "speed": speed,
                                "eta": eta,
                                "total_bytes": total
                            })
                        elif d.get('fragment_count') and d.get('fragment_index'):
                            percent = (d['fragment_index'] / d['fragment_count']) * 100
                            speed = d.get('speed', 0)
                            eta = d.get('eta', 0)
                            progress_callback({
                                "type": "progress", 
                                "percent": percent,
                                "speed": speed,
                                "eta": eta,
                                "total_bytes": d.get('total_bytes') or d.get('total_bytes_estimate')
                            })

                    if pbar is None:
                        total = d.get('fragment_count') or d.get('total_bytes') or d.get('total_bytes_estimate')
                        unit = 'frag' if d.get('fragment_count') else 'B'
                        name = d.get('info_dict', {}).get('_filename', 'video').split('.')[-2][-10:]
                        desc = f"Downloading {name}"
                        pbar = tqdm(total=total, desc=desc, unit=unit, unit_scale=(unit == 'B'), dynamic_ncols=True)
                        
                    if pbar.unit == 'frag' and d.get('fragment_index'):
                        pbar.n = d.get('fragment_index')
                        
                        # Calculate custom ETA based on speed
                        if d.get('speed') and d.get('fragment_count'):
                            frags_left = d['fragment_count'] - d['fragment_index']
                            # Note: d['speed'] is in bytes/s, but we're tracking frags. 
                            # We'll just let tqdm calculate the ETA natively based on pbar.update() instead.
                            
                        pbar.refresh()
                    elif pbar.unit == 'B' and d.get('downloaded_bytes'):
                        pbar.n = d.get('downloaded_bytes')
                        pbar.refresh()
                        
                elif d['status'] == 'finished':
                    if pbar:
                        pbar.close()
                        pbar = None
                    log('\n[+] Download stream finished! Merging/Finalizing...')
                    
            ydl_opts['progress_hooks'] = [yt_dlp_tqdm_hook]
            ydl_opts['quiet'] = True
            ydl_opts['noprogress'] = True
        except ImportError:
            print("[!] tqdm is not installed (pip install tqdm) - using default yt-dlp progress.")

        # Removed cookie_file setting

        log(f"[-] Downloading: {url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        log("\n[+] Download completed successfully!")

    except Exception as e:
        import traceback
        print(f"\n[!] yt-dlp failed: {e}")
        traceback.print_exc()
        raise e
if __name__ == "__main__":
    test_url = "https://vidsrc.sbs/movie/1339713/"
    asyncio.run(intercept_media(test_url))
