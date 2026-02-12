import itertools
import json
import os
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

try:
    from colorama import Fore, Style, init as colorama_init
except ImportError:
    Fore = Style = None
    colorama_init = None

DISCORD_INVITE = "https://discord.gg/XWbjStSz5b"
GUNS_LOL_URL = "https://guns.lol/cke"


ASCII_REAPER = r"""
                                                                                                                   
                                                                                                                   
RRRRRRRRRRRRRRRRR                                                                                                  
R::::::::::::::::R                                                                                                 
R::::::RRRRRR:::::R                                                                                                
RR:::::R     R:::::R                                                                                               
  R::::R     R:::::R    eeeeeeeeeeee    aaaaaaaaaaaaa  ppppp   ppppppppp       eeeeeeeeeeee    rrrrr   rrrrrrrrr   
  R::::R     R:::::R  ee::::::::::::ee  a::::::::::::a p::::ppp:::::::::p    ee::::::::::::ee  r::::rrr:::::::::r  
  R::::RRRRRR:::::R  e::::::eeeee:::::eeaaaaaaaaa:::::ap:::::::::::::::::p  e::::::eeeee:::::eer:::::::::::::::::r 
  R:::::::::::::RR  e::::::e     e:::::e         a::::app::::::ppppp::::::pe::::::e     e:::::err::::::rrrrr::::::r
  R::::RRRRRR:::::R e:::::::eeeee::::::e  aaaaaaa:::::a p:::::p     p:::::pe:::::::eeeee::::::e r:::::r     r:::::r
  R::::R     R:::::Re:::::::::::::::::e aa::::::::::::a p:::::p     p:::::pe:::::::::::::::::e  r:::::r     rrrrrrr
  R::::R     R:::::Re::::::eeeeeeeeeee a::::aaaa::::::a p:::::p     p:::::pe::::::eeeeeeeeeee   r:::::r            
  R::::R     R:::::Re:::::::e         a::::a    a:::::a p:::::p    p::::::pe:::::::e            r:::::r            
RR:::::R     R:::::Re::::::::e        a::::a    a:::::a p:::::ppppp:::::::pe::::::::e           r:::::r            
R::::::R     R:::::R e::::::::eeeeeeeea:::::aaaa::::::a p::::::::::::::::p  e::::::::eeeeeeee   r:::::r            
R::::::R     R:::::R  ee:::::::::::::e a::::::::::aa:::ap::::::::::::::pp    ee:::::::::::::e   r:::::r            
RRRRRRRR     RRRRRRR    eeeeeeeeeeeeee  aaaaaaaaaa  aaaap::::::pppppppp        eeeeeeeeeeeeee   rrrrrrr            
                                                        p:::::p                                                    
                                                        p:::::p                                                    
                                                       p:::::::p                                                   
                                                       p:::::::p                                                   
                                                       p:::::::p                                                   
                                                       ppppppppp                                                   
                                                                                                                   """


DISCORD_API_BASE = "https://discord.com/api/v9"


class TitleUpdater(threading.Thread):
    def __init__(self, valid_ref, invalid_ref, stop_event):
        super().__init__(daemon=True)
        self.valid_ref = valid_ref
        self.invalid_ref = invalid_ref
        self.stop_event = stop_event

    def run(self):
        titles = [
            "({valid} Valid) ({invalid} Invalid) (Reaper Checker)",
            "(Reaper Checker) ({valid} Valid) ({invalid} Invalid)",
            "Reaper Checker - V:{valid} I:{invalid}",
        ]
        idx = 0
        while not self.stop_event.is_set():
            title = titles[idx % len(titles)].format(
                valid=self.valid_ref["count"],
                invalid=self.invalid_ref["count"],
            )
            try:
                os.system(f"title {title}")
            except Exception:
                pass
            idx += 1
            self.stop_event.wait(5)


def init_colors():
    if colorama_init:
        colorama_init(autoreset=True)


# ANSI 256-color codes for dark purple -> light purple fade
_PURPLE_SHADES = (53, 54, 55, 56, 89, 90, 91, 129, 141, 165, 201, 213)


