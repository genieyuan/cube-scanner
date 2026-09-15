#!/usr/bin/env python3
"""colour_reader.py — the one server the 2x2 Cube Scanner needs.

POST /api/colours  {"images": [<base64 jpeg grid>], "grid": {"cols", "rows", "count"}, "kind": "faces"|"pair", "mirrored": bool}
                -> {"ok": true, "reads": [["W","R","G","B"], ...], "meta": {...}}

The browser lays the photographs out as ONE grid image and asks a vision model to read the four
sticker colours of each tile. The model is never asked a geometry question: which photo is which
face, and how the cube was turned, are decided in the browser, where they can be checked.

Set GEMINI_API_KEY in the environment. The key never reaches the browser.
Run:  GEMINI_API_KEY=... python3 colour_reader.py   (listens on 127.0.0.1:8901; put it behind your https server as /api/colours)
Python 3.9+, standard library only.
"""
import datetime, json, os, re, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

GRID_PROMPT = """This single image is a grid of %d photographs of the SAME real 2x2 Rubik's
cube, laid out %d across and %d down, in order reading left to right then down. (Any leftover
cells at the end are blank and should be ignored.) Each photograph shows one side of the cube
held square-on to the camera.

Your only job is to read colours. Do NOT work out which side of the cube each photograph shows,
and do NOT work out how the cube was turned between them. That is handled elsewhere.

For each of the %d photographs in order, give the four sticker colours of that side, in the
order top-left, top-right, bottom-left, bottom-right AS THEY APPEAR IN THE PHOTOGRAPH.
Each colour is exactly one of: white, yellow, red, orange, green, blue.

Two warnings about this cube specifically:
- the lighting is often warm, so white looks cream and red can look orange. Across the whole
  cube there are exactly 4 stickers of each of the six colours, which helps separate the red
  family from the orange family.
- some stickers carry a printed logo. Judge the sticker's colour, not the logo's.

Reply with ONLY a fenced json block:

```json
{"moments": [["..","..","..",".."], ... %d entries in order ... ]}
```"""


MIRROR_NOTE = """

IMPORTANT: the camera that took these photographs MIRRORS the scene, so each photograph is a
left-to-right mirror image of the real cube. Report the colours as they are ON THE REAL CUBE,
not as they appear in the photograph. In practice that means reading each row RIGHT TO LEFT:
the sticker on the right of the photograph is the one on the left of the real cube.
So give me: real-top-left, real-top-right, real-bottom-left, real-bottom-right."""

PAIR_PROMPT = """This single image shows TWO photographs of the same real 2x2 Rubik's cube,
side by side. LEFT was taken earlier; RIGHT was taken just now. They are meant to be the SAME
side of the cube, photographed twice.

Read the four sticker colours of each, in the order top-left, top-right, bottom-left,
bottom-right as they appear in that photograph. Each colour is exactly one of: white, yellow,
red, orange, green, blue. Judge the sticker colour, not any printed logo.

Do not try to decide whether they ought to match. Just report what each one shows.

Reply with ONLY a fenced json block:

```json
{"moments": [["..","..","..",".."],["..","..","..",".."]]}
```"""

