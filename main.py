# main.py

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import logging
import threading

from database import DB
from processing_manager import VideoProcessingManager
from report_panel import ReportPanel
from settings_dialog import SettingsDialog
from progress_frame import ProgressFrame
from constants import MAX_CONCURRENT_STREAMS

# Добавляем в PATH путь к нужным DLL (DTKLPR5, DTKVID)
os.environ['PATH'] = '../../lib/windows/x64/' + os.pathsep + os.environ['PATH']

# Настройка логгирования (для отладки можно изменить уровень)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class MainApp:
    """
    Основное приложение с интерфейсом на Tkinter.
    """
    def __init__(self, root):
        self.root = root
        self.root.title("LPR System")
        self.db = DB()
        self.profile = None
        self.processing_manager = None
        self.setup_ui()

    def setup_ui(self):
        """
        Создание всех элементов интерфейса (кнопки, фреймы и т.д.).
        """
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Верхняя панель (toolbar) с кнопками
        toolbar = ttk.Frame(self.main_frame)
        toolbar.pack(fill=tk.X, pady=5)

        button_info = [
            ("Select Profile", self.select_profile),
            ("Select Videos/Folder", self.select_input),
            ("Show Report", self.show_report),
            ("Settings", self.open_settings),
        ]
        for txt, cmd in button_info:
            ttk.Button(toolbar, text=txt, command=cmd).pack(side=tk.LEFT, padx=2)

        self.profile_label = ttk.Label(toolbar, text="No profile selected")
        self.profile_label.pack(side=tk.RIGHT, padx=5)

        # Фрейм с прогресс-барами и статистикой по текущей обработке
        self.progress_frame = ProgressFrame(self.main_frame)
        self.progress_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # Статус-бар (строка состояния)
        self.status_var = tk.StringVar()
        self.status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, padding=(2, 2))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def select_profile(self):
        """
        Окно выбора (или создания) профиля из имеющихся в базе.
        """
        profiles = self.db.get_profiles()
        if not profiles:
            if messagebox.askyesno("No Profiles", "No profiles exist. Would you like to create one?"):
                self.create_profile()
            return

        profile_var = tk.StringVar(value=profiles[0])
        dialog = tk.Toplevel(self.root)
        dialog.title("Select Profile")
        dialog.geometry("300x150")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Select a profile:", padding=10).pack()
        cb = ttk.Combobox(dialog, textvariable=profile_var, values=profiles, width=30)
        cb.pack(padx=10, pady=5)

        def on_select():
            self.profile = profile_var.get()
            self.profile_label.config(text=f"Profile: {self.profile}")
            self.status_var.set(f"Selected profile: {self.profile}")
            dialog.destroy()

        ttk.Button(dialog, text="Select", command=on_select).pack(pady=10)

    def select_input(self):
        """
        Окно выбора либо папки, либо отдельных видеофайлов для последующей обработки.
        """
        if not self.profile:
            messagebox.showwarning("Warning", "Please select a profile first")
            return

        # Всплывающее окно для выбора входных данных
        input_dialog = tk.Toplevel(self.root)
        input_dialog.title("Select Input")
        input_dialog.geometry("300x150")
        input_dialog.transient(self.root)
        input_dialog.grab_set()

        def select_folder():
            dir_path = filedialog.askdirectory(title="Select Video Folder")
            if dir_path:
                self.progress_frame.clear_videos()
                self.process_videos(dir_path)
                self.status_var.set(f"Processing videos from {dir_path}...")
            input_dialog.destroy()

        def select_files():
            file_paths = filedialog.askopenfilenames(
                title="Select Video Files",
                filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv *.flv *.wmv *.mpeg")]
            )
            if file_paths:
                self.progress_frame.clear_videos()
                self.process_videos(file_paths)
                self.status_var.set("Processing selected video files...")
            input_dialog.destroy()

        ttk.Button(input_dialog, text="Select Folder", command=select_folder).pack(pady=20)
        ttk.Button(input_dialog, text="Select Files", command=select_files).pack(pady=10)

    def process_videos(self, input_paths):
        """
        Создает VideoProcessingManager и добавляет в очередь все выбранные видеофайлы.
        Запускает поток, который обрабатывает все видео (с учётом MAX_CONCURRENT_STREAMS).
        """
        self.processing_manager = VideoProcessingManager(self.profile, self.progress_frame)

        if isinstance(input_paths, str):
            # Обработка папки
            for root, _, files in os.walk(input_paths):
                for file in files:
                    if file.lower().endswith((".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".mpeg")):
                        self.processing_manager.add_video(os.path.join(root, file))
        else:
            # Обработка списка файлов
            for file_path in input_paths:
                self.processing_manager.add_video(file_path)

        # Запуск в отдельном потоке, чтобы не блокировать GUI
        processing_thread = threading.Thread(target=self._process_videos_wrapper, daemon=True)
        processing_thread.start()

    def _process_videos_wrapper(self):
        """
        Запуск пакетной обработки в отдельном потоке.
        """
        try:
            self.processing_manager.process_batch()
            self.root.after(0, lambda: self.status_var.set("Processing completed"))
        except Exception as e:
            logging.exception("Error in video processing:")
            self.root.after(0, lambda: self.status_var.set(f"Error: {str(e)}"))

    def show_report(self):
        """
        Открывает окно с отчетом (ReportPanel).
        """
        report_window = tk.Toplevel(self.root)
        report_window.title("LPR Report")
        report_window.geometry("1000x600")
        ReportPanel(report_window)

    def open_settings(self):
        """
        Открывает диалоговое окно с настройками системы.
        """
        SettingsDialog(self.root, self.db)

    def create_profile(self):
        """
        Диалог для создания нового профиля.
        """
        name = simpledialog.askstring("Create Profile", "Enter profile name:")
        if name:
            try:
                self.db.add_profile(name)
                messagebox.showinfo("Success", f"Profile '{name}' created successfully")
                self.profile = name
                self.profile_label.config(text=f"Profile: {name}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to create profile: {str(e)}")

    def on_closing(self):
        """
        Обработчик закрытия главного окна.
        Если идёт процесс обработки, запрашивает подтверждение.
        """
        # Проверяем, есть ли активные потоки
        if self.processing_manager and self.processing_manager.active_threads:
            if messagebox.askyesno("Quit", "Processing is active. Stop and quit?"):
                self.processing_manager.stop_all()
                self.root.destroy()
        else:
            self.root.destroy()


def main():
    """
    Точка входа в программу. Спрашивает пароль, при верном пароле запускает Tkinter-приложение.
    """
    password = simpledialog.askstring("Password", "Enter password:", show="*")
    if password == "1":
        root = tk.Tk()
        root.geometry("800x600")
        root.minsize(600, 400)
        app = MainApp(root)
        root.protocol("WM_DELETE_WINDOW", app.on_closing)

        def setup_style():
            style = ttk.Style()
            style.configure('Danger.TLabel', foreground='red', font=('Helvetica', 10, 'bold'))
            style.configure('TButton', padding=6)
            style.configure('TEntry', padding=3)
            style.configure('TLabel', padding=3)
            style.configure("Treeview", background="#ffffff", foreground="black", rowheight=25, fieldbackground="#ffffff")
            style.map('Treeview', background=[('selected', '#0078D7')])

        setup_style()
        root.mainloop()
    else:
        messagebox.showerror("Error", "Incorrect password")


if __name__ == "__main__":
    main()
