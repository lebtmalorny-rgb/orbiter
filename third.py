from __future__ import annotations

import argparse
import functools
import http.server
import json
import socket
import threading
import time
import webbrowser
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

PROJECT_DIR = Path(__file__).resolve().parent
APP_FILE = PROJECT_DIR / "orbiter_web.html"
HOST = "127.0.0.1"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/realtime/catalog":
            self._handle_realtime_catalog(parsed.query)
            return
        if parsed.path == "/api/realtime/trajectory":
            self._handle_realtime_trajectory(parsed.query)
            return
        super().do_GET()

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, error: Exception) -> None:
        self._send_json(status, {"error": type(error).__name__, "message": str(error)})

    def _handle_realtime_catalog(self, query: str) -> None:
        try:
            from orbiter.realtime import catalog_summary, load_celestrak_omm_json

            params = parse_qs(query)
            group = params.get("group", ["STATIONS"])[0]
            elements = load_celestrak_omm_json("GROUP", group)
            self._send_json(200, {"group": group.upper(), "satellites": catalog_summary(elements)})
        except Exception as error:
            self._send_error(500, error)

    def _handle_realtime_trajectory(self, query: str) -> None:
        try:
            from orbiter.realtime import (
                catalog_summary,
                load_celestrak_omm_json,
                sample_realtime_trajectory,
                select_omm_element,
                trajectory_to_json,
            )

            params = parse_qs(query)
            group = params.get("group", ["STATIONS"])[0]
            satellite_query = params.get("query", ["ISS"])[0]
            catnr = params.get("catnr", [""])[0].strip()
            duration_min = min(max(float(params.get("duration_min", ["180"])[0]), 1.0), 1440.0)
            step_seconds = min(max(float(params.get("step_seconds", ["20"])[0]), 1.0), 600.0)

            if catnr:
                elements = load_celestrak_omm_json("CATNR", catnr)
                element = elements[0] if elements else None
                source_label = f"CATNR {catnr}"
            else:
                elements = load_celestrak_omm_json("GROUP", group)
                element = select_omm_element(elements, satellite_query)
                source_label = f"group {group!r}"

            if element is None:
                suggestions = catalog_summary(elements[:5])
                self._send_json(
                    404,
                    {
                        "error": "SatelliteNotFound",
                        "message": f"No satellite matching {satellite_query!r} in {source_label}.",
                        "suggestions": suggestions,
                    },
                )
                return

            samples = sample_realtime_trajectory(
                element,
                duration_min=duration_min,
                step_seconds=step_seconds,
            )
            self._send_json(200, trajectory_to_json(element, samples))
        except Exception as error:
            self._send_error(500, error)


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
