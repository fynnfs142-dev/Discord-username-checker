import itertools
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
    print(purple("  [2] Start Checker"))
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


def prompt_combination_length():
    while True:
        try:
            value = input(purple("[?] No names found. How many letters per combination? ")).strip()
            length = int(value)
            if length <= 0:
                print(purple("[!] Please enter a positive number."))
                continue
            return length
        except ValueError:
            print(purple("[!] Invalid number, try again."))


def generate_combinations(length: int):
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    return ("".join(chars) for chars in itertools.product(alphabet, repeat=length))


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
                with proxies_path.open("w", encoding="utf-8") as f:
                    for p in proxies:
                        f.write(p + "\n")


def check_username(
    username: str,
    proxies: list,
    proxy_index_ref: dict,
    proxies_path: Path | None,
    timeout: int = 30,
    proxy_lock: threading.Lock | None = None,
):
    """
    Check Discord username availability via the public /unique-username/username-attempt-unauthed endpoint.
    Failing proxies are removed from the list and from proxies.txt.
    """
    if requests is None:
        return False, "requests_not_installed"

    lock = proxy_lock or threading.Lock()
    while True:
        proxy = None
        try:
            with lock:
                if proxies:
                    proxy = get_next_proxy(proxies, proxy_index_ref)

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
                    return False, f"bad_json:{resp.text}"

                if "taken" not in data:
                    return False, f"no_taken_field:{data}"

                if data["taken"]:
                    return False, "taken"
                return True, "available"

            if resp.status_code == 429:
                try:
                    data = resp.json()
                    retry_after = float(data.get("retry_after", 1.0))
                except Exception:
                    retry_after = 1.0
                time.sleep(retry_after)
                continue

            return False, f"http_{resp.status_code}"

        except (requests.exceptions.ProxyError,
                requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout):
            if proxy is not None and proxies:
                remove_proxy(proxies, proxy, proxies_path, lock=lock)
            with lock:
                if not proxies:
                    return False, "no_proxies_left"
            continue
        except Exception as e:
            return False, f"error:{e}"


def run_checker(fast: bool = False):
    script_dir = Path(__file__).resolve().parent
    names_path = script_dir / "names.txt"
    proxies_path = script_dir / "proxies.txt"

    print(purple(ASCII_REAPER))
    print(purple("=== Reaper Discord Username Checker ==="))
    print(purple("https://github.com/diactine"))
    print(purple("by @wgpf, @fdpw, @jvck"))
    print()

    webhook_url = input(purple("discord webhook for valid names (leave blank to skip): ")).strip()

    results_dir = script_dir / "results"
    results_dir.mkdir(exist_ok=True)
    hits_path = results_dir / "hits.txt"
    ensure_file(hits_path)

    names = read_names(names_path)
    if not names:
        length = prompt_combination_length()
        print(purple(f"[*] Generating combinations with length {length}..."))
        combos = generate_combinations(length)
        write_names(names_path, combos)
        names = read_names(names_path)
        print(purple(f"[+] Generated {len(names)} names into {names_path.name}"))

    print(purple(f"[*] Loaded {len(names)} usernames from {names_path.name}"))

    proxies = load_proxies(proxies_path)
    print(purple(f"[*] Loaded {len(proxies)} proxies from {proxies_path.name}"))

    proxy_index_ref: dict = {"i": 0}
    proxy_lock = threading.Lock()
    valid_counter = {"count": 0}
    invalid_counter = {"count": 0}
    print_lock = threading.Lock()

    stop_event = threading.Event()
    title_thread = TitleUpdater(valid_counter, invalid_counter, stop_event)
    title_thread.start()

    def process_one(username: str):
        available, status = check_username(
            username, proxies, proxy_index_ref, proxies_path,
            timeout=25 if fast else 30,
            proxy_lock=proxy_lock,
        )
        return username, available, status

    def do_result(username: str, available: bool, status: str):
        if available:
            valid_counter["count"] += 1
            with print_lock:
                print(green(f"[VALID ] {username}"))
            with proxy_lock:
                with hits_path.open("a", encoding="utf-8") as f:
                    f.write(username + "\n")
            if webhook_url:
                send_webhook(webhook_url, username)
        else:
            invalid_counter["count"] += 1
            with print_lock:
                print(red(f"[INVALID] {username} ({status})"))

    try:
        if fast:
            max_workers = min(10, max(2, len(proxies) // 2)) if proxies else 4
            print(purple(f"[*] Fast mode: checking up to {max_workers} names at a time"))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(process_one, name): name for name in names}
                for fut in as_completed(futures):
                    try:
                        username, available, status = fut.result()
                        do_result(username, available, status)
                    except Exception as e:
                        with print_lock:
                            print(red(f"[ERROR] {futures[fut]} - {e}"))
                        invalid_counter["count"] += 1
        else:
            for username in names:
                _, available, status = process_one(username)
                do_result(username, available, status)
                time.sleep(0.3)

        print(purple("\n=== Done ==="))
        print(green(f"Valid  : {valid_counter['count']}"))
        print(red(f"Invalid: {invalid_counter['count']}"))
        print(purple(f"Valid names saved to {hits_path}"))
    finally:
        stop_event.set()
        title_thread.join(timeout=2)


def main():
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
            run_checker(fast=False)
            break
        elif choice == "3":
            run_checker(fast=True)
            break
        else:
            print(red("[!] Invalid option. Enter 1, 2, or 3."))


if __name__ == "__main__":
    main()

