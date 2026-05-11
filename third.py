from __future__ import annotations

import argparse
import functools
import http.server
import socket
import threading
import time
import webbrowser
from pathlib import Path
from socketserver import ThreadingMixIn

PROJECT_DIR = Path(__file__).resolve().parent
APP_FILE = PROJECT_DIR / "orbiter_web.html"
HOST = "127.0.0.1"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


class ThreadingHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def find_free_port(start: int = 8765, end: int = 8865, host: str = HOST) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError("Не удалось найти свободный локальный порт.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Локальный сервер Orbiter WebGL.")
    parser.add_argument("--host", default=HOST, help="Адрес локального сервера.")
    parser.add_argument("--port", type=int, help="Порт сервера. По умолчанию ищется свободный.")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Не открывать браузер автоматически.",
    )
    args = parser.parse_args(argv)

    if not APP_FILE.exists():
        print(f"Не найден файл приложения: {APP_FILE}")
        return 1

    port = args.port if args.port is not None else find_free_port(host=args.host)
    handler = functools.partial(QuietHandler, directory=str(PROJECT_DIR))
    server = ThreadingHTTPServer((args.host, port), handler)
    url = f"http://{args.host}:{port}/{APP_FILE.name}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print("WebGL-версия визуализации запущена.")
    print(f"Откройте в браузере: {url}")
    print("Для остановки сервера нажмите Ctrl+C в этом окне.")
    if not args.no_browser:
        webbrowser.open(url)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nОстанавливаю сервер...")
    finally:
        server.shutdown()
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
