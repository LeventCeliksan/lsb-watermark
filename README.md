# lsb-watermark

Hide a short ID (an owner code, asset number or customer reference) inside an image's pixels, read it back with a checksum, and **search a folder tree or a web page for images that carry it**.

The ID goes into the least significant bit of each red, green and blue value, so every pixel changes by at most 1 and the image looks identical. A tiny header and a SHA-256 checksum make sure random images never produce false matches.

## Be aware
- **This is a watermark, not encryption.** Anyone who knows the format can read the ID. Do not store secrets in it.
- **Lossless formats only.** Saving as JPEG, resizing or re-encoding on social platforms destroys the mark. Output is always PNG. For marks that survive recompression you need frequency-domain or learned watermarking.

## Install
```bash
pip install git+https://github.com/LeventCeliksan/lsb-watermark
```

## Usage
```bash
lsb-watermark embed photo.jpg "ACME-2026-00042"      # -> photo_marked.png
lsb-watermark extract photo_marked.png                # ACME-2026-00042
lsb-watermark scan-folder ~/Pictures --id ACME-2026-00042
lsb-watermark scan-url https://example.com/gallery --id ACME-2026-00042
lsb-watermark-gui                                     # small desktop app (needs Tk)
```
```python
from lsb_watermark import embed, extract, scan_folder
embed("photo.jpg", "ACME-2026-00042", "photo_marked.png")
assert extract("photo_marked.png") == "ACME-2026-00042"
```

## Format
`b"LSBW"` · version (1 byte) · length (4 bytes, big-endian) · UTF-8 text · first 8 bytes of SHA-256(text), written bit by bit into R, G, B in pixel order. Any Unicode text works; a 1000x1000 image holds about 375 KB. Alpha channels are kept as they are.

Marks made by the earlier version of this tool (`###START###...###END###` format) are still recognized.

## Safety limits for web scans
Only `http`/`https` URLs, at most 200 images per page, 20 MB per download (checked while streaming), 40 megapixels per image, and a descriptive User-Agent.

## Tests
```bash
pip install -e ".[test]"
pytest
```
15 tests: round trips including non-Latin text, pixel changes of at most 1, alpha preservation, capacity limits, a flipped bit being rejected, JPEG destroying the mark, reading the legacy format, a 12-megapixel image in under 3 seconds, folder scanning past broken files, and web scanning against a local HTTP server, including the size and scheme limits. Tested on Python 3.9 and 3.14.

## License
MIT
