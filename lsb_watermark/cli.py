"""lsb-watermark CLI: embed | extract | scan-folder | scan-url."""
import argparse
import sys
from pathlib import Path

from .core import CapacityError, embed, extract, scan_folder


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="lsb-watermark", description="Invisible LSB watermark IDs for images.")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("embed", help="write an ID into an image (saved as PNG)")
    e.add_argument("image", type=Path)
    e.add_argument("text")
    e.add_argument("-o", "--out", type=Path, help="output file (default: <name>_marked.png)")
    x = sub.add_parser("extract", help="read the ID from an image")
    x.add_argument("image", type=Path)
    f = sub.add_parser("scan-folder", help="find marked images in a folder tree")
    f.add_argument("folder", type=Path)
    f.add_argument("--id", dest="target")
    u = sub.add_parser("scan-url", help="find marked images on a web page or at an image URL")
    u.add_argument("url")
    u.add_argument("--id", dest="target")
    a = p.parse_args(argv)

    try:
        if a.cmd == "embed":
            out = embed(a.image, a.text, a.out or a.image.with_name(a.image.stem + "_marked.png"))
            print(f"saved {out}")
        elif a.cmd == "extract":
            text = extract(a.image)
            if text is None:
                print("no watermark found")
                return 1
            print(text)
        else:
            if a.cmd == "scan-folder":
                hits = scan_folder(a.folder, a.target)
            else:
                from .web import scan_url

                hits = scan_url(a.url, a.target)
            for h in hits:
                print(f"{h.text}\t{h.location}")
            print(f"{len(hits)} marked image(s)")
            return 0 if hits else 1
    except (OSError, ValueError, CapacityError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 2
    except Exception as err:  # network errors from requests
        print(f"Error: {type(err).__name__}: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
