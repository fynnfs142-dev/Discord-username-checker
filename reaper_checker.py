import itertools
import json
import os
import sys
import threading
import time
import webbrowser
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

try:
    from colorama import init as colorama_init
    colorama_init(autoreset=False)
except ImportError:
    pass

DISCORD_INVITE = "https://discord.gg/XWbjStSz5b"
GUNS_LOL_URL = "https://guns.lol/cke"
DISCORD_API_BASE = "https://discord.com/api/v9"

# ─── ANSI helpers ─────────────────────────────────────────────────────────────

RST  = "\033[0m"
BOLD = "\033[1m"

def _c(r, g, b):           return f"\033[38;2;{r};{g};{b}m"
def _bg(r, g, b):          return f"\033[48;2;{r};{g};{b}m"

# Palette — matches screenshot's cyan/teal art + magenta labels + purple body
CYAN      = _c(0,   210, 220)
CYAN2     = _c(0,   180, 200)
TEAL      = _c(0,   255, 200)
MAGENTA   = _c(220,  50, 255)
PURPLE    = _c(160,  80, 255)
PURPLE2   = _c(130,  60, 220)
WHITE     = _c(220, 220, 230)
GREY      = _c(100, 110, 130)
GREEN     = _c( 50, 230, 120)
RED       = _c(230,  60,  80)
YELLOW    = _c(255, 200,  50)
DIM       = _c( 70,  80,  95)
BG_DARK   = _bg(  8,  10,  16)

def _256(n): return f"\033[38;5;{n}m"

# Purple fade palette for the ASCII banner (dark→light purple)
_BANNER_SHADES = [
    _c( 80,  20, 160),
    _c(100,  30, 180),
    _c(120,  40, 200),
    _c(140,  55, 220),
    _c(160,  70, 240),
    _c(180,  90, 255),
    _c(200, 110, 255),
    _c(215, 135, 255),
    _c(230, 160, 255),
    _c(240, 185, 255),
]

# ─── ASCII Art (matches original) ─────────────────────────────────────────────

ASCII_REAPER = (
    "                .---.\n"
    "           '-.  |   |  .-'      \n"
    "             ___|   |___        \n"
    "        -=  [           ]  =-   \n"
    "            `---.   .---'       \n"
    "         __||__ |   | __||__    \n"
    "         '-..-' |   | '-..-'    \n"
    "           ||   |   |   ||      \n"
    "           ||_.-|   |-,_||      \n"
    '         .-`   \'`   `"-.        \n'
    "       .'                   '."
)

# ─── Terminal UI engine ────────────────────────────────────────────────────────

def _term_width():
    try:
        return os.get_terminal_size().columns
    except Exception:
        return 120


def _clear():
    os.system("cls" if os.name == "nt" else "clear")


def _hide_cursor():
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()


def _show_cursor():
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


def _move_to(row, col=1):
    sys.stdout.write(f"\033[{row};{col}H")


def _erase_line():
    sys.stdout.write("\033[2K")


# ─── Banner with fade-in ───────────────────────────────────────────────────────