def gemini_colours(images, grid=None, kind="faces", mirrored=False):
    """One image that is a GRID of `count` photographs -> that many 4-colour readings.

    Sending the photographs separately costs 10,066 prompt tokens and ~4s; the same
    set as one grid costs 1,354 and ~1.6s, with an identical reading. Measured over
    five runs, correct every time. A child is not going to wait four seconds.
    """
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("set GEMINI_API_KEY in the environment")
    if grid:
        count = int(grid.get("count") or 0)
        cols = int(grid.get("cols") or 1)
        rows = int(grid.get("rows") or 1)
        if kind == "pair":
            text = PAIR_PROMPT
        else:
            text = GRID_PROMPT % (count, cols, rows, count, count)
    else:
        count = len(images)
        text = GRID_PROMPT % (count, count, 1, count, count)
    # the maintainer's idea, and a better one than transforming the answer afterwards: if the camera
    # mirrors, say so and let the reader account for it. Flipping the result ourselves meant
    # guessing WHICH flip, and we guessed wrong three times.
    if mirrored:
        text += MIRROR_NOTE
    parts = [{"text": text}]
    for b64 in images:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
    # Measured on this exact task: letting it think costs 4x the wall clock and changes
    # nothing. 12.3s with default thinking, 3.1s with none, same nine readings both times.
    # Reading a sticker's colour is perception, not deliberation.
    body = json.dumps({"contents": [{"parts": parts}],
                       "generationConfig": {"temperature": 0, "maxOutputTokens": 65536,
                                            "thinkingConfig": {"thinkingBudget": 0}}}).encode()
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % GEMINI_MODEL,
        data=body, method="POST")
    req.add_header("x-goog-api-key", key)          # header, never the URL
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.load(r)
    text = "".join(pt.get("text", "")
                   for c in out.get("candidates", [])
                   for pt in c.get("content", {}).get("parts", []))
    m = re.findall(r"```json\s*(.*?)```", text, re.S)
    if not m:
        m = re.findall(r"(\{[^{}]*\"moments\".*?\})", text, re.S)
    if not m:
        raise ValueError("the model did not return a json block")
    L = {"white":"W","yellow":"Y","red":"R","orange":"O","green":"G","blue":"B"}
    got = []
    for q in json.loads(m[-1])["moments"]:
        if len(q) != 4:
            raise ValueError("expected 4 colours per face, got %d" % len(q))
        got.append([L[str(c).strip().lower()] for c in q])
    u = out.get("usageMetadata", {})
    return got, {"model": GEMINI_MODEL, "mirrored": bool(mirrored),
                 "promptTokens": u.get("promptTokenCount"),
                 "thinkingTokens": u.get("thoughtsTokenCount"),
                 "answerTokens": u.get("candidatesTokenCount")}


class H(BaseHTTPRequestHandler):
    server_version = "colour-reader/1.0"

    def _say(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.rstrip("/").endswith("colours"):
            return self.do_colours()
        return self._say(404, {"error": "POST /api/colours"})

    def do_colours(self):
        """{"images": [<base64 jpeg>, ...]} -> {"reads": [["B","O","Y","B"], ...]}"""
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._say(400, {"error": "bad length"})
        if n <= 0 or n > 24 * 1024 * 1024:
            return self._say(413, {"error": "0 < size <= 24MB required"})
        try:
            payload = json.loads(self.rfile.read(n))
            images = payload["images"]
            grid = payload.get("grid")
            kind = payload.get("kind", "faces")
            mirrored = bool(payload.get("mirrored"))
        except Exception as e:
            return self._say(400, {"error": "bad payload: %s" % e})
        if not isinstance(images, list) or not (1 <= len(images) <= 20):
            return self._say(400, {"error": "between 1 and 20 images required"})
        if grid and not (2 <= int(grid.get("count") or 0) <= 20):
            return self._say(400, {"error": "grid count must be between 2 and 20"})
        t0 = datetime.datetime.now()
        try:
            reads, meta = gemini_colours(images, grid, kind, mirrored)
        except urllib.error.HTTPError as e:
            return self._say(502, {"error": "model rejected the request: HTTP %s" % e.code})
        except Exception as e:
            return self._say(502, {"error": str(e)})
        meta["seconds"] = round((datetime.datetime.now() - t0).total_seconds(), 1)
        want = int(grid.get("count")) if grid else len(images)
        if len(reads) != want:
            return self._say(502, {"error": "asked about %d photos, got %d back"
                                            % (want, len(reads))})
        return self._say(200, {"ok": True, "reads": reads, "meta": meta})


    def log_message(self, fmt, *a):
        print("%s %s" % (self.log_date_time_string(), fmt % a), flush=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8901"))
    print("colour reader on 127.0.0.1:%d (model %s)" % (port, GEMINI_MODEL), flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
