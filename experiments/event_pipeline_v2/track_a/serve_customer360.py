"""Local-only Customer 360 server. No customer data is bundled with the UI."""
import argparse
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from track_a.customer360 import CustomerStore


STATIC = Path(__file__).with_name("customer360_ui")


def handler_for(store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Avoid logging customer IDs / queries.
            pass

        def send(self, status, body, content_type="application/json; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def json(self, status, value):
            self.send(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))

        def do_GET(self):
            expected = f"127.0.0.1:{self.server.server_port}"
            host = self.headers.get("Host", "")
            if host not in {expected, f"localhost:{self.server.server_port}"}:
                return self.json(403, {"error": "Localhost access only"})
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://{expected}", f"http://localhost:{self.server.server_port}"}:
                return self.json(403, {"error": "Cross-origin access denied"})
            url = urlparse(self.path)
            args = parse_qs(url.query)
            try:
                month = args.get("month", [store.months[-1]])[0]
                if url.path == "/api/meta":
                    return self.json(200, dict(**store.metadata(), examples=store.examples(store.months[-1])))
                if url.path == "/api/customers":
                    query = args.get("q", [""])[0]
                    if not query.isascii() or not query.isdigit() or len(query) > 12:
                        raise ValueError("Nhập mã khách bằng chữ số (tối đa 12 ký tự)")
                    return self.json(200, store.search(query, month))
                if url.path == "/api/profile":
                    raw_id = args.get("id", [""])[0]
                    if not raw_id.isascii() or not raw_id.isdigit() or len(raw_id) > 12:
                        raise ValueError("Mã khách không hợp lệ")
                    return self.json(200, store.profile(int(raw_id), month, int(args.get("window", ["6"])[0])))
                assets = {"/": ("index.html", "text/html; charset=utf-8"),
                          "/app.js": ("app.js", "application/javascript; charset=utf-8"),
                          "/style.css": ("style.css", "text/css; charset=utf-8")}
                if url.path not in assets:
                    return self.json(404, {"error": "Không tìm thấy"})
                name, content_type = assets[url.path]
                return self.send(200, (STATIC / name).read_bytes(), content_type)
            except ValueError as exc:
                return self.json(400, {"error": str(exc)})
            except KeyError:
                return self.json(404, {"error": "Khách chưa xuất hiện tính đến tháng đã chọn"})
            except Exception:
                logging.exception("Customer 360 request failed")
                return self.json(500, {"error": "Không đọc được hồ sơ; kiểm tra log server"})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--track-a-run", required=True)
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Use a port between 1024 and 65535")
    print("Checking source provenance and loading customer history...", flush=True)
    store = CustomerStore.load(args.source_run, args.cache_dir, args.track_a_run)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(store))
    server.daemon_threads = True
    print(f"Customer 360 ready: http://127.0.0.1:{args.port} ({store.metadata()['customer_count']} customers)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
