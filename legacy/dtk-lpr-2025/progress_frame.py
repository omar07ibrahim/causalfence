# progress_frame.py

import tkinter as tk
from tkinter import ttk
import os

from database import DB
from utils import format_time


class ProgressFrame(ttk.Frame):
    """
    Фрейм для отображения списка обрабатываемых видео, их прогресса и общей статистики.
    """
    def __init__(self, master):
        super().__init__(master)
        self.video_statuses = {}
        self.db = DB()
        self.setup_ui()

    def setup_ui(self):
        """
        Создает элементы интерфейса: общий статус, прогресс-бар, скроллируемый список видео.
        """
        self.status_frame = ttk.Frame(self)
        self.status_frame.pack(fill=tk.X, pady=(0, 5))

        self.stats_frame = ttk.Frame(self.status_frame)
        self.stats_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.total_label = ttk.Label(self.stats_frame, text="Total: 0")
        self.total_label.pack(side=tk.LEFT, padx=5)

        self.processed_label = ttk.Label(self.stats_frame, text="Processed: 0")
        self.processed_label.pack(side=tk.LEFT, padx=5)

        self.plates_found_label = ttk.Label(self.stats_frame, text="Plates Found: 0")
        self.plates_found_label.pack(side=tk.LEFT, padx=5)

        self.blacklist_label = ttk.Label(self.stats_frame, text="⚠️ Blacklisted: 0", foreground='red')
        self.blacklist_label.pack(side=tk.LEFT, padx=5)

        self.progress_frame = ttk.Frame(self)
        self.progress_frame.pack(fill=tk.X, pady=(0, 5))

        self.progress = ttk.Progressbar(self.progress_frame, mode='determinate')
        self.progress.pack(fill=tk.X)

        self.videos_frame = ttk.Frame(self)
        self.videos_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.videos_frame)
        self.scrollbar = ttk.Scrollbar(self.videos_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind("<Configure>",
                                   lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Прокрутка колесом мыши
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        """
        Вертикальная прокрутка содержимого canvas при скролле колёсиком мыши.
        """
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def update_progress(self, processed, total, plates_found=0, blacklisted=0):
        """
        Обновляет суммарную статистику (количество видео, обработанных, найденных номеров и т.д.).
        """
        self.total_label.config(text=f"Total: {total}")
        self.processed_label.config(text=f"Processed: {processed}")
        self.plates_found_label.config(text=f"Plates Found: {plates_found}")
        self.blacklist_label.config(text=f"⚠️ Blacklisted: {blacklisted}")

        if total > 0:
            progress_val = (processed / total) * 100
            self.progress['value'] = progress_val

    def clear_videos(self):
        """
        Очищает список видео и сбрасывает общий прогресс.
        """
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.video_statuses.clear()
        self.progress['value'] = 0
        self.update_progress(0, 0, 0, 0)

    def add_video(self, video_path, video_duration=0):
        """
        Добавляет новый элемент (строчку) в список видео с прогрессом.
        """
        frame = ttk.Frame(self.scrollable_frame)
        frame.pack(fill=tk.X, padx=5, pady=2)

        name_label = ttk.Label(frame, text=os.path.basename(video_path))
        name_label.pack(side=tk.LEFT)

        progress = ttk.Progressbar(frame, mode='determinate', length=100)
        progress.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        time_label = ttk.Label(frame, text=f"0:00 / {format_time(video_duration)}")
        time_label.pack(side=tk.LEFT, padx=5)

        status_label = ttk.Label(frame, text="Queued")
        status_label.pack(side=tk.RIGHT, padx=5)

        self.video_statuses[video_path] = {
            'frame': frame,
            'name_label': name_label,
            'progress': progress,
            'time_label': time_label,
            'status_label': status_label,
            'duration': video_duration,
            'start_time': None
        }
        return self.video_statuses[video_path]

    def update_video_progress(self, video_path, progress_value, current_time=None, status=None):
        """
        Обновляет прогресс (и метку времени, и статус) для конкретного видео.
        """
        if video_path in self.video_statuses:
            vs = self.video_statuses[video_path]
            vs['progress']['value'] = progress_value

            if current_time is not None:
                vs['time_label'].config(text=f"{format_time(current_time)} / {format_time(vs['duration'])}")

            if status:
                vs['status_label'].config(text=status)
                if "Blacklisted" in status:
                    vs['status_label'].config(foreground='red')

    def show_blacklist_alert(self, plate_text, reason):
        """
        Показывает всплывающее окно предупреждения, если номер найден в blacklist.
        """
        alert_window = tk.Toplevel(self)
        alert_window.title("⚠️ BLACKLIST ALERT!")
        alert_window.geometry("400x200")

        style = ttk.Style()
        style.configure('Alert.TLabel', foreground='red', font=('Helvetica', 12, 'bold'))

        ttk.Label(alert_window, text="⚠️ BLACKLISTED PLATE DETECTED! ⚠️", style='Alert.TLabel').pack(pady=10)
        ttk.Label(alert_window, text=f"Plate Number: {plate_text}", font=('Helvetica', 11)).pack(pady=5)
        ttk.Label(alert_window, text=f"Reason: {reason}", font=('Helvetica', 11)).pack(pady=5)

        # Звуковое оповещение, если включено в настройках
        if self.db.get_setting('alert_sound', True):
            alert_window.bell()

        def close_alert():
            alert_window.destroy()

        ttk.Button(alert_window, text="Acknowledge", command=close_alert).pack(pady=10)

        alert_window.transient(self)
        alert_window.grab_set()

        # Центрируем окно относительно родителя
        x = self.winfo_x() + (self.winfo_width() - alert_window.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - alert_window.winfo_height()) // 2
        alert_window.geometry(f"+{x}+{y}")