def play_fade_intro(duration: float = 3.5, step: float = 0.09):
    _clear()
    _hide_cursor()
    lines = ASCII_REAPER.lstrip("\n").split("\n")
    total = int(duration / step)
    n = len(_BANNER_SHADES)

    for frame in range(total):
        shade_idx = min(frame * n // total, n - 1)
        color = _BANNER_SHADES[shade_idx]
        sub_color = _BANNER_SHADES[max(0, shade_idx - 2)]

        # Build full frame in one string, then write atomically
        buf = "\033[H"   # move cursor to absolute top-left (no scroll)
        for line in lines:
            buf += f"{color}{line:<120}{RST}\n"
        buf += f"\n{sub_color}  DC-Checker By Reaper  {GREY}•{RST} {sub_color}by @wgpf, @fdpw, @jvck{RST}\n"
        buf += "\033[J"  # erase everything below current position

        sys.stdout.write(buf)
        sys.stdout.flush()
        time.sleep(step)

    _show_cursor()


# ─── Dashboard renderer ────────────────────────────────────────────────────────

# State shared between threads and renderer
_state = {
    "requests":     0,
    "rps":          0,
    "hits":         0,
    "taken":        0,
    "errors":       0,
    "webhook_fails":0,
    "progress":     0,
    "total":        0,
    "elapsed":      0,
    "threads":      0,
    "feed":         deque(maxlen=20),   # list of (label, username, proxy_hint)
    "running":      True,
    "start_time":   0.0,
    "banner_lines": 0,
}

_render_lock = threading.Lock()

def _banner_colored():
    """Return the ASCII banner lines with per-character colour fade."""
    lines = ASCII_REAPER.lstrip("\n").split("\n")
    result = []
    n = len(_BANNER_SHADES)
    for i, line in enumerate(lines):
        shade = _BANNER_SHADES[min(i * (n - 1) // max(len(lines) - 1, 1), n - 1)]
        result.append(f"{shade}{line}{RST}")
    return result


def _bar(filled: int, total_width: int) -> str:
    """Render a progress bar like [=====>----]."""
    if total_width < 4:
        return ""
    inner = total_width - 2
    if _state["total"] > 0:
        ratio = min(_state["progress"] / _state["total"], 1.0)
    else:
        ratio = 0.0
    done = int(ratio * inner)
    rest = inner - done
    bar_fill = "=" * max(done - 1, 0) + (">" if done > 0 else "")
    bar_empty = "-" * rest
    pct = f"{ratio * 100:.1f}%"
    return (
        f"{GREY}[{RST}"
        f"{CYAN}{bar_fill}{RST}"
        f"{DIM}{bar_empty}{RST}"
        f"{GREY}]{RST} "
        f"{WHITE}{pct}{RST}"
    )


def _elapsed_str():
    s = int(time.time() - _state["start_time"])
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def _render_dashboard():
    """Full dashboard repaint — call from renderer thread only."""
    w = _term_width()
    sep = f"{DIM}{'─' * w}{RST}"

    banner_lines = _banner_colored()
    out = []

    # ── Banner ──────────────────────────────────────────────────────────────
    out.append("")
    for bl_raw, bl_colored in zip(ASCII_REAPER.lstrip("\n").split("\n"), banner_lines):
        # pad the raw text to fixed width so redraws never leave ghost chars
        out.append(f"  {bl_colored}")

    out.append(f"\n  {MAGENTA}DC-Checker By Reaper{RST}  {GREY}•{RST}  {PURPLE}made by @wgpf{RST}  {DIM}•{RST}  {PURPLE}@fdpw{RST}  {DIM}•{RST}  {PURPLE}@jvck{RST}")
    out.append(sep)

    # ── Stats row ────────────────────────────────────────────────────────────
    s = _state
    def stat(label, val, color=WHITE):
        return f"{GREY}{label}: {RST}{color}{BOLD}{val}{RST}"

    stats = "  ".join([
        stat("Requests", s["requests"]),
        stat("RPS",      s["rps"], CYAN),
        stat("Hits",     f"🔥 {s['hits']}", GREEN),
        stat("Taken",    s["taken"], RED),
        stat("Errors:",  s["errors"], YELLOW),
        stat("WebhookFails:", s["webhook_fails"], GREY),
    ])
    out.append(f"  {stats}")

    # ── Progress bar ─────────────────────────────────────────────────────────
    bar_label = (
        f"  {GREY}Progress: {RST}"
    )
    bar_w = max(w - 80, 20)
    prog_info = (
        f"  {s['progress']}/{s['total']} "
        f"{GREY}Elapsed: {_elapsed_str()}  "
        f"Threads:{s['threads']}{RST}"
    )
    out.append(f"{bar_label}{_bar(s['progress'], bar_w)}{prog_info}")
    out.append(sep)

    # ── Live feed header ──────────────────────────────────────────────────────
    out.append(f"  {WHITE}{BOLD}Live feed{RST} {GREY}(latest){RST}")
    out.append(sep)

    # ── Feed rows ─────────────────────────────────────────────────────────────
    feed = list(s["feed"])
    if not feed:
        out.append(f"  {DIM}Waiting for results…{RST}")
    else:
        for entry in feed[-16:]:
            label, username, proxy_hint, age_s = entry
            if label == "TAKEN":
                lbl_color = RED
            elif label == "HIT":
                lbl_color = GREEN
            elif label == "ERROR":
                lbl_color = YELLOW
            else:
                lbl_color = GREY

            age = f"{int(age_s)}s"
            row = (
                f"  {lbl_color}{BOLD}{label:<7}{RST}"
                f"  {GREY}{age:<4}{RST}"
                f"  {WHITE}{username:<20}{RST}"
                f"  {DIM}{proxy_hint}{RST}"
            )
            out.append(row)

    # Pad to keep footer stable
    feed_lines = len(feed) if feed else 1
    for _ in range(max(0, 16 - feed_lines)):
        out.append("")

    out.append(sep)
    out.append(
        f"  {DIM}CTRL+C to stop  {GREY}•{RST}  {DIM}hits → results/hits.txt  "
        f"{GREY}•{RST}  {DIM}made by @wgpf 💀{RST}"
    )

    return "\n".join(out)


class DashboardThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)

    def run(self):
        _hide_cursor()
        _clear()
        while _state["running"]:
            with _render_lock:
                content = _render_dashboard()
            # Single atomic write: home + content + clear-below
            sys.stdout.write("\033[H" + content + "\033[J")
            sys.stdout.flush()
            time.sleep(0.25)


class RpsThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self._prev = 0

    def run(self):
        while _state["running"]:
            time.sleep(1)
            cur = _state["requests"]
            _state["rps"] = cur - self._prev
            self._prev = cur
            _state["elapsed"] = int(time.time() - _state["start_time"])


# ─── Feed helper ──────────────────────────────────────────────────────────────

def _mask_proxy(proxy: str) -> str:
    """Mask proxy for display: keep host visible, hide last octet and password.
    e.g. '192.168.1.55:8080' -> '192.168.1.***:8080'
         'user:pass@192.168.1.55:8080' -> '192.168.1.***:8080'
         '192.168.1.55' -> '192.168.1.***'
    """
    if not proxy:
        return "no proxy"
    # Strip auth prefix (user:pass@)
    p = proxy
    if "@" in p:
        p = p.split("@", 1)[1]
    # Split host and port
    if ":" in p:
        host, port = p.rsplit(":", 1)
        # Mask last octet of IP
        parts = host.split(".")
        if len(parts) == 4:
            masked_host = ".".join(parts[:3]) + ".*"
        else:
            masked_host = host[:max(len(host)//2, 4)] + "***"
        return f"{masked_host}:{port}"
    else:
        parts = p.split(".")
        if len(parts) == 4:
            return ".".join(parts[:3]) + ".*"
        return p[:max(len(p)//2, 4)] + "***"


def _add_feed(label: str, username: str, proxy: str = ""):
    masked = _mask_proxy(proxy)
    ts = time.time()
    _state["feed"].appendleft((label, username, masked, 0))


def _tick_feed_ages():
    """Refresh age seconds in feed entries."""
    now = time.time()
    feed = list(_state["feed"])
    _state["feed"] = deque(
        [(lbl, un, ph, age + 0.25) for (lbl, un, ph, age) in feed],
        maxlen=20,
    )


# ─── Core logic (unchanged from original, wired to dashboard) ─────────────────

class TitleUpdater(threading.Thread):
    def __init__(self, stop_event):
        super().__init__(daemon=True)
        self.stop_event = stop_event

    def run(self):
        while not self.stop_event.is_set():
            title = (
                f"({_state['hits']} Hits) "
                f"({_state['taken']} Taken) "
                f"Reaper Checker"
            )
            try:
                if os.name == "nt":
                    os.system(f"title {title}")
                else:
                    sys.stdout.write(f"\033]0;{title}\007")
                    sys.stdout.flush()
            except Exception:
                pass
            self.stop_event.wait(3)


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        default = {"webhook": ""}
        with config_path.open("w") as f:
            json.dump(default, f, indent=4)
        return default
    try:
        with config_path.open() as f:
            return json.load(f)
    except Exception:
        return {"webhook": ""}


def save_config(config_path: Path, config: dict):
    try:
        with config_path.open("w") as f:
            json.dump(config, f, indent=4)
    except Exception:
        pass


def ensure_file(path: Path):
    if not path.exists():
        path.touch()


def read_names(path: Path):
    ensure_file(path)
    with path.open(encoding="utf-8", errors="ignore") as f:
        return [l.strip() for l in f if l.strip()]


def write_names(path: Path, names_iter):
    with path.open("w", encoding="utf-8") as f:
        for n in names_iter:
            f.write(n + "\n")


def remove_name_from_file(path: Path, username: str, lock: threading.Lock):
    with lock:
        try:
            names = read_names(path)
            write_names(path, [n for n in names if n != username])
        except Exception:
            pass


def prompt_combination_length():
    while True:
        try:
            v = input(f"\n{PURPLE}  [?] No names found. Combo length? (default 4): {RST}").strip()
            if not v:
                return 4
            n = int(v)
            if n > 0:
                return n
        except ValueError:
            pass


def generate_combinations(length: int):
    vowels, consonants = "aeiou", "bcdfghjklmnpqrstvwxyz"
    if length == 4:
        for pat in [
            [consonants, vowels, consonants, consonants],
            [consonants, consonants, vowels, consonants],
            [consonants, vowels, consonants, vowels],
        ]:
            for combo in itertools.product(*pat):
                yield "".join(combo)
    else:
        pattern = [consonants if i % 2 == 0 else vowels for i in range(length)]
        for combo in itertools.product(*pattern):
            yield "".join(combo)


def scrape_proxies(proxies_path: Path):
    if requests is None:
        return []
    urls = [
        "https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&proxy_format=ipport&format=text",
    ]
    collected = []
    for url in urls:
        try:
            r = requests.get(url, timeout=15)
            if r.ok:
                collected.extend(l.strip() for l in r.text.splitlines() if l.strip())
        except Exception:
            pass
    collected = list(dict.fromkeys(collected))
    if collected:
        with proxies_path.open("w") as f:
            f.write("\n".join(collected) + "\n")
    return collected


def load_proxies(proxies_path: Path):
    ensure_file(proxies_path)
    with proxies_path.open(encoding="utf-8", errors="ignore") as f:
        proxies = [l.strip() for l in f if l.strip()]
    if not proxies:
        proxies = scrape_proxies(proxies_path)
    return proxies


def get_next_proxy(proxies, idx_ref):
    if not proxies:
        return None
    p = proxies[idx_ref["i"] % len(proxies)]
    idx_ref["i"] += 1
    return p


def send_webhook(url: str, username: str) -> bool:
    if not url or not requests:
        return False
    try:
        r = requests.post(url.strip(), json={"content": f"`{username}` is available"}, timeout=10)
        return 200 <= r.status_code < 300
    except Exception:
        return False


def remove_proxy(proxies, proxy, proxies_path, lock):
    with lock:
        if proxy and proxy in proxies:
            proxies.remove(proxy)
            if proxies_path and proxies_path.exists():
                try:
                    with proxies_path.open("w") as f:
                        f.write("\n".join(proxies) + "\n")
                except Exception:
                    pass


def check_username(username, proxies, proxy_idx, proxies_path, timeout=30, proxy_lock=None, max_retries=5):
    if requests is None:
        return False, "requests_not_installed", ""
    lock = proxy_lock or threading.Lock()
    last_proxy = ""
    for attempt in range(max_retries):
        proxy = None
        try:
            with lock:
                proxy = get_next_proxy(proxies, proxy_idx) if proxies else None
            if proxy:
                last_proxy = proxy
            pd = {"http": f"http://{proxy}", "https": f"http://{proxy}"} if proxy else None
            resp = requests.post(
                f"{DISCORD_API_BASE}/unique-username/username-attempt-unauthed",
                headers={"Content-Type": "application/json"},
                json={"username": username},
                proxies=pd, timeout=timeout,
            )
            _state["requests"] += 1
            if resp.status_code in (200, 201, 204):
                try:
                    data = resp.json()
                except Exception:
                    return False, "bad_json", last_proxy
                taken = data.get("taken", True)
                return (not taken), ("taken" if taken else "available"), last_proxy
            if resp.status_code == 429:
                try:
                    ra = float(resp.json().get("retry_after", 1.0))
                except Exception:
                    ra = 1.0
                time.sleep(min(ra, 60.0))
                continue
            if 400 <= resp.status_code < 500:
                return False, f"http_{resp.status_code}", last_proxy
        except Exception as e:
            if proxy and proxies:
                remove_proxy(proxies, proxy, proxies_path, lock)
            time.sleep(0.5)
    return False, "max_retries_exceeded", last_proxy


# ─── Menu ─────────────────────────────────────────────────────────────────────

def show_menu():
    sys.stdout.write("\033[H\033[J")  # home + clear screen (no os.system flicker)
    sys.stdout.flush()
    banner = _banner_colored()
    print()
    for bl in banner:
        print(f"  {bl}")
    print(f"\n  {MAGENTA}DC-Checker By Reaper{RST}  {GREY}•{RST}  {PURPLE}by @wgpf, @fdpw, @jvck{RST}\n")
    w = _term_width()
    print(f"  {DIM}{'─' * (w - 4)}{RST}\n")
    print(f"  {CYAN}[1]{RST}  {WHITE}Discord{RST}")
    print(f"  {CYAN}[2]{RST}  {WHITE}Watch{RST} {GREY}(monitor single username){RST}")
    print(f"  {CYAN}[3]{RST}  {WHITE}Start Checker Fast{RST}")
    print()
    return input(f"  {PURPLE}Select option (1/2/3): {RST}").strip()


# ─── Checker ──────────────────────────────────────────────────────────────────

def run_checker(fast: bool = False):
    script_dir = Path(__file__).resolve().parent
    names_path = script_dir / "names.txt"
    proxies_path = script_dir / "proxies.txt"
    config_path = script_dir / "config.json"

    _clear()
    # Setup prompts shown BEFORE dashboard starts — plain lines, no banner reprint
    print(f"\n  {MAGENTA}Reaper Checker — Setup{RST}\n")

    config = load_config(config_path)
    saved_wh = config.get("webhook", "")
    if saved_wh:
        print(f"  {PURPLE}[*]{RST} Loaded webhook from config")
        use_s = input(f"  {PURPLE}Use saved webhook? (y/n, default y): {RST}").strip().lower()
        webhook_url = saved_wh if use_s in ("", "y", "yes") else input(f"  {PURPLE}New webhook (blank=skip): {RST}").strip()
    else:
        webhook_url = input(f"  {PURPLE}Discord webhook (blank=skip): {RST}").strip()
    if webhook_url:
        config["webhook"] = webhook_url
        save_config(config_path, config)

    results_dir = script_dir / "results"
    results_dir.mkdir(exist_ok=True)
    hits_path = results_dir / "hits.txt"
    ensure_file(hits_path)

    names = read_names(names_path)
    if not names:
        length = prompt_combination_length()
        write_names(names_path, generate_combinations(length))
        names = read_names(names_path)

    proxies = load_proxies(proxies_path)
    orig_proxy_count = len(proxies)

    proxy_idx = {"i": 0}
    proxy_lock = threading.Lock()
    names_lock = threading.Lock()
    hits_lock = threading.Lock()
    print_lock = threading.Lock()

    # Init dashboard state
    _state["total"]      = len(names)
    _state["progress"]   = 0
    _state["threads"]    = min(10, max(2, len(proxies) // 2)) if proxies else 4
    _state["start_time"] = time.time()
    _state["running"]    = True

    stop_title = threading.Event()
    TitleUpdater(stop_title).start()
    DashboardThread().start()
    RpsThread().start()

    def process_one(username):
        try:
            avail, status, proxy = check_username(
                username, proxies, proxy_idx, proxies_path,
                timeout=25 if fast else 30,
                proxy_lock=proxy_lock,
                max_retries=5 if fast else 3,
            )
            return username, avail, status, proxy
        except Exception as e:
            return username, False, f"exception:{e}", ""

    def do_result(username, available, status, proxy=""):
        _state["progress"] += 1
        if available:
            _state["hits"] += 1
            _add_feed("HIT", username, proxy)
            try:
                with hits_lock:
                    with hits_path.open("a") as f:
                        f.write(username + "\n")
            except Exception:
                pass
            if webhook_url:
                ok = send_webhook(webhook_url, username)
                if not ok:
                    _state["webhook_fails"] += 1
        else:
            if any(x in status for x in ("error", "exception", "max_retries")):
                _state["errors"] += 1
                _add_feed("ERROR", username, proxy)
            else:
                _state["taken"] += 1
                _add_feed("TAKEN", username, proxy)
            remove_name_from_file(names_path, username, names_lock)

    try:
        if fast:
            workers = _state["threads"]
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = {ex.submit(process_one, n): n for n in names}
                for fut in as_completed(futs):
                    try:
                        un, avail, status, proxy = fut.result(timeout=60)
                        do_result(un, avail, status, proxy)
                    except Exception as e:
                        _state["errors"] += 1
                        _state["progress"] += 1
        else:
            for username in names:
                try:
                    _, avail, status, proxy = process_one(username)
                    do_result(username, avail, status, proxy)
                    time.sleep(0.3)
                except Exception:
                    _state["errors"] += 1
                    _state["progress"] += 1

    except KeyboardInterrupt:
        pass
    finally:
        _state["running"] = False
        stop_title.set()
        _show_cursor()
        time.sleep(0.3)
        _clear()
        print(f"\n  {MAGENTA}=== Done ==={RST}")
        print(f"  {GREEN}Hits   : {_state['hits']}{RST}")
        print(f"  {RED}Taken  : {_state['taken']}{RST}")
        print(f"  {YELLOW}Errors : {_state['errors']}{RST}")
        print(f"  {PURPLE}Saved  → {hits_path}{RST}\n")


# ─── Watch mode ───────────────────────────────────────────────────────────────

def watch_username():
    script_dir = Path(__file__).resolve().parent
    proxies_path = script_dir / "proxies.txt"
    config_path = script_dir / "config.json"

    _clear()
    print(f"\n  {MAGENTA}=== Watch Mode ==={RST}\n")

    username = input(f"  {PURPLE}Username to watch: {RST}").strip()
    if not username:
        print(f"  {RED}[!] No username provided.{RST}")
        return

    config = load_config(config_path)
    saved_wh = config.get("webhook", "")
    webhook_url = ""
    if saved_wh:
        u = input(f"  {PURPLE}Use saved webhook? (y/n, default y): {RST}").strip().lower()
        webhook_url = saved_wh if u in ("", "y", "yes") else input(f"  {PURPLE}New webhook: {RST}").strip()
    else:
        webhook_url = input(f"  {PURPLE}Webhook URL (blank=skip): {RST}").strip()
    if webhook_url:
        config["webhook"] = webhook_url
        save_config(config_path, config)

    try:
        iv = input(f"  {PURPLE}Check interval seconds (default 5): {RST}").strip()
        interval = max(1.0, float(iv) if iv else 5.0)
    except ValueError:
        interval = 5.0

    proxies = load_proxies(proxies_path)
    proxy_idx = {"i": 0}
    proxy_lock = threading.Lock()
    check_count = 0

    results_dir = script_dir / "results"
    results_dir.mkdir(exist_ok=True)
    hits_path = results_dir / "hits.txt"
    ensure_file(hits_path)

    _state["total"]      = 0
    _state["start_time"] = time.time()
    _state["running"]    = True

    print(f"\n  {CYAN}Watching:{RST} {WHITE}{username}{RST}  {GREY}| interval {interval}s | CTRL+C to stop{RST}\n")
    w = _term_width()
    print(f"  {DIM}{'─' * (w - 4)}{RST}")

    try:
        while True:
            check_count += 1
            ts = time.strftime("%H:%M:%S")
            avail, status, _ = check_username(
                username, proxies, proxy_idx, proxies_path,
                timeout=30, proxy_lock=proxy_lock, max_retries=3,
            )
            if avail:
                print(f"  {GREEN}{BOLD}[{ts}] ✓ AVAILABLE!  {username} is free!{RST}")
                try:
                    with hits_path.open("a") as f:
                        f.write(f"{username}  — {ts}\n")
                except Exception:
                    pass
                if webhook_url:
                    send_webhook(webhook_url, username)
                print(f"\n  {PURPLE}Watch complete — username is yours to grab!{RST}\n")
                break
            else:
                st = status[:25] + "…" if len(status) > 25 else status
                remaining = len(proxies)
                print(f"  {RED}[{ts}] #{check_count:<5}{RST}  {WHITE}{username:<20}{RST}  {GREY}{st:<28}{RST}  {DIM}proxies:{remaining}{RST}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\n\n  {PURPLE}[!] Stopped after {check_count} checks.{RST}\n")
    finally:
        _state["running"] = False
        _show_cursor()


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    script_dir = Path(__file__).resolve().parent
    load_config(script_dir / "config.json")

    play_fade_intro(duration=3.5, step=0.09)

    try:
        webbrowser.open(DISCORD_INVITE)
        webbrowser.open(GUNS_LOL_URL)
    except Exception:
        pass

    while True:
        choice = show_menu()
        if choice == "1":
            webbrowser.open(DISCORD_INVITE)
        elif choice == "2":
            watch_username()
            break
        elif choice == "3":
            run_checker(fast=True)
            break
        else:
            pass


if __name__ == "__main__":
    main()