def _purple_fade_code(i: int) -> str:
    """Return ANSI color code for fading purple (256-color)."""
    idx = i % len(_PURPLE_SHADES)
    return f"\033[38;5;{_PURPLE_SHADES[idx]}m"


def play_fade_intro(duration: float = 4.0, step: float = 0.12):
    """Animate banner with fading dark purple to light purple text."""
    lines = [ASCII_REAPER.strip()] + [
        "",
        "=== Reaper Discord Username Checker ===",
        "https://github.com/diactine",
        "by @wgpf, @fdpw, @jvck",
    ]
    total_frames = int(duration / step)
    for frame in range(total_frames):
        code = _purple_fade_code(frame)
        reset = "\033[0m"
        if os.name == "nt":
            os.system("cls")
        else:
            os.system("clear")
        for line in lines:
            print(f"{code}{line}{reset}")
        time.sleep(step)


def show_menu() -> str:
    """Show options and return '1', '2', or '3'."""
    print()
    print(purple("  [1] Discord"))
    print(purple("  [2] Watch (monitor single username)"))
    print(purple("  [3] Start Checker Fast"))
    print()
    choice = input(purple("Select option (1/2/3): ")).strip()
    return choice


def purple(text: str) -> str:
    if Fore and Style:
        return f"{Fore.MAGENTA}{text}{Style.RESET_ALL}"
    return text


def green(text: str) -> str:
    if Fore and Style:
        return f"{Fore.GREEN}{text}{Style.RESET_ALL}"
    return text


def red(text: str) -> str:
    if Fore and Style:
        return f"{Fore.RED}{text}{Style.RESET_ALL}"
    return text


def load_config(config_path: Path) -> dict:
    """Load config from config.json, create if doesn't exist."""
    if not config_path.exists():
        # Create default config
        default_config = {
            "webhook": ""
        }
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4)
        print(purple(f"[+] Created {config_path.name}"))
        return default_config
    
    try:
        with config_path.open("r", encoding="utf-8") as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(red(f"[!] Error loading config: {e}"))
        return {"webhook": ""}


def save_config(config_path: Path, config: dict):
    """Save config to config.json."""
    try:
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(red(f"[!] Error saving config: {e}"))


def ensure_file(path: Path):
    if not path.exists():
        path.touch()


def read_names(names_path: Path):
    ensure_file(names_path)
    with names_path.open("r", encoding="utf-8", errors="ignore") as f:
        names = [line.strip() for line in f if line.strip()]
    return names


def write_names(names_path: Path, names_iter):
    with names_path.open("w", encoding="utf-8") as f:
        for name in names_iter:
            f.write(name + "\n")


def remove_name_from_file(names_path: Path, username: str, file_lock: threading.Lock):
    """Remove a single username from names.txt in a thread-safe way."""
    with file_lock:
        try:
            names = read_names(names_path)
            updated = [n for n in names if n != username]
            write_names(names_path, updated)
        except Exception as e:
            pass  # Don't crash the checker if file write fails


def prompt_combination_length():
    while True:
        try:
            value = input(purple("[?] No names found. How many letters per combination? (default 4): ")).strip()
            if not value:
                return 4
            length = int(value)
            if length <= 0:
                print(purple("[!] Please enter a positive number."))
                continue
            return length
        except ValueError:
            print(purple("[!] Invalid number, try again."))


def generate_combinations(length: int):
    """Generate pronounceable combinations using consonant-vowel patterns."""
    vowels = "aeiou"
    consonants = "bcdfghjklmnpqrstvwxyz"
    
    if length == 4:
        # For 4-letter names, use patterns like CVCC (jvck, jfck)
        # Patterns: CVCC, CCVC, CVCV
        patterns = [
            [consonants, vowels, consonants, consonants],  # CVCC (like jvck)
            [consonants, consonants, vowels, consonants],  # CCVC (like stop)
            [consonants, vowels, consonants, vowels],      # CVCV (like mama)
        ]
        
        for pattern in patterns:
            for combo in itertools.product(*pattern):
                yield "".join(combo)
    else:
        # For other lengths, alternate consonants and vowels
        pattern = []
        for i in range(length):
            if i % 2 == 0:
                pattern.append(consonants)
            else:
                pattern.append(vowels)
        
        for combo in itertools.product(*pattern):
            yield "".join(combo)


