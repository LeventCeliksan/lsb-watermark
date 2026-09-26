"""Embed a short ID in the least significant bits of an image, read it back, and search folders or web pages for it.

Payload layout, written into the lowest bit of each R, G, B value in pixel order:
    b"LSBW" | version (1 byte) | length (4 bytes, big-endian) | UTF-8 text | SHA-256(text)[:8]
"""
from __future__ import annotations

import hashlib
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Union

import numpy as np
from PIL import Image

MAGIC = b"LSBW"
VERSION = 1
HEADER = struct.Struct(">4sBI")
CHECKSUM_BYTES = 8
IMAGE_EXTS = (".png", ".bmp", ".tif", ".tiff", ".webp", ".jpg", ".jpeg")
LEGACY_START, LEGACY_HASH, LEGACY_END = "###START###", "###HASH###", "###END###"

ImageLike = Union[str, os.PathLike, Image.Image]


class CapacityError(ValueError):
    pass


def _open(image: ImageLike) -> Image.Image:
    return image if isinstance(image, Image.Image) else Image.open(image)


def _channels(img: Image.Image) -> np.ndarray:
    """RGB values in pixel order as a flat uint8 array (alpha, if any, is left untouched elsewhere)."""
    return np.asarray(img.convert("RGB"), dtype=np.uint8).reshape(-1)


def capacity(image: ImageLike) -> int:
    """Maximum text length in bytes that fits in the image."""
    w, h = _open(image).size
    return (w * h * 3) // 8 - HEADER.size - CHECKSUM_BYTES


def embed(image: ImageLike, text: str, out_path) -> Path:
    """Write `text` into the image and save it losslessly as PNG (JPEG would destroy the bits)."""
    if not text:
        raise ValueError("text is empty")
    img = _open(image)
    data = text.encode("utf-8")
    payload = HEADER.pack(MAGIC, VERSION, len(data)) + data + hashlib.sha256(data).digest()[:CHECKSUM_BYTES]
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    rgba = np.array(img.convert("RGBA" if has_alpha else "RGB"), dtype=np.uint8)
    rgb = np.ascontiguousarray(rgba[..., :3])
    flat = rgb.reshape(-1)
    bits = np.unpackbits(np.frombuffer(payload, dtype=np.uint8))
    if bits.size > flat.size:
        raise CapacityError(f"image too small: needs {bits.size} bits, has {flat.size}")
    flat[:bits.size] = (flat[:bits.size] & 0xFE) | bits
    rgba[..., :3] = rgb
    out_path = Path(out_path).with_suffix(".png")
    Image.fromarray(rgba).save(out_path, "PNG")  # mode follows the array shape
    return out_path


def _read_bytes(flat: np.ndarray, start_byte: int, count: int) -> bytes:
    lo, hi = start_byte * 8, (start_byte + count) * 8
    if hi > flat.size:
        raise EOFError
    return np.packbits(flat[lo:hi] & 1).tobytes()


def _extract_legacy(flat: np.ndarray, max_chars: int = 4096) -> Optional[str]:
    """Format of the earlier desktop tool: ###START###text###HASH###sha256[:16]###END###, one byte per char."""
    head = np.packbits(flat[: min(flat.size, max_chars * 8)] & 1).tobytes().decode("latin-1")
    if not head.startswith(LEGACY_START) or LEGACY_END not in head:
        return None
    body = head[len(LEGACY_START): head.index(LEGACY_END)]
    text, sep, digest = body.partition(LEGACY_HASH)
    if sep and hashlib.sha256(text.encode("latin-1")).hexdigest()[:16] == digest:
        return text
    return None


def extract(image: ImageLike) -> Optional[str]:
    """Return the embedded text, or None if there is none or the checksum does not match."""
    flat = _channels(_open(image))
    try:
        magic, version, length = HEADER.unpack(_read_bytes(flat, 0, HEADER.size))
    except EOFError:
        return None
    if magic != MAGIC:
        return _extract_legacy(flat)
    if version != VERSION or length > flat.size // 8:
        return None
    try:
        data = _read_bytes(flat, HEADER.size, length)
        checksum = _read_bytes(flat, HEADER.size + length, CHECKSUM_BYTES)
    except EOFError:
        return None
    if hashlib.sha256(data).digest()[:CHECKSUM_BYTES] != checksum:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


@dataclass
class Hit:
    location: str
    text: str


def scan_folder(folder, target: Optional[str] = None) -> List[Hit]:
    """Every image under `folder` carrying a watermark (only those equal to `target`, if given)."""
    hits = []
    for path in sorted(Path(folder).rglob("*")):
        if path.suffix.lower() not in IMAGE_EXTS or not path.is_file():
            continue
        try:
            text = extract(path)
        except (OSError, ValueError, Image.DecompressionBombError):
            continue
        if text is not None and (target is None or text == target):
            hits.append(Hit(str(path), text))
    return hits


def iter_page_images(html: str, base_url: str) -> Iterable[str]:
    from urllib.parse import urljoin

    from bs4 import BeautifulSoup

    seen = set()
    for tag in BeautifulSoup(html, "html.parser").find_all("img"):
        src = tag.get("src")
        if src and not src.startswith("data:"):
            url = urljoin(base_url, src)
            if url not in seen:
                seen.add(url)
                yield url
