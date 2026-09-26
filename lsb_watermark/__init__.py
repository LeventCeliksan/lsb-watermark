"""Invisible LSB watermark IDs: embed, extract, and search folders or web pages."""
from .core import CapacityError, Hit, capacity, embed, extract, scan_folder

__all__ = ["embed", "extract", "capacity", "scan_folder", "Hit", "CapacityError"]
