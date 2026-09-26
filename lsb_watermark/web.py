"""Fetch a web page (or a direct image URL) and check every image on it, with strict size and scheme limits."""
from __future__ import annotations

import io
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import requests
from PIL import Image

from .core import Hit, extract, iter_page_images

USER_AGENT = "lsb-watermark/0.1 (+https://github.com/LeventCeliksan/lsb-watermark)"
MAX_PAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGES = 200


def _check_url(url: str) -> None:
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError(f"only http(s) URLs are allowed: {url}")


def _get(session: requests.Session, url: str, limit: int, timeout: float) -> Tuple[bytes, str]:
    _check_url(url)
    with session.get(url, timeout=timeout, stream=True, headers={"User-Agent": USER_AGENT}) as r:
        r.raise_for_status()
        declared = int(r.headers.get("content-length") or 0)
        if declared > limit:
            raise ValueError(f"response too large ({declared} bytes): {url}")
        body = bytearray()
        for chunk in r.iter_content(64 * 1024):
            body += chunk
            if len(body) > limit:
                raise ValueError(f"response too large (> {limit} bytes): {url}")
        return bytes(body), r.headers.get("content-type", "")


def _image_text(data: bytes) -> Optional[str]:
    img = Image.open(io.BytesIO(data))
    w, h = img.size
    if w * h > MAX_IMAGE_PIXELS:
        raise ValueError("image has too many pixels")
    return extract(img)


def scan_url(url: str, target: Optional[str] = None, timeout: float = 15) -> List[Hit]:
    """Scan a direct image URL, or every <img> on an HTML page (up to MAX_IMAGES)."""
    hits = []
    with requests.Session() as session:
        data, ctype = _get(session, url, MAX_IMAGE_BYTES, timeout)
        if ctype.startswith("image/"):
            candidates = [(url, data)]
        else:
            html = data[:MAX_PAGE_BYTES].decode("utf-8", errors="replace")
            candidates = []
            for i, img_url in enumerate(iter_page_images(html, url)):
                if i >= MAX_IMAGES:
                    break
                try:
                    candidates.append((img_url, _get(session, img_url, MAX_IMAGE_BYTES, timeout)[0]))
                except (requests.RequestException, ValueError):
                    continue
        for img_url, body in candidates:
            try:
                text = _image_text(body)
            except (OSError, ValueError, Image.DecompressionBombError):
                continue
            if text is not None and (target is None or text == target):
                hits.append(Hit(img_url, text))
    return hits
