from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request, sys

TARGET = "http://127.0.0.1:8000"

class Proxy(BaseHTTPRequestHandler):
    def _forward(self, method):
        content_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_len) if content_len else b''
        print(f"\n=== {method} {self.path} ===")
        print("HEADERS:")
        for k, v in self.headers.items():
            print(f"  {k}: {v}")
        if body:
            try:
                print(f"BODY: {body[:200].decode('utf-8', errors='replace')}")
            except Exception:
                print(f"BODY: {body[:200]}")
        sys.stdout.flush()
        url = TARGET + self.path
        req = urllib.request.Request(url, data=body, method=method)
        for k, v in self.headers.items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp_body = resp.read()
                self.send_response(resp.status)
                for k, v in resp.getheaders():
                    if k.lower() != 'transfer-encoding':
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp_body)
                print(f"  => {resp.status}")
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
            self.wfile.write(e.read())
            print(f"  => {e.code}")
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())
            print(f"  => ERROR: {e}")
    def do_GET(self): self._forward("GET")
    def do_POST(self): self._forward("POST")
    def do_PUT(self): self._forward("PUT")
    def do_DELETE(self): self._forward("DELETE")
    def do_PATCH(self): self._forward("PATCH")
    def log_message(self, format, *args): pass

if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 9999), Proxy)
    print("Proxy listening on 127.0.0.1:9999 ->", TARGET, flush=True)
    server.serve_forever()
