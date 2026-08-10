# video_processor.py

import time
import logging
import datetime
import os
from PIL import ImageDraw
import Levenshtein
import cv2

# Импорт из DTKLPR5 (движок распознавания) и DTKVID (захват видео).
# Оставляем DTKLPR5.py и DTKVID.py неизменными!
from DTKLPR5 import DTKLPRLibrary, LPREngine, LPRParams, BURN_POS
from DTKVID import DTKVIDLibrary, VideoCapture

from database import DB
from utils import format_time


class VideoProcessor:
    """
    Класс, отвечающий за обработку одного видео:
    - Передача кадров в LPREngine
    - Колбэки при распознавании номеров (plate_callback)
    - Обработка blacklist
    - Сохранение в БД
    """
    def __init__(self, video_path, stream_id, profile, stop_event, status_widgets):
        self.video_path = video_path
        self.stream_id = stream_id
        self.profile = profile
        self.stop_event = stop_event
        self.status_widgets = status_widgets
        self.stopFlag = False

        self.db = DB()

        # Собираем изначально список blacklist и plates (все sqlite3.Row превращаем в dict, чтоб удобно .get(...))
        raw_blacklist = self.db.get_blacklist()
        self.blacklist = {row['plate_text']: dict(row) for row in raw_blacklist}

        raw_known_plates = self.db.get_all_plates()
        self.known_plates = {p['plate_text']: dict(p) for p in raw_known_plates}

        self.plates_found = 0
        self.blacklist_found = 0
        self.frame_count = 0

        # Для более точного прогресса используем счётчик кадров
        self.cap = cv2.VideoCapture(self.video_path)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.cap.release()

        self.setup_lpr()

    def setup_lpr(self):
        """
        Инициализируем движок распознавания номеров, задаём нужные параметры.
        """
        self.params = LPRParams(DTKLPRLibrary('../../lib/windows/x64/'))
        self.params.MinPlateWidth = 80
        self.params.MaxPlateWidth = 300
        self.params.Countries = "AZ"  # Пример. При необходимости замените нужные коды стран
        self.params.FormatPlateText = True
        self.params.BurnFormatString = f"%DATETIME% | Stream {self.stream_id} | Plate: %PLATE_NUM% | Conf: %CONFIDENCE%"
        self.params.BurnPosition = BURN_POS.RIGHT_TOP
        self.params.NumThreads = 1

        # Минимальная уверенность берём из настроек
        min_conf = self.db.get_setting('min_confidence', 75)
        self.params.MinConfidence = min_conf

    def _check_blacklist(self, plate_text):
        """
        Проверка на то, что номер (plate_text) похож (Levenshtein.distance <= 2) на какой-то номер из blacklist.
        """
        for bp, bl_data in self.blacklist.items():
            if Levenshtein.distance(plate_text, bp) <= 2:
                self.blacklist_found += 1
                # Пометим в БД все схожие номера как is_blacklisted
                # также обновим reason и danger_level
                for known_plate_text, plate_data in self.known_plates.items():
                    if Levenshtein.distance(plate_text, known_plate_text) <= 2:
                        self.db.exec('''
                            UPDATE plates
                            SET is_blacklisted = 1,
                                reason = ?,
                                danger_level = ?
                            WHERE plate_text = ?
                        ''', (bl_data.get('reason'), bl_data.get('danger_level'), known_plate_text))
                return bl_data
        return None

    def plate_callback(self, engine, plate):
        """
        Колбэк, вызываемый при распознавании номера. 
        Возвращаем 1, если хотим прервать распознавание.
        """
        if self.stop_event.is_set():
            return 1  # Прекращаем обработку

        self.plates_found += 1
        pt = plate.Text()
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

        # Проверяем blacklist
        blacklist_match = self._check_blacklist(pt)

        # Ищем схожие номера среди уже известных (self.known_plates)
        similar_plates = [
            (p_text, data) for p_text, data in self.known_plates.items()
            if Levenshtein.distance(pt, p_text) <= 2
        ]

        if similar_plates:
            # Берём из схожих тот, у которого выше confidence
            best_match = max(similar_plates, key=lambda x: x[1]['confidence'])

            if plate.Confidence() > best_match[1]['confidence']:
                # Обновляем запись в БД
                self._update_existing_plate(plate, best_match[1], ts)
                pid = best_match[1]['id']

                # Обновляем кэш known_plates
                updated_dict = dict(best_match[1])  # копия
                updated_dict['confidence'] = plate.Confidence()
                updated_dict['last_appearance'] = ts
                self.known_plates[best_match[0]] = updated_dict
            else:
                pid = best_match[1]['id']
        else:
            # В БД такого (или похожего) номера нет, сохраняем новый
            pid = self._save_new_plate(plate, pt, ts)

        # Если номер в blacklist — обрабатываем доп. логику (сохранение спец. изображения, alerts и т.д.)
        if blacklist_match:
            self._handle_blacklist_match(plate, ts, blacklist_match, pid)

        return 0

    def _handle_blacklist_match(self, plate, ts, blacklist_data, pid):
        """
        Дополнительные действия, если распознанный номер — blacklist:
        - Сохраняем помеченную картинку в "blacklist_matches"
        - Добавляем запись в blacklist_alerts
        - Обновляем метку в UI
        """
        try:
            os.makedirs("blacklist_matches", exist_ok=True)
            fp = f"blacklist_matches/{plate.Text()}_{ts}.jpg"
            img = plate.GetImage()

            # Обводим красным
            draw = ImageDraw.Draw(img)
            draw.rectangle(
                [plate.X(), plate.Y(), plate.X() + plate.Width(), plate.Y() + plate.Height()],
                outline="red",
                width=3
            )
            draw.text(
                (10, 10),
                f"BLACKLISTED! Reason: {blacklist_data.get('reason','')}  Danger: {blacklist_data.get('danger_level','')}",
                fill="red"
            )
            img.save(fp)

            self.db.exec('UPDATE plates SET is_blacklisted=1 WHERE id=?', (pid,))
            self.db.add_blacklist_alert(plate.Text(), fp)

            # Обновление статуса в интерфейсе
            self.status_widgets['status_label'].config(
                text=f"⚠️ BLACKLISTED plate detected: {plate.Text()}",
                foreground='red'
            )
        except Exception as e:
            logging.error(f"Error handling blacklist match: {e}", exc_info=True)

    def _update_existing_plate(self, plate, plate_data, ts):
        """
        Обновление уже существующего номера (повышаем confidence, last_appearance, сохраняем изображения).
        """
        try:
            pid = plate_data['id']
            # Приводим sqlite3.Row к dict, если нужно
            plate_data = dict(plate_data)

            os.makedirs("images", exist_ok=True)
            pp = f"images/{plate.Text()}_plate_{ts}.jpg"
            fp = f"images/{plate.Text()}_frame_{ts}.jpg"

            plate.GetPlateImage().save(pp)
            img = plate.GetImage()
            draw = ImageDraw.Draw(img)

            outline_color = "red" if plate_data.get('is_blacklisted') else "green"
            draw.rectangle(
                [plate.X(), plate.Y(), plate.X() + plate.Width(), plate.Y() + plate.Height()],
                outline=outline_color,
                width=5
            )
            img.save(fp)

            self.db.update_plate(pid, ts, plate.Confidence(), pp, fp)

        except Exception as e:
            logging.error(f"Error updating existing plate: {e}", exc_info=True)

    def _save_new_plate(self, plate, pt, ts):
        """
        Сохранение нового номера в БД (+ изображения).
        """
        try:
            is_blacklisted = self.db.is_in_blacklist(pt)
            pid = self.db.insert_plate((
                pt,
                plate.Confidence(),
                plate.CountryCode(),
                plate.Timestamp(),
                plate.DateTimeString(),
                plate.DateTimeString(),
                self.profile
            ))

            os.makedirs("images", exist_ok=True)
            pp = f"images/{pt}_plate_{ts}.jpg"
            fp = f"images/{pt}_frame_{ts}.jpg"

            plate.GetPlateImage().save(pp)
            img = plate.GetImage()
            draw = ImageDraw.Draw(img)
            outline_color = "red" if is_blacklisted else "green"
            draw.rectangle(
                [plate.X(), plate.Y(), plate.X() + plate.Width(), plate.Y() + plate.Height()],
                outline=outline_color,
                width=5
            )
            img.save(fp)

            self.db.save_images(pid, pp, fp)

            # Обновляем кэш
            new_row = self.db.get_plate_by_id(pid)
            if new_row:
                self.known_plates[pt] = dict(new_row)

            return pid
        except Exception as e:
            logging.error(f"Error saving new plate: {e}", exc_info=True)
            return None

    def frame_callback(self, vc, frame, engine):
        """
        Колбэк при захвате каждого кадра. 
        Передаем кадр в движок LPR (engine.PutFrame).
        """
        if not self.stop_event.is_set():
            self.frame_count += 1

            # Обновляем прогресс по кадрам
            if self.total_frames > 0:
                progress_percent = (self.frame_count / self.total_frames) * 100
                self.status_widgets['progress']['value'] = progress_percent

                video_duration = self.status_widgets['duration']  # из progress_frame
                current_time = (self.frame_count / self.total_frames) * video_duration
                self.status_widgets['time_label'].config(
                    text=f"{format_time(current_time)} / {format_time(video_duration)}"
                )

            engine.PutFrame(frame, 0)

    def error_callback(self, vc, ec, engine):
        """
        Колбэк при ошибках захвата. Код 3 (EOF) — не критическая ошибка (конец файла).
        """
        if ec != 3:
            logging.error(f"Stream {self.stream_id} - Error: {ec}")
            self.status_widgets['status_label'].config(text=f"Error: {ec}")
        self.stopFlag = True

    def start_processing(self):
        """
        Запуск процесса распознавания номеров из видео.
        """
        try:
            self.status_widgets['status_label'].config(text="Processing...")
            engine = LPREngine(self.params, True, self.plate_callback)
            if engine.IsLicensed() != 0:
                self.status_widgets['status_label'].config(text="License Error")
                return

            cap = VideoCapture(
                self.frame_callback,
                self.error_callback,
                engine,
                DTKVIDLibrary('../../lib/windows/x64/')
            )
            cap.StartCaptureFromFile(self.video_path, 1)

            logging.info(f"Stream {self.stream_id} started: {self.video_path}")

            # Ждём, пока не будет установлен stopFlag или stop_event
            while not self.stopFlag and not self.stop_event.is_set():
                time.sleep(0.001)

            cap.StopCapture()
            logging.info(f"Stream {self.stream_id} stopped")

            if not self.stop_event.is_set():
                status_text = f"Completed - Found {self.plates_found} plates"
                if self.blacklist_found > 0:
                    status_text += f" (⚠️ {self.blacklist_found} blacklisted)"
                self.status_widgets['status_label'].config(
                    text=status_text,
                    foreground='red' if self.blacklist_found > 0 else 'black'
                )
            else:
                self.status_widgets['status_label'].config(text="Stopped")

        except Exception as e:
            logging.error(f"Error processing stream {self.stream_id}: {e}", exc_info=True)
            self.status_widgets['status_label'].config(text=f"Error: {str(e)}")
