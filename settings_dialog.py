# settings_dialog.py

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox

from database import DB
from constants import MAX_CONCURRENT_STREAMS


class SettingsDialog:
    """
    Диалоговое окно с настройками системы:
    - Количество потоков
    - Минимальная уверенность распознавания
    - Звуковое оповещение
    - Очистка базы данных
    - Добавление/удаление из blacklist
    - Создание новых профилей
    """
    def __init__(self, parent, db):
        self.parent = parent
        self.db = db
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Settings")
        self.dialog.geometry("400x350")
        self.setup_ui()

    def setup_ui(self):
        notebook = ttk.Notebook(self.dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        main_frame = ttk.Frame(notebook)
        notebook.add(main_frame, text="Main")

        process_frame = ttk.LabelFrame(main_frame, text="Processing", padding=10)
        process_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(process_frame, text="Number of Threads:").grid(row=0, column=0, padx=5, pady=5)
        self.threads_entry = ttk.Entry(process_frame, width=10)
        self.threads_entry.grid(row=0, column=1, padx=5, pady=5)
        self.threads_entry.insert(0, self.db.get_setting('threads', '4'))

        ttk.Label(process_frame, text="Min Confidence (%):").grid(row=1, column=0, padx=5, pady=5)
        self.confidence_entry = ttk.Entry(process_frame, width=10)
        self.confidence_entry.grid(row=1, column=1, padx=5, pady=5)
        self.confidence_entry.insert(0, self.db.get_setting('min_confidence', '75'))

        alert_frame = ttk.LabelFrame(main_frame, text="Alerts", padding=10)
        alert_frame.pack(fill=tk.X, padx=5, pady=5)

        self.alert_sound_var = tk.BooleanVar(value=self.db.get_setting('alert_sound', True))
        ttk.Checkbutton(alert_frame, text="Enable alert sound", variable=self.alert_sound_var).pack(padx=5, pady=5)

        clear_db_frame = ttk.Frame(main_frame)
        clear_db_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(clear_db_frame, text="Clear Database", command=self.clear_database).pack(fill=tk.X, pady=5)

        profiles_frame = ttk.Frame(main_frame)
        profiles_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(profiles_frame, text="Create New Profile", command=self.create_profile).pack(fill=tk.X, pady=5)

        # Второй таб - Blacklist
        blacklist_frame = ttk.Frame(notebook)
        notebook.add(blacklist_frame, text="Blacklist")

        bl_frame = ttk.Frame(blacklist_frame)
        bl_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.blacklist = tk.Listbox(bl_frame)
        self.blacklist.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(bl_frame, orient=tk.VERTICAL, command=self.blacklist.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.blacklist.config(yscrollcommand=scrollbar.set)

        # Загружаем текущий blacklist
        for item in self.db.get_blacklist():
            self.blacklist.insert(
                tk.END,
                f"{item['plate_text']} - {item['reason']} ({item['danger_level']})"
            )

        bl_buttons = ttk.Frame(blacklist_frame)
        bl_buttons.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(bl_buttons, text="Add", command=self.add_to_blacklist).pack(side=tk.LEFT, padx=5)
        ttk.Button(bl_buttons, text="Remove", command=self.remove_from_blacklist).pack(side=tk.LEFT, padx=5)

        ttk.Button(self.dialog, text="Save", command=self.save_settings).pack(pady=10)

    def create_profile(self):
        """
        Диалоговое окно для создания нового профиля.
        """
        name = simpledialog.askstring("Create Profile", "Enter profile name:")
        if name:
            try:
                self.db.add_profile(name)
                messagebox.showinfo("Success", f"Profile '{name}' created successfully")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to create profile: {str(e)}")

    def add_to_blacklist(self):
        """
        Диалоговое окно для добавления номера в blacklist.
        """
        plate = simpledialog.askstring("Add to Blacklist", "Enter plate number:")
        if plate:
            details_dialog = tk.Toplevel(self.dialog)
            details_dialog.title("Blacklist Details")
            details_dialog.geometry("300x200")

            ttk.Label(details_dialog, text="Reason:").pack(padx=5, pady=5)
            reason_entry = ttk.Entry(details_dialog, width=40)
            reason_entry.pack(padx=5, pady=5)

            ttk.Label(details_dialog, text="Danger Level:").pack(padx=5, pady=5)
            danger_var = tk.StringVar(value="HIGH")
            danger_cb = ttk.Combobox(details_dialog, textvariable=danger_var,
                                     values=["LOW", "MEDIUM", "HIGH", "CRITICAL"])
            danger_cb.pack(padx=5, pady=5)

            def save_blacklist():
                try:
                    self.db.add_to_blacklist(plate, reason_entry.get(), danger_var.get())
                    self.blacklist.insert(tk.END, f"{plate} - {reason_entry.get()} ({danger_var.get()})")
                    details_dialog.destroy()
                    messagebox.showinfo("Success", f"Added {plate} to blacklist")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to add to blacklist: {str(e)}")

            ttk.Button(details_dialog, text="Save", command=save_blacklist).pack(pady=10)

    def remove_from_blacklist(self):
        """
        Удаление выбранного номера из списка blacklist.
        """
        selection = self.blacklist.curselection()
        if selection:
            item = self.blacklist.get(selection[0])
            plate = item.split(" - ")[0]
            if messagebox.askyesno("Confirm", f"Remove {plate} from blacklist?"):
                try:
                    self.db.remove_from_blacklist(plate)
                    self.blacklist.delete(selection[0])
                    messagebox.showinfo("Success", f"Removed {plate} from blacklist")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to remove from blacklist: {str(e)}")
        else:
            messagebox.showwarning("Warning", "Please select a plate to remove")

    def save_settings(self):
        """
        Сохранение изменений настроек (threads, min_confidence, alert_sound).
        """
        try:
            threads = int(self.threads_entry.get())
            if not (1 <= threads <= 64):
                raise ValueError("Threads must be between 1 and 64")

            confidence = float(self.confidence_entry.get())
            if not (0 <= confidence <= 100):
                raise ValueError("Confidence must be between 0 and 100")

            self.db.set_setting('threads', str(threads))
            self.db.set_setting('min_confidence', str(confidence))
            self.db.set_setting('alert_sound', str(self.alert_sound_var.get()))

            global MAX_CONCURRENT_STREAMS
            MAX_CONCURRENT_STREAMS = threads

            messagebox.showinfo("Success", "Settings saved successfully!")
            self.dialog.destroy()
        except ValueError as e:
            messagebox.showerror("Error", str(e))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {str(e)}")

    def clear_database(self):
        """
        Полная очистка базы данных (drop & recreate).
        """
        if messagebox.askyesno("Confirm", "Are you sure you want to clear the database?"):
            self.db.clear_database()
            self.blacklist.delete(0, tk.END)
            messagebox.showinfo("Success", "Database cleared successfully")
