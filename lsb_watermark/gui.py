"""Small Tkinter desktop app on top of the core functions."""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import CapacityError, embed, extract, scan_folder


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("LSB Watermark")
        root.geometry("560x380")
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Watermark ID").pack(anchor="w")
        self.id_entry = ttk.Entry(frame, width=40)
        self.id_entry.pack(fill="x", pady=(0, 12))
        ttk.Button(frame, text="Mark an image...", command=self.mark).pack(fill="x", pady=3)
        ttk.Button(frame, text="Read an image...", command=self.read).pack(fill="x", pady=3)
        ttk.Button(frame, text="Search a folder...", command=self.search_folder).pack(fill="x", pady=3)
        ttk.Label(frame, text="Web page or image URL").pack(anchor="w", pady=(12, 0))
        self.url_entry = ttk.Entry(frame, width=40)
        self.url_entry.pack(fill="x")
        ttk.Button(frame, text="Search the URL", command=self.search_url).pack(fill="x", pady=3)
        self.status = ttk.Label(frame, text="")
        self.status.pack(anchor="w", pady=(12, 0))

    def _id(self):
        text = self.id_entry.get().strip()
        if not text:
            messagebox.showerror("Missing ID", "Enter a watermark ID first.")
        return text

    def mark(self):
        text = self._id()
        path = text and filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.webp")])
        if not path:
            return
        try:
            out = embed(path, text, Path(path).with_name(Path(path).stem + "_marked.png"))
            messagebox.showinfo("Saved", f"Watermarked copy saved as\n{out}")
        except (OSError, CapacityError, ValueError) as e:
            messagebox.showerror("Error", str(e))

    def read(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.webp")])
        if path:
            text = extract(path)
            messagebox.showinfo("Result", text if text is not None else "No watermark found.")

    def _run(self, label, work):
        self.status.config(text=label)

        def target():
            try:
                hits = work()
                msg = "\n".join(h.location for h in hits) or "No matching images found."
                self.root.after(0, lambda: messagebox.showinfo(f"{len(hits)} match(es)", msg))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: messagebox.showerror("Error", err))
            finally:
                self.root.after(0, lambda: self.status.config(text=""))

        threading.Thread(target=target, daemon=True).start()

    def search_folder(self):
        text = self._id()
        folder = text and filedialog.askdirectory()
        if folder:
            self._run("Searching folder...", lambda: scan_folder(folder, text))

    def search_url(self):
        from .web import scan_url

        text, url = self._id(), self.url_entry.get().strip()
        if text and url:
            self._run("Searching URL...", lambda: scan_url(url, text))


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
