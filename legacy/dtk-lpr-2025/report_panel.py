# report_panel.py

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import datetime
import logging

from database import DB
from utils import load_and_resize_image, parse_date, decode_if_bytes


class ReportPanel:
    """
    Панель для отображения отчетов:
    - Список номеров (с возможностью фильтрации и поиска)
    - Детальная информация и изображения
    - Статистика и экспорт отчета в HTML
    """
    def __init__(self, master):
        self.master = master
        self.db = DB()
        self.current_sort = {'column': None, 'reverse': False}
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        self.pw = ttk.PanedWindow(self.master, orient=tk.HORIZONTAL)
        self.pw.pack(fill=tk.BOTH, expand=True)

        self.setup_left_panel()
        self.setup_right_panel()

    def setup_left_panel(self):
        lf = ttk.Frame(self.pw)

        sf = ttk.LabelFrame(lf, text="Search")
        sf.pack(fill=tk.X, padx=5, pady=5)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *args: self.load_data())
        search_entry = ttk.Entry(sf, textvariable=self.search_var)
        search_entry.pack(fill=tk.X, padx=5, pady=5)

        ff = ttk.LabelFrame(lf, text="Filters")
        ff.pack(fill=tk.X, padx=5, pady=5)

        pf = ttk.Frame(ff)
        pf.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(pf, text="Profile:").pack(side=tk.LEFT)
        self.profile_var = tk.StringVar(value="All")
        profile_cb = ttk.Combobox(pf, textvariable=self.profile_var,
                                  values=["All"] + self.db.get_profiles())
        profile_cb.pack(side=tk.LEFT, padx=5)
        profile_cb.bind('<<ComboboxSelected>>', lambda e: self.load_data())

        df = ttk.Frame(ff)
        df.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(df, text="Date:").pack(side=tk.LEFT)
        self.date_var = tk.StringVar(value="All")
        date_cb = ttk.Combobox(df, textvariable=self.date_var,
                               values=["All", "Today", "Last 7 Days", "Last 30 Days"])
        date_cb.pack(side=tk.LEFT, padx=5)
        date_cb.bind('<<ComboboxSelected>>', lambda e: self.load_data())

        bf = ttk.Frame(ff)
        bf.pack(fill=tk.X, padx=5, pady=2)
        self.blacklist_var = tk.BooleanVar()
        ttk.Checkbutton(bf, text="Show only blacklisted",
                        variable=self.blacklist_var,
                        command=self.load_data).pack(side=tk.LEFT)

        self.setup_results_tree(lf)
        self.pw.add(lf)

    def setup_results_tree(self, parent):
        columns = ('plate', 'conf', 'country', 'appearances', 'status')
        self.tree = ttk.Treeview(parent, columns=columns, show='headings')

        # Включаем сортировку по клику на заголовок
        for col in columns:
            self.tree.heading(col, text=col.capitalize(), command=lambda c=col: self.sort_column(c))

        self.tree.column('plate', width=100)
        self.tree.column('conf', width=80)
        self.tree.column('country', width=70)
        self.tree.column('appearances', width=90)
        self.tree.column('status', width=100)

        self.tree.tag_configure('blacklisted', foreground='red')

        scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind('<<TreeviewSelect>>', self.on_select)

    def setup_right_panel(self):
        rf = ttk.Frame(self.pw)

        self.details_frame = ttk.LabelFrame(rf, text="Details")
        self.details_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.images_frame = ttk.Frame(self.details_frame)
        self.images_frame.pack(fill=tk.X, padx=5, pady=5)

        self.plate_image_label = ttk.Label(self.images_frame)
        self.plate_image_label.pack(side=tk.LEFT, padx=5)

        self.frame_image_label = ttk.Label(self.images_frame)
        self.frame_image_label.pack(side=tk.LEFT, padx=5)

        self.info_text = tk.Text(self.details_frame, wrap=tk.WORD, height=10)
        self.info_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.stats_frame = ttk.LabelFrame(rf, text="Statistics")
        self.stats_frame.pack(fill=tk.X, padx=5, pady=5)
        self.update_statistics()

        bf = ttk.Frame(rf)
        bf.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(bf, text="Export Report", command=self.export_report).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text="Add to Blacklist", command=self.add_selected_to_blacklist).pack(side=tk.LEFT, padx=5)

        self.pw.add(rf)

    def update_statistics(self):
        """
        Обновляет/перерисовывает сводку статистики.
        """
        stats = self.db.get_plate_stats()
        # Если в базе пока нет номеров, средняя уверенность (avg_confidence) может быть None
        avg_confidence = stats['avg_confidence']
        if avg_confidence is None:
            avg_confidence_str = "N/A"
        else:
            avg_confidence_str = f"{avg_confidence:.2f}"

        stats_text = (
            f"Total Unique Plates: {stats['total_plates']}\n"
            f"Total Detections: {stats['total_detections']}\n"
            f"Blacklisted Plates Detected: {stats['blacklisted_detected']}\n"
            f"Average Confidence: {avg_confidence_str}%"
        )

        for widget in self.stats_frame.winfo_children():
            widget.destroy()

        ttk.Label(self.stats_frame, text=stats_text.strip()).pack(padx=5, pady=5)

    def sort_column(self, col):
        """
        Сортирует данные в self.tree по выбранному столбцу col.
        """
        if self.current_sort['column'] == col:
            self.current_sort['reverse'] = not self.current_sort['reverse']
        else:
            self.current_sort['column'] = col
            self.current_sort['reverse'] = False

        self.load_data()

    def load_data(self):
        """
        Загружает данные из БД, применяет фильтрацию и сортировку, отображает в self.tree.
        """
        self.tree.delete(*self.tree.get_children())

        search_text = self.search_var.get().lower()
        profile_filter = self.profile_var.get()
        date_filter = self.date_var.get()
        blacklist_only = self.blacklist_var.get()

        plates = self.db.get_all_plates()
        filtered_plates = []

        for plate in plates:
            # Фильтр по строке поиска
            if search_text and search_text not in plate['plate_text'].lower():
                continue
            # Фильтр по профилю
            if profile_filter != "All" and plate['profile'] != profile_filter:
                continue
            # Фильтр по дате
            if date_filter != "All":
                last_appearance = decode_if_bytes(plate['last_appearance'])
                try:
                    plate_date = datetime.datetime.fromisoformat(last_appearance)
                except (ValueError, TypeError):
                    # Пытаемся парсить альтернативным способом
                    logging.error(f"Error parsing date {last_appearance}")
                    try:
                        plate_date = datetime.datetime.strptime(last_appearance, '%Y-%m-%d %H:%M:%S.%f')
                    except Exception as e:
                        logging.error(f"Error parsing date with alternative format: {e}")
                        continue

                now = datetime.datetime.now()
                if date_filter == "Today":
                    if plate_date.date() != now.date():
                        continue
                elif date_filter == "Last 7 Days":
                    if plate_date < now - datetime.timedelta(days=7):
                        continue
                elif date_filter == "Last 30 Days":
                    if plate_date < now - datetime.timedelta(days=30):
                        continue

            # Фильтр "только в черном списке"
            if blacklist_only and not plate['is_blacklisted']:
                continue

            filtered_plates.append(plate)

        # Сортировка
        if self.current_sort['column']:
            sort_map = {
                'plate': lambda x: x['plate_text'],
                'conf': lambda x: float(x['confidence']),
                'country': lambda x: x['country_code'],
                'appearances': lambda x: x['total_appearances'],
                'status': lambda x: x['is_blacklisted']
            }
            key_func = sort_map[self.current_sort['column']]
            filtered_plates.sort(key=key_func, reverse=self.current_sort['reverse'])

        # Заполняем Treeview
        for plate in filtered_plates:
            status = "⚠️ Blacklisted" if plate['is_blacklisted'] else "Normal"
            values = (
                plate['plate_text'],
                f"{plate['confidence']:.1f}%",
                plate['country_code'],
                plate['total_appearances'],
                status
            )
            tags = ('blacklisted',) if plate['is_blacklisted'] else ()
            self.tree.insert('', tk.END, values=values, tags=tags)

        self.update_statistics()

    def on_select(self, event):
        """
        При выборе записи в списке загружаем подробные данные и показываем в правой части.
        """
        selection = self.tree.selection()
        if selection:
            plate_text = self.tree.item(selection[0])['values'][0]
            plate_data = next((p for p in self.db.get_all_plates() if p['plate_text'] == plate_text), None)
            if plate_data:
                self.update_details(plate_data)

    def update_details(self, plate_data):
        """
        Показывает детальную информацию о номере (plate_data) в text-widget + изображения.
        """
        self.info_text.delete('1.0', tk.END)
        info_text = (
            f"Plate Number: {plate_data['plate_text']}\n"
            f"Confidence: {plate_data['confidence']:.1f}%\n"
            f"Country: {plate_data['country_code']}\n"
            f"First Seen: {plate_data['first_appearance']}\n"
            f"Last Seen: {plate_data['last_appearance']}\n"
            f"Total Appearances: {plate_data['total_appearances']}\n"
            f"Profile: {plate_data['profile']}\n"
        )

        if plate_data['is_blacklisted']:
            info_text += (
                f"⚠️ BLACKLISTED\n"
                f"Reason: {plate_data['blacklist_reason']}\n"
                f"Danger Level: {plate_data['danger_level']}"
            )

        self.info_text.insert('1.0', info_text)

        if plate_data['is_blacklisted']:
            self.info_text.tag_add('blacklisted', '1.0', 'end')
            self.info_text.tag_config('blacklisted', foreground='red')

        self.update_images(plate_data['plate_image_path'], plate_data['frame_image_path'])

    def update_images(self, plate_path, frame_path):
        """
        Загрузка и отображение миниатюр изображений.
        """
        plate_image = load_and_resize_image(plate_path, (200, 100))
        self.plate_image_label.configure(image=plate_image)
        self.plate_image_label.image = plate_image

        frame_image = load_and_resize_image(frame_path, (400, 200))
        self.frame_image_label.configure(image=frame_image)
        self.frame_image_label.image = frame_image

    def export_report(self):
        """
        Экспорт всего списка plates в HTML-отчет со статистикой и копированием изображений.
        """
        path = filedialog.asksaveasfilename(defaultextension=".html", filetypes=[("HTML files", "*.html")])
        if path:
            try:
                plates_data = self.db.get_all_plates()
                self.export_html(path, plates_data)
                messagebox.showinfo("Success", "Report exported successfully!")
            except Exception as e:
                logging.error(f"Failed to export report: {e}")
                messagebox.showerror("Error", f"Failed to export report: {str(e)}")

    def export_html(self, path, plates_data):
        """
        Формирует HTML-файл отчета и копирует изображения в отдельную папку report_images.
        """
        report_dir = os.path.dirname(path)
        images_dir = os.path.join(report_dir, 'report_images')
        os.makedirs(images_dir, exist_ok=True)

        def copy_image(src_path):
            if src_path and os.path.exists(src_path):
                filename = os.path.basename(src_path)
                dst_path = os.path.join(images_dir, filename)
                try:
                    from shutil import copy2
                    copy2(src_path, dst_path)
                    return f'report_images/{filename}'
                except Exception as e:
                    logging.error(f"Failed to copy image {src_path}: {e}")
            return None

        report_data = []
        profiles = set()
        dates = set()

        for plate in plates_data:
            plate_dict = dict(plate)
            plate_dict.update({
                'plate_image': copy_image(plate['plate_image_path']),
                'frame_image': copy_image(plate['frame_image_path']),
                'first_appearance': decode_if_bytes(plate['first_appearance']),
                'last_appearance': decode_if_bytes(plate['last_appearance'])
            })
            profiles.add(decode_if_bytes(plate_dict['profile']))
            dates.add(parse_date(plate_dict['first_appearance']))
            report_data.append(plate_dict)

        if report_data:
            avg_conf = sum(float(p['confidence']) for p in report_data) / len(report_data)
        else:
            avg_conf = 0

        stats = {
            'total_plates': len({p['plate_text'] for p in report_data}),
            'total_detections': len(report_data),
            'blacklisted': sum(1 for p in report_data if p['is_blacklisted']),
            'avg_confidence': avg_conf,
            'countries': len({p['country_code'] for p in report_data}),
            'profiles': len(profiles)
        }

        dates_dict = {}
        for plate in report_data:
            date_str = plate['first_appearance'][:10]
            dates_dict[date_str] = dates_dict.get(date_str, 0) + 1

        # Создаём HTML
        html_content = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>LPR System Report - {datetime.datetime.now().strftime('%Y-%m-%d')}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header {{ text-align: center; margin-bottom: 30px; padding-bottom: 20px; border-bottom: 2px solid #eee; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .stat-card {{ background-color: #f8f9fa; padding: 15px; border-radius: 6px; text-align: center; }}
        .chart-container {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin: 30px 0; }}
        .chart-box {{ background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
        .plates {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }}
        .plate-card {{ background-color: white; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; transition: transform .2s; }}
        .plate-card:hover {{ transform: translateY(-5px); box-shadow: 0 4px 8px rgba(0,0,0,0.1); }}
        .plate-card.blacklisted {{ border-color: #dc3545; }}
        .plate-images {{ display: flex; flex-direction: column; gap: 10px; padding: 10px; }}
        .plate-images img {{ width: 100%; height: auto; border-radius: 4px; cursor: pointer; }}
        .plate-info {{ padding: 15px; }}
        .plate-info h3 {{ margin: 0 0 10px; color: #333; }}
        .blacklisted .plate-info h3 {{ color: #dc3545; }}
        .plate-info p {{ margin: 5px 0; color: #666; }}
        .confidence {{ display: inline-block; padding: 3px 8px; border-radius: 12px; font-size: 14px; font-weight: bold; }}
        .blacklist-warning {{ background-color: #dc3545; color: white; padding: 10px; border-radius: 4px; margin-bottom: 10px; }}
        .modal {{ display: none; position: fixed; z-index: 1000; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.9); }}
        .modal-content {{ margin: auto; display: block; max-width: 90%; max-height: 90vh; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); }}
        .modal-close {{ position: absolute; top: 15px; right: 35px; color: #f1f1f1; font-size: 40px; font-weight: bold; cursor: pointer; }}
        .modal-close:hover {{ color: #bbb; }}
        @media print {{
            body {{ background-color: white; }}
            .container {{ box-shadow: none; }}
        }}
    </style>
</head>
<body>
<div id="imageModal" class="modal">
    <span class="modal-close">×</span>
    <img class="modal-content" id="modalImage">
</div>
<div class="container">
    <div class="header">
        <h1>LPR System Report</h1>
        <p>Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    <div class="stats">
        <div class="stat-card"><h3>Total Unique Plates</h3><p>{stats['total_plates']}</p></div>
        <div class="stat-card"><h3>Total Detections</h3><p>{stats['total_detections']}</p></div>
        <div class="stat-card"><h3>Blacklisted Plates</h3><p style="color:#dc3545">{stats['blacklisted']}</p></div>
        <div class="stat-card"><h3>Average Confidence</h3><p>{stats['avg_confidence']:.1f}%</p></div>
        <div class="stat-card"><h3>Unique Countries</h3><p>{stats['countries']}</p></div>
        <div class="stat-card"><h3>Unique Profiles</h3><p>{stats['profiles']}</p></div>
    </div>
    <div class="chart-container">
        <div class="chart-box"><canvas id="detectionsByDate"></canvas></div>
        <div class="chart-box"><canvas id="blacklistBreakdown"></canvas></div>
    </div>
    <h2>Detected Plates</h2>
    <div class="plates">
'''

        for plate in report_data:
            plate_date = plate['first_appearance'][:10]
            try:
                confidence_val = float(plate['confidence'])
            except:
                confidence_val = 0
            if confidence_val < 80:
                confidence_color = '#dc3545'
            elif confidence_val < 90:
                confidence_color = '#ffc107'
            else:
                confidence_color = '#28a745'

            blacklisted_class = 'blacklisted' if plate['is_blacklisted'] else ''
            reason_text = ""
            if plate.get('reason'):
                reason_text = f"Reason: {plate['reason']}\nDanger Level: {plate['danger_level']}"

            reason_block = ''
            if plate['is_blacklisted']:
                reason_block = f'''
<div class="blacklist-warning">
    ⚠️ BLACKLISTED<br>{reason_text}
</div>
'''

            html_content += f'''
<div class="plate-card {blacklisted_class}" data-profile="{plate['profile']}" data-date="{plate_date}">
    {reason_block}
    <div class="plate-images">
        {f'<img src="{plate["plate_image"]}" alt="Plate Image" onclick="openModal(this)">' if plate["plate_image"] else ''}
        {f'<img src="{plate["frame_image"]}" alt="Frame Image" onclick="openModal(this)">' if plate["frame_image"] else ''}
    </div>
    <div class="plate-info">
        <h3>{plate['plate_text']}</h3>
        <p><span class="confidence" style="background-color:{confidence_color};color:white">{confidence_val:.1f}%</span></p>
        <p>Country: {plate['country_code']}</p>
        <p>First Seen: {plate['first_appearance']}</p>
        <p>Last Seen: {plate['last_appearance']}</p>
        <p>Total Appearances: {plate['total_appearances']}</p>
        <p>Profile: {plate['profile']}</p>
    </div>
</div>
'''

        # Закрываем контейнер
        html_content += '''
    </div>
</div>
<script>
const modal = document.getElementById('imageModal');
const modalImg = document.getElementById('modalImage');
const closeBtn = document.getElementsByClassName('modal-close')[0];

function openModal(img) {
    modal.style.display = "block";
    modalImg.src = img.src;
}

closeBtn.onclick = () => modal.style.display = "none";
modal.onclick = e => { if(e.target === modal) modal.style.display = "none"; };
document.addEventListener('keydown', e => {
  if(e.key === 'Escape' && modal.style.display === 'block') modal.style.display = 'none';
});

new Chart(document.getElementById('detectionsByDate'), {
    type: 'line',
    data: {
        labels: ''' + f"{[d for d in sorted(dates_dict.keys())]}" + ''',
        datasets: [{
            label: 'Detections',
            data: ''' + f"{[dates_dict[d] for d in sorted(dates_dict.keys())]}" + ''',
            borderColor: '#0d6efd',
            backgroundColor: 'rgba(13,110,253,0.1)',
            tension: 0.1
        }]
    },
    options: {
        responsive: true,
        plugins: {
            title: { display: true, text: 'Detections by Date' }
        }
    }
});

new Chart(document.getElementById('blacklistBreakdown'), {
    type: 'pie',
    data: {
        labels: ['Blacklisted', 'Non-Blacklisted'],
        datasets: [{
            data: [''' + f"{stats['blacklisted']}, {stats['total_detections'] - stats['blacklisted']}" + '''],
            backgroundColor: ['#dc3545', '#0d6efd']
        }]
    },
    options: {
        responsive: true,
        plugins: {
            title: { display: true, text: 'Blacklist Breakdown' }
        }
    }
});
</script>
</body>
</html>
'''

        with open(path, 'w', encoding='utf-8') as f:
            f.write(html_content)

    def add_selected_to_blacklist(self):
        """
        Добавляет выбранный номер в blacklist с указанием причины и уровня опасности.
        """
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a plate first")
            return

        plate_text = self.tree.item(selection[0])['values'][0]
        dialog = tk.Toplevel(self.master)
        dialog.title("Add to Blacklist")
        dialog.geometry("400x300")

        ttk.Label(dialog, text="Reason:").pack(padx=5, pady=5)
        reason_entry = ttk.Entry(dialog, width=40)
        reason_entry.pack(padx=5, pady=5)

        ttk.Label(dialog, text="Danger Level:").pack(padx=5, pady=5)
        danger_var = tk.StringVar(value="HIGH")
        danger_cb = ttk.Combobox(dialog, textvariable=danger_var, values=["LOW", "MEDIUM", "HIGH", "CRITICAL"])
        danger_cb.pack(padx=5, pady=5)

        def save():
            self.db.add_to_blacklist(plate_text, reason_entry.get(), danger_var.get())
            messagebox.showinfo("Success", f"Added {plate_text} to blacklist")
            self.load_data()
            dialog.destroy()

        ttk.Button(dialog, text="Save", command=save).pack(pady=10)
