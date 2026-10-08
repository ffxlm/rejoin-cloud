#!/usr/bin/env python3
"""
local_listener.py — listener สำหรับเทสต์ Phase 0 (รันบน PC)

ใช้คู่กับ:  adb reverse tcp:8787 tcp:8787
จากนั้น Lua ที่ยิงไป http://127.0.0.1:8787/... บนมือถือ จะมาถึง listener นี้

รัน:
    python3 phase0/local_listener.py 8787
"""
import datetime
import http.server
import sys


class Handler(http.server.BaseHTTPRequestHandler):
    def _handle(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        now = datetime.datetime.now().isoformat(timespec="seconds")
        print(f"[{now}] {self.command} {self.path}")
        for k, v in self.headers.items():
            print(f"    {k}: {v}")
        if body:
            print(f"    BODY: {body.decode('utf-8', 'replace')}")
        print("-" * 60, flush=True)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def log_message(self, *args):
        pass  # ปิด log ดีฟอลต์ ใช้ของเราเอง


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    print(f"listening on 127.0.0.1:{port}  (Ctrl+C เพื่อหยุด)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