def scrape_proxies(proxies_path: Path):
    print(purple("[*] Scraping fresh proxies..."))
    if requests is None:
        print(purple("[!] The 'requests' library is not installed. Cannot scrape proxies."))
        return []

    urls = [
        # Proxyscrape free proxy list (HTTP/S)
        "https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&proxy_format=ipport&format=text",
    ]

    collected = []
    for url in urls:
        try:
            resp = requests.get(url, timeout=15)
            if resp.ok:
                lines = [line.strip() for line in resp.text.splitlines() if line.strip()]
                collected.extend(lines)
                print(purple(f"[+] Got {len(lines)} proxies from {url}"))
            else:
                print(purple(f"[!] Failed to fetch proxies from {url}: {resp.status_code}"))
        except Exception as e:
            print(purple(f"[!] Error scraping {url}: {e}"))

    collected = list(dict.fromkeys(collected))
    if collected:
        with proxies_path.open("w", encoding="utf-8") as f:
            for p in collected:
                f.write(p + "\n")
        print(purple(f"[+] Saved {len(collected)} proxies to {proxies_path.name}"))
    else:
        print(purple("[!] No proxies scraped. You can add your own to proxies.txt."))

    return collected


def load_proxies(proxies_path: Path):
    ensure_file(proxies_path)
    with proxies_path.open("r", encoding="utf-8", errors="ignore") as f:
        proxies = [line.strip() for line in f if line.strip()]
    if not proxies:
        proxies = scrape_proxies(proxies_path)
    return proxies


def get_next_proxy(proxies: list, index_ref: dict):
    """Get next proxy from list; index_ref['i'] is the current index."""
    if not proxies:
        return None
    idx = index_ref["i"] % len(proxies)
    index_ref["i"] += 1
    return proxies[idx]


def send_webhook(webhook_url: str, username: str) -> bool:
    # sends to discord webhook, message: `<name>` is available
    if not webhook_url or not webhook_url.strip():
        return False
    if not requests:
        return False
    try:
        content = f"`{username}` is available"
        r = requests.post(
            webhook_url.strip(),
            json={"content": content},
            timeout=10,
        )
        return 200 <= r.status_code < 300
    except Exception:
        return False


def remove_proxy(proxies: list, proxy: str, proxies_path: Path | None = None, lock: threading.Lock | None = None):
    """Remove a failing proxy from the list and optionally rewrite proxies.txt."""
    with (lock or threading.Lock()):
        if proxy and proxy in proxies:
            proxies.remove(proxy)
            if proxies_path is not None and proxies_path.exists():
                try:
                    with proxies_path.open("w", encoding="utf-8") as f:
                        for p in proxies:
                            f.write(p + "\n")
                except Exception:
                    pass  # Don't crash if file write fails


def check_username(
    username: str,
    proxies: list,
    proxy_index_ref: dict,
    proxies_path: Path | None,
    timeout: int = 30,
    proxy_lock: threading.Lock | None = None,
    max_retries: int = 5,
):
    """
    Check Discord username availability via the public /unique-username/username-attempt-unauthed endpoint.
    Failing proxies are removed from the list and from proxies.txt.
    
    FIX: Added max_retries to prevent infinite loops when all proxies fail.
    """
    if requests is None:
        return False, "requests_not_installed"

    lock = proxy_lock or threading.Lock()
    retry_count = 0
    
    while retry_count < max_retries:
        proxy = None
        try:
            with lock:
                if proxies:
                    proxy = get_next_proxy(proxies, proxy_index_ref)
                else:
                    # FIX: If no proxies available, try without proxy
                    proxy = None

            proxy_dict = None
            if proxy:
                proxy_url = f"http://{str(proxy).strip()}"
                proxy_dict = {"http": proxy_url, "https": proxy_url}

            resp = requests.post(
                url=f"{DISCORD_API_BASE}/unique-username/username-attempt-unauthed",
                headers={"Content-Type": "application/json"},
                json={"username": username},
                proxies=proxy_dict,
                timeout=timeout,
            )

            if resp.status_code in (200, 201, 204):
                try:
                    data = resp.json()
                except Exception:
                    return False, f"bad_json:{resp.text[:100]}"

                if "taken" not in data:
                    return False, f"no_taken_field"

                if data["taken"]:
                    return False, "taken"
                return True, "available"

            if resp.status_code == 429:
                try:
                    data = resp.json()
                    retry_after = float(data.get("retry_after", 1.0))
                except Exception:
                    retry_after = 1.0
                
                retry_after = min(retry_after, 60.0)
                time.sleep(retry_after)
                retry_count += 1
                continue

            if 400 <= resp.status_code < 500:
                return False, f"http_{resp.status_code}"
            
            retry_count += 1
            continue

        except (requests.exceptions.ProxyError,
                requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout,
                requests.exceptions.Timeout) as e:
            if proxy is not None and proxies:
                remove_proxy(proxies, proxy, proxies_path, lock=lock)
            
            retry_count += 1
            
            with lock:
                if not proxies and retry_count >= max_retries:
                    return False, "no_proxies_available"
            
            time.sleep(0.5)
            continue
            
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                return False, f"error:{str(e)[:100]}"
            time.sleep(0.5)
            continue
    
    return False, "max_retries_exceeded"


