# utils.py

import os
import datetime
from PIL import Image, ImageTk
import logging


def format_time(seconds):
    """
    Превращает количество секунд в строку формата mm:ss.
    """
    if seconds < 0:
        seconds = 0
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def load_and_resize_image(path, max_size):
    """
    Загружает изображение с диска, ресайзит его до max_size (width, height),
    возвращает объект ImageTk.PhotoImage.
    """
    try:
        if path and os.path.exists(path):
            img = Image.open(path)
            ratio = min(max_size[0] / img.width, max_size[1] / img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            return ImageTk.PhotoImage(img.resize(new_size, Image.LANCZOS))
    except Exception as e:
        logging.error(f"Error loading image {path}: {e}")
    return None


def decode_if_bytes(value):
    """
    Декодирует bytes -> str, если value является байтовой строкой.
    """
    return value.decode('utf-8') if isinstance(value, bytes) else value


def parse_date(date_str):
    """
    Парсит строку даты (ISO8601) и возвращает её в формате YYYY-MM-DD.
    """
    val = decode_if_bytes(date_str)
    try:
        return datetime.datetime.fromisoformat(val).strftime('%Y-%m-%d')
    except (ValueError, AttributeError):
        return val[:10]
