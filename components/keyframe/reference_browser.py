"""On-demand FilmGrab movie search and single-frame import for ComfyUI."""
import asyncio
import hashlib
import html
import io
import json
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from aiohttp import web
from PIL import Image, PngImagePlugin
import folder_paths
from server import PromptServer

BASE = "https://film-grab.com"
_cache = {}


def _read(url, limit=8_000_000):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {"film-grab.com", "www.film-grab.com"}:
        raise ValueError("Only public FilmGrab pages and frames are supported.")
    url = urlunsplit((parsed.scheme, parsed.netloc, quote(parsed.path, safe="/%"), parsed.query, ""))
    with urlopen(Request(url, headers={"User-Agent": "dharani.prod-reference-browser/1.0"}), timeout=25) as response:
        target = urlsplit(response.url)
        if target.scheme != "https" or target.hostname not in {"film-grab.com", "www.film-grab.com"}:
            raise ValueError("Unexpected frame host.")
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("The remote response exceeds the import size limit.")
        return data


class GalleryParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.frames = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a":
            href = html.unescape(a.get("href", ""))
            self.current = href if "/wp-content/uploads/" in href and urlsplit(href).path.lower().endswith((".jpg", ".jpeg", ".png", ".webp")) else None
        if tag == "img":
            src = html.unescape(a.get("data-original") or a.get("src", ""))
            full = self.current or src
            if "/wp-content/uploads/" in full and urlsplit(full).hostname in {"film-grab.com", "www.film-grab.com"}:
                if not any(f["url"] == full for f in self.frames):
                    self.frames.append({"url": full, "thumbnail": src or full,
                                        "caption": html.unescape(a.get("alt", "Frame"))})

    def handle_endtag(self, tag):
        if tag == "a":
            self.current = None


def search_movies(query, page=1):
    query = query.strip()
    if not 2 <= len(query) <= 120 or not 1 <= page <= 50:
        raise ValueError("Enter a movie title with 2 to 120 characters.")
    params = urlencode({"search": query, "per_page": 12, "page": page,
                        "_fields": "id,title,link"})
    posts = json.loads(_read(BASE + "/wp-json/wp/v2/posts?" + params))
    return [{"id": p["id"], "title": html.unescape(p["title"]["rendered"]),
             "source": p["link"]} for p in posts]


def movie_frames(post_id):
    if not isinstance(post_id, int) or not 1 <= post_id <= 10_000_000:
        raise ValueError("Invalid movie ID.")
    cached = _cache.get(post_id)
    if cached and time.monotonic() - cached[0] < 900:
        return cached[1]
    post = json.loads(_read(f"{BASE}/wp-json/wp/v2/posts/{post_id}?_fields=id,title,link,content"))
    parser = GalleryParser()
    parser.feed(post["content"]["rendered"])
    result = {"id": post_id, "title": html.unescape(post["title"]["rendered"]),
              "source": post["link"], "frames": parser.frames[:160]}
    if len(_cache) >= 32:
        _cache.pop(next(iter(_cache)))
    _cache[post_id] = (time.monotonic(), result)
    return result


def import_frame(post_id, index):
    movie = movie_frames(post_id)
    if not isinstance(index, int) or not 0 <= index < len(movie["frames"]):
        raise ValueError("Invalid frame selection.")
    frame = movie["frames"][index]
    raw = _read(frame["url"], 20_000_000)
    with Image.open(io.BytesIO(raw)) as image:
        if image.width * image.height > 40_000_000:
            raise ValueError("Frame dimensions exceed the import limit.")
        image.load()
        digest = hashlib.sha256(raw).hexdigest()[:12]
        relative = f"MovieReferences/filmgrab_{post_id}_{index + 1:03}_{digest}.png"
        dest = Path(folder_paths.get_input_directory()) / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        meta = PngImagePlugin.PngInfo()
        meta.add_text("Source", movie["source"])
        meta.add_text("Source image", frame["url"])
        meta.add_text("Movie", movie["title"])
        if not dest.exists():
            image.convert("RGB").save(dest, pnginfo=meta)
    return {"image": relative, "title": movie["title"], "source": movie["source"]}


async def _respond(fn, *args):
    try:
        return web.json_response(await asyncio.to_thread(fn, *args))
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=400)


routes = PromptServer.instance.routes


@routes.get("/dharani-prod/reference/search")
async def search(request):
    return await _respond(search_movies, request.query.get("q", ""), int(request.query.get("page", "1")))


@routes.get("/dharani-prod/reference/frames/{post_id}")
async def frames(request):
    return await _respond(movie_frames, int(request.match_info["post_id"]))


@routes.post("/dharani-prod/reference/import")
async def select(request):
    try:
        body = await request.json()
        return await _respond(import_frame, body.get("post_id"), body.get("index"))
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=400)
