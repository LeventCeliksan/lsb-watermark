import hashlib
import http.server
import io
import threading
import time
from functools import partial

import numpy as np
import pytest
from PIL import Image

from lsb_watermark import CapacityError, capacity, embed, extract, scan_folder
from lsb_watermark.cli import main
from lsb_watermark import web


def photo(size=(320, 240), mode="RGB", seed=0):
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, (size[1], size[0], 3), dtype=np.uint8)
    img = Image.fromarray(arr, "RGB")
    return img.convert(mode) if mode != "RGB" else img


@pytest.mark.parametrize("text", ["SEALIFY-2026-000123", "Ünïcödé şğüıöç 漢字", "x" * 500])
def test_roundtrip(tmp_path, text):
    out = embed(photo(), text, tmp_path / "m.png")
    assert extract(out) == text


def test_pixels_change_by_at_most_one(tmp_path):
    src = photo()
    out = embed(src, "ID-1", tmp_path / "m.png")
    diff = np.abs(np.asarray(Image.open(out), dtype=int) - np.asarray(src, dtype=int))
    assert diff.max() <= 1


def test_alpha_is_preserved(tmp_path):
    src = photo(mode="RGBA")
    a = np.array(src)
    a[..., 3] = 77
    out = embed(Image.fromarray(a, "RGBA"), "with-alpha", tmp_path / "m.png")
    marked = Image.open(out)
    assert marked.mode == "RGBA" and np.all(np.asarray(marked)[..., 3] == 77)
    assert extract(out) == "with-alpha"


def test_no_mark_and_capacity(tmp_path):
    assert extract(photo()) is None
    tiny = photo((8, 8))
    assert capacity(tiny) == 8 * 8 * 3 // 8 - 17
    with pytest.raises(CapacityError):
        embed(tiny, "x" * 100, tmp_path / "t.png")


def test_corrupted_bit_is_rejected(tmp_path):
    out = embed(photo(), "ID-42", tmp_path / "m.png")
    arr = np.array(Image.open(out))
    flat = arr.reshape(-1)
    flat[9 * 8 + 3] ^= 1  # flip one payload bit
    assert extract(Image.fromarray(arr)) is None


def test_jpeg_destroys_the_mark(tmp_path):
    out = embed(photo(), "ID-7", tmp_path / "m.png")
    buf = io.BytesIO()
    Image.open(out).save(buf, "JPEG", quality=95)
    assert extract(Image.open(io.BytesIO(buf.getvalue()))) is None


def test_reads_marks_from_the_earlier_desktop_tool():
    code = "ABC123"
    payload = f"###START###{code}###HASH###{hashlib.sha256(code.encode()).hexdigest()[:16]}###END###"
    bits = np.array([int(b) for ch in payload for b in format(ord(ch), "08b")], dtype=np.uint8)
    arr = np.array(photo())
    flat = arr.reshape(-1)
    flat[:bits.size] = (flat[:bits.size] & 0xFE) | bits
    assert extract(Image.fromarray(arr)) == code


def test_large_image_is_fast(tmp_path):
    big = photo((4000, 3000))
    out = embed(big, "BIG", tmp_path / "big.png")
    t = time.perf_counter()
    assert extract(out) == "BIG"
    assert time.perf_counter() - t < 3


def test_scan_folder(tmp_path):
    (tmp_path / "sub").mkdir()
    embed(photo(seed=1), "OWNER-A", tmp_path / "a.png")
    embed(photo(seed=2), "OWNER-B", tmp_path / "sub" / "b.png")
    photo(seed=3).save(tmp_path / "plain.png")
    (tmp_path / "broken.png").write_bytes(b"not an image")
    assert [h.text for h in scan_folder(tmp_path)] == ["OWNER-A", "OWNER-B"]
    assert [h.location.endswith("b.png") for h in scan_folder(tmp_path, "OWNER-B")] == [True]


@pytest.fixture
def site(tmp_path):
    embed(photo(seed=5), "SITE-ID", tmp_path / "marked.png")
    photo(seed=6).save(tmp_path / "plain.png")
    (tmp_path / "index.html").write_text(
        '<html><body><img src="marked.png"><img src="/plain.png"><img src="missing.png"><img src="data:x"></body></html>')
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    handler.log_message = lambda *a: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_scan_web_page(site):
    hits = web.scan_url(site + "/index.html")
    assert [(h.text, h.location.endswith("marked.png")) for h in hits] == [("SITE-ID", True)]
    assert web.scan_url(site + "/index.html", "OTHER") == []


def test_scan_direct_image_url(site):
    assert [h.text for h in web.scan_url(site + "/marked.png")] == ["SITE-ID"]


def test_web_limits(site, monkeypatch):
    with pytest.raises(ValueError):
        web.scan_url("file:///etc/passwd")
    monkeypatch.setattr(web, "MAX_IMAGE_BYTES", 1000)
    with pytest.raises(ValueError):
        web.scan_url(site + "/marked.png")  # oversized response is refused


def test_cli(tmp_path, capsys):
    src = tmp_path / "in.jpg"
    photo().save(src, "JPEG")
    assert main(["embed", str(src), "CLI-ID"]) == 0
    marked = tmp_path / "in_marked.png"
    assert marked.exists()
    assert main(["extract", str(marked)]) == 0 and "CLI-ID" in capsys.readouterr().out
    assert main(["extract", str(src)]) == 1
    assert main(["scan-folder", str(tmp_path), "--id", "CLI-ID"]) == 0
    assert main(["embed", str(tmp_path / "missing.png"), "x"]) == 2