def run_checker(fast: bool = False):
    script_dir = Path(__file__).resolve().parent
    names_path = script_dir / "names.txt"
    proxies_path = script_dir / "proxies.txt"
    config_path = script_dir / "config.json"

    print(purple(ASCII_REAPER))
    print(purple("=== Reaper Discord Username Checker ==="))
    print(purple("https://github.com/diactine"))
    print(purple("by @wgpf, @fdpw, @jvck"))
    print()

    # Load config
    config = load_config(config_path)
    
    # Get webhook URL
    saved_webhook = config.get("webhook", "")
    if saved_webhook:
        print(purple(f"[*] Loaded webhook from config: {saved_webhook[:50]}..."))
        use_saved = input(purple("Use saved webhook? (y/n, default y): ")).strip().lower()
        if use_saved in ("", "y", "yes"):
            webhook_url = saved_webhook
        else:
            webhook_url = input(purple("Enter new discord webhook (leave blank to skip): ")).strip()
            if webhook_url:
                config["webhook"] = webhook_url
                save_config(config_path, config)
                print(purple("[+] Webhook saved to config.json"))
    else:
        webhook_url = input(purple("Discord webhook for valid names (leave blank to skip): ")).strip()
        if webhook_url:
            config["webhook"] = webhook_url
            save_config(config_path, config)
            print(purple("[+] Webhook saved to config.json"))

    results_dir = script_dir / "results"
    results_dir.mkdir(exist_ok=True)
    hits_path = results_dir / "hits.txt"
    ensure_file(hits_path)

    names = read_names(names_path)
    if not names:
        length = prompt_combination_length()
        print(purple(f"[*] Generating pronounceable combinations with length {length}..."))
        combos = generate_combinations(length)
        
        # Count total combinations for user info
        if length == 4:
            # 3 patterns × their sizes
            total = (21 * 5 * 21 * 21) + (21 * 21 * 5 * 21) + (21 * 5 * 21 * 5)
            print(purple(f"[*] This will generate approximately {total:,} pronounceable names"))
        
        write_names(names_path, combos)
        names = read_names(names_path)
        print(purple(f"[+] Generated {len(names)} names into {names_path.name}"))

    print(purple(f"[*] Loaded {len(names)} usernames from {names_path.name}"))

    proxies = load_proxies(proxies_path)
    print(purple(f"[*] Loaded {len(proxies)} proxies from {proxies_path.name}"))
    
    original_proxy_count = len(proxies)

    proxy_index_ref: dict = {"i": 0}
    proxy_lock = threading.Lock()
    # Separate lock for names.txt file writes to avoid conflicts with proxy_lock
    names_file_lock = threading.Lock()
    valid_counter = {"count": 0}
    invalid_counter = {"count": 0}
    error_counter = {"count": 0}
    print_lock = threading.Lock()

    stop_event = threading.Event()
    title_thread = TitleUpdater(valid_counter, invalid_counter, stop_event)
    title_thread.start()

    def process_one(username: str):
        try:
            available, status = check_username(
                username, proxies, proxy_index_ref, proxies_path,
                timeout=25 if fast else 30,
                proxy_lock=proxy_lock,
                max_retries=5 if fast else 3,
            )
            return username, available, status
        except Exception as e:
            return username, False, f"exception:{str(e)[:100]}"

    def do_result(username: str, available: bool, status: str):
        if available:
            valid_counter["count"] += 1
            with print_lock:
                print(green(f"[VALID ] {username}"))
            try:
                with proxy_lock:
                    with hits_path.open("a", encoding="utf-8") as f:
                        f.write(username + "\n")
            except Exception as e:
                with print_lock:
                    print(red(f"[ERROR] Failed to write to hits.txt: {e}"))
            
            if webhook_url:
                try:
                    send_webhook(webhook_url, username)
                except Exception:
                    pass
        else:
            if "error" in status or "exception" in status or "max_retries" in status:
                error_counter["count"] += 1
            invalid_counter["count"] += 1
            with print_lock:
                print(red(f"[INVALID] {username} ({status})"))
            # Remove invalid name from names.txt so the list shrinks as we check
            remove_name_from_file(names_path, username, names_file_lock)

    try:
        if fast:
            max_workers = min(10, max(2, len(proxies) // 2)) if proxies else 4
            print(purple(f"[*] Fast mode: checking up to {max_workers} names at a time"))
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(process_one, name): name for name in names}
                completed = 0
                total = len(names)
                
                for fut in as_completed(futures):
                    try:
                        username, available, status = fut.result(timeout=60)
                        do_result(username, available, status)
                        completed += 1
                        
                        if completed % 10 == 0:
                            with print_lock:
                                remaining_proxies = len(proxies)
                                print(purple(f"[*] Progress: {completed}/{total} | Proxies: {remaining_proxies}/{original_proxy_count} | Errors: {error_counter['count']}"))
                        
                    except Exception as e:
                        with print_lock:
                            print(red(f"[ERROR] {futures[fut]} - {e}"))
                        invalid_counter["count"] += 1
                        error_counter["count"] += 1
        else:
            total = len(names)
            for idx, username in enumerate(names, 1):
                try:
                    _, available, status = process_one(username)
                    do_result(username, available, status)
                    
                    if idx % 10 == 0:
                        with print_lock:
                            remaining_proxies = len(proxies)
                            print(purple(f"[*] Progress: {idx}/{total} | Proxies: {remaining_proxies}/{original_proxy_count} | Errors: {error_counter['count']}"))
                    
                    time.sleep(0.3)
                except Exception as e:
                    with print_lock:
                        print(red(f"[ERROR] {username} - {e}"))
                    invalid_counter["count"] += 1
                    error_counter["count"] += 1

        print(purple("\n=== Done ==="))
        print(green(f"Valid  : {valid_counter['count']}"))
        print(red(f"Invalid: {invalid_counter['count']}"))
        print(purple(f"Errors : {error_counter['count']}"))
        print(purple(f"Valid names saved to {hits_path}"))
        print(purple(f"Proxies remaining: {len(proxies)}/{original_proxy_count}"))
        
    except KeyboardInterrupt:
        print(purple("\n[!] Interrupted by user"))
    finally:
        stop_event.set()
        title_thread.join(timeout=2)


def watch_username():
    """Monitor a single username continuously until it becomes available or user stops."""
    script_dir = Path(__file__).resolve().parent
    proxies_path = script_dir / "proxies.txt"
    config_path = script_dir / "config.json"

    print(purple(ASCII_REAPER))
    print(purple("=== Reaper Username Watch Mode ==="))
    print(purple("https://github.com/diactine"))
    print(purple("by @wgpf, @fdpw, @jvck"))
    print()

    # Get username to watch
    username = input(purple("Enter username to watch: ")).strip()
    if not username:
        print(red("[!] No username provided"))
        return

    # Load config
    config = load_config(config_path)
    
    # Get webhook URL
    saved_webhook = config.get("webhook", "")
    if saved_webhook:
        print(purple(f"[*] Loaded webhook from config: {saved_webhook[:50]}..."))
        use_saved = input(purple("Use saved webhook? (y/n, default y): ")).strip().lower()
        if use_saved in ("", "y", "yes"):
            webhook_url = saved_webhook
        else:
            webhook_url = input(purple("Enter new discord webhook (leave blank to skip): ")).strip()
            if webhook_url:
                config["webhook"] = webhook_url
                save_config(config_path, config)
                print(purple("[+] Webhook saved to config.json"))
    else:
        webhook_url = input(purple("Discord webhook for notifications (leave blank to skip): ")).strip()
        if webhook_url:
            config["webhook"] = webhook_url
            save_config(config_path, config)
            print(purple("[+] Webhook saved to config.json"))

    # Get check interval
    try:
        interval_input = input(purple("Check interval in seconds (default 5): ")).strip()
        check_interval = float(interval_input) if interval_input else 5.0
        if check_interval < 1:
            check_interval = 1.0
            print(purple("[!] Minimum interval is 1 second"))
    except ValueError:
        check_interval = 5.0
        print(purple("[!] Invalid interval, using default 5 seconds"))

    # Load proxies
    proxies = load_proxies(proxies_path)
    print(purple(f"[*] Loaded {len(proxies)} proxies from {proxies_path.name}"))
    original_proxy_count = len(proxies)

    proxy_index_ref = {"i": 0}
    proxy_lock = threading.Lock()
    check_count = 0

    print()
    print(purple(f"[*] Watching username: {username}"))
    print(purple(f"[*] Check interval: {check_interval}s"))
    print(purple("[*] Press Ctrl+C to stop"))
    print()

    results_dir = script_dir / "results"
    results_dir.mkdir(exist_ok=True)
    hits_path = results_dir / "hits.txt"
    ensure_file(hits_path)

    try:
        while True:
            check_count += 1
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            
            try:
                available, status = check_username(
                    username, proxies, proxy_index_ref, proxies_path,
                    timeout=30,
                    proxy_lock=proxy_lock,
                    max_retries=3,
                )

                if available:
                    print(green(f"[{timestamp}] ✓ AVAILABLE! {username} is now available!"))
                    print(green(f"[*] Username became available after {check_count} checks"))
                    
                    # Save to hits
                    try:
                        with hits_path.open("a", encoding="utf-8") as f:
                            f.write(f"{username} - {timestamp}\n")
                        print(purple(f"[+] Saved to {hits_path}"))
                    except Exception as e:
                        print(red(f"[!] Error saving: {e}"))
                    
                    # Send webhook
                    if webhook_url:
                        try:
                            send_webhook(webhook_url, username)
                            print(purple("[+] Webhook notification sent"))
                        except Exception:
                            pass
                    
                    print(purple("\n[*] Watch complete! Username is available."))
                    break
                else:
                    remaining_proxies = len(proxies)
                    status_display = status[:30] + "..." if len(status) > 30 else status
                    print(red(f"[{timestamp}] Check #{check_count}: Not available ({status_display}) | Proxies: {remaining_proxies}/{original_proxy_count}"))
                
            except Exception as e:
                print(red(f"[{timestamp}] Check #{check_count}: Error - {str(e)[:50]}"))
            
            # Wait before next check
            time.sleep(check_interval)
            
    except KeyboardInterrupt:
        print(purple(f"\n\n[!] Watch stopped by user after {check_count} checks"))
        print(purple(f"[*] Username '{username}' was not available"))



def main():
    script_dir = Path(__file__).resolve().parent
    config_path = script_dir / "config.json"
    
    # Load or create config on startup
    load_config(config_path)
    
    init_colors()
    play_fade_intro(duration=4.0, step=0.12)
    webbrowser.open(DISCORD_INVITE)
    webbrowser.open(GUNS_LOL_URL)

    while True:
        choice = show_menu()
        if choice == "1":
            print(purple(f"[*] Opening Discord: {DISCORD_INVITE}"))
            webbrowser.open(DISCORD_INVITE)
        elif choice == "2":
            watch_username()
            break
        elif choice == "3":
            run_checker(fast=True)
            break
        else:
            print(red("[!] Invalid option. Enter 1, 2, or 3."))


if __name__ == "__main__":
    main()
