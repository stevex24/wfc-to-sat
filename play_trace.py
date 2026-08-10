#!/usr/bin/env python3
"""Launch the local HTML player for one or two CDCL traces."""

from __future__ import annotations

import argparse
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import Path
import re
import sys
import threading
import webbrowser


ASSET_DIR = Path(__file__).with_name("visualizer_web")
FRAME_NAME = re.compile(r"frame-\d{6}\.png")


class PlayerServer(ThreadingHTTPServer):
    traces: list[Path]
    export_dir: Path | None


class Handler(BaseHTTPRequestHandler):
    server: PlayerServer

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._serve_file(ASSET_DIR / "index.html")
            return
        if path.startswith("/assets/"):
            candidate = (ASSET_DIR / path.removeprefix("/assets/")).resolve()
            if candidate.parent != ASSET_DIR.resolve():
                self.send_error(404)
            else:
                self._serve_file(candidate)
            return
        if path.startswith("/trace/"):
            try:
                index = int(path.removeprefix("/trace/"))
                trace = self.server.traces[index]
            except (ValueError, IndexError):
                self.send_error(404)
                return
            try:
                data = gzip.open(trace, "rb").read() if trace.suffix == ".gz" else trace.read_bytes()
            except OSError as error:
                self.send_error(500, str(error))
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/config":
            import json
            data = json.dumps({
                "traceCount": len(self.server.traces),
                "traceNames": [item.name for item in self.server.traces],
                "exportEnabled": self.server.export_dir is not None,
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        name = self.path.removeprefix("/export/")
        if self.server.export_dir is None or not FRAME_NAME.fullmatch(name):
            self.send_error(403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400)
            return
        if length <= 0 or length > 100 * 1024 * 1024:
            self.send_error(413)
            return
        data = self.rfile.read(length)
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            self.send_error(400, "expected PNG data")
            return
        self.server.export_dir.mkdir(parents=True, exist_ok=True)
        (self.server.export_dir / name).write_bytes(data)
        self.send_response(204)
        self.end_headers()

    def _serve_file(self, path: Path) -> None:
        try:
            data = path.read_bytes()
        except OSError:
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        return


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", nargs="+", type=Path, help="one trace, or two traces to compare")
    parser.add_argument("--export-dir", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=0, type=int)
    parser.add_argument("--no-browser", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= len(args.trace) <= 2:
        print("play_trace: provide one or two traces", file=sys.stderr)
        return 2
    traces = [item.resolve() for item in args.trace]
    missing = [str(item) for item in traces if not item.is_file()]
    if missing:
        print(f"play_trace: trace not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    server = PlayerServer((args.host, args.port), Handler)
    server.traces = traces
    server.export_dir = args.export_dir.resolve() if args.export_dir else None
    url = f"http://{args.host}:{server.server_port}/"
    print(f"CDCL trace player: {url}")
    if server.export_dir:
        print(f"PNG export directory: {server.export_dir}")
    if not args.no_browser:
        threading.Timer(0.2, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
