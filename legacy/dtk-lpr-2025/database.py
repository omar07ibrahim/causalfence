# database.py

import sqlite3
import datetime
import logging
import Levenshtein

from constants import DATABASE_PATH
from utils import decode_if_bytes


class DB:
    """
    Класс для работы с базой данных (SQLite).
    """
    def __init__(self, path=DATABASE_PATH):
        self.path = path
        self._init_db()

    def _init_db(self):
        """
        Инициализация структуры базы данных:
        - Таблицы: plates, images, blacklist, blacklist_alerts, profiles, settings
        - Начальные настройки (settings)
        """
        with sqlite3.connect(self.path) as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS plates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate_text TEXT,
                    confidence REAL,
                    country_code TEXT,
                    timestamp TEXT,
                    first_appearance TEXT,
                    last_appearance TEXT,
                    profile TEXT,
                    total_appearances INTEGER DEFAULT 1,
                    is_blacklisted BOOLEAN DEFAULT 0,
                    reason TEXT,
                    danger_level TEXT
                );

                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate_id INTEGER,
                    plate_image_path TEXT,
                    frame_image_path TEXT,
                    FOREIGN KEY(plate_id) REFERENCES plates(id)
                );

                CREATE TABLE IF NOT EXISTS blacklist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate_text TEXT UNIQUE,
                    reason TEXT,
                    danger_level TEXT,
                    date_added TEXT,
                    last_seen TEXT,
                    location TEXT,
                    notes TEXT
                );

                CREATE TABLE IF NOT EXISTS blacklist_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate_text TEXT,
                    detection_time TEXT,
                    location TEXT,
                    image_path TEXT,
                    processed BOOLEAN DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_name TEXT UNIQUE,
                    created_date TEXT,
                    settings TEXT
                );

                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    setting_name TEXT UNIQUE,
                    setting_value TEXT,
                    setting_type TEXT
                );

                INSERT OR IGNORE INTO settings (setting_name, setting_value, setting_type)
                VALUES
                    ('threads', '4', 'integer'),
                    ('min_confidence', '75', 'float'),
                    ('save_blacklist_matches', 'true', 'boolean'),
                    ('alert_sound', 'true', 'boolean');
            ''')

    def exec(self, query, params=()):
        """
        Универсальный метод для выполнения SQL-запросов.
        Возвращает объект курсора (sqlite3.Cursor).
        """
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(query, params)

    def insert_plate(self, data):
        """
        Сохранение новой записи в таблицу plates.
        data ожидается в формате:
            (plate_text, confidence, country_code, timestamp,
             first_appearance, last_appearance, profile)
        """
        pt = data[0]
        is_blacklisted = False
        blacklist_info = None
        blacklist_plates = self.get_blacklist()

        # Проверка на схожесть с номерами из blacklist через Levenshtein.distance
        for bp in blacklist_plates:
            if Levenshtein.distance(pt, bp['plate_text']) <= 2:
                is_blacklisted = True
                blacklist_info = bp
                break

        pid = self.exec('''
            INSERT INTO plates
            (plate_text, confidence, country_code, timestamp,
             first_appearance, last_appearance, profile, is_blacklisted)
            VALUES (?,?,?,?,?,?,?,?)
        ''', (*data, is_blacklisted)).lastrowid

        if blacklist_info:
            self.exec('''
                UPDATE plates
                SET reason = ?, danger_level = ?
                WHERE id = ?
            ''', (blacklist_info['reason'], blacklist_info['danger_level'], pid))

        return pid

    def save_images(self, pid, pp, fp):
        """
        Сохранение путей к изображениям (plate_image, frame_image) в таблице images.
        """
        self.exec('INSERT INTO images (plate_id, plate_image_path, frame_image_path) VALUES (?,?,?)',
                  (pid, pp, fp))

    def get_all_plates(self):
        """
        Возвращает все данные из plates, объединяя с таблицами images и blacklist (по plate_text).
        """
        return self.exec('''
            SELECT
                p.*,
                i.plate_image_path,
                i.frame_image_path,
                b.reason as blacklist_reason,
                b.danger_level
            FROM plates p
            LEFT JOIN images i ON p.id=i.plate_id
            LEFT JOIN blacklist b ON p.plate_text=b.plate_text
            ORDER BY p.last_appearance DESC
        ''').fetchall()

    def update_plate(self, pid, la, confidence, plate_image_path, frame_image_path):
        """
        Обновляет поля last_appearance, confidence (если новое значение выше),
        total_appearances для указанной записи (pid),
        а также обновляет пути изображений в таблице images.
        """
        self.exec('''
            UPDATE plates
            SET last_appearance = ?,
                confidence = MAX(confidence, ?),
                total_appearances = total_appearances + 1
            WHERE id = ?
        ''', (la, confidence, pid))

        self.exec('''
            UPDATE images
            SET plate_image_path = ?,
                frame_image_path = ?
            WHERE plate_id = ?
        ''', (plate_image_path, frame_image_path, pid))

    def add_to_blacklist(self, pt, reason="", danger_level="HIGH"):
        """
        Добавляет новый номер в blacklist.
        """
        now = datetime.datetime.now().isoformat()
        self.exec('''
            INSERT INTO blacklist (plate_text, reason, danger_level, date_added, last_seen)
            VALUES (?,?,?,?,?)
        ''', (pt, reason, danger_level, now, now))
        self.update_blacklist_status()

    def update_blacklist_status(self):
        """
        Пересчитывает признак is_blacklisted для всех номеров в таблице plates,
        сравнивая их с blacklist (с допущением расстояния Левенштейна <= 2).
        """
        # Список всех номеров из blacklist
        blacklist_plates = [row['plate_text'] for row in self.get_blacklist()]

        # Обновление статуса для всех plates
        all_plates = self.exec('SELECT id, plate_text FROM plates').fetchall()
        for plate in all_plates:
            # Проверяем расстояние Левенштейна, чтобы считать номер схожим
            is_blacklisted = any(Levenshtein.distance(plate['plate_text'], bp) <= 2
                                 for bp in blacklist_plates)
            self.exec('UPDATE plates SET is_blacklisted = ? WHERE id = ?', (is_blacklisted, plate['id']))

    def remove_from_blacklist(self, pt):
        """
        Удаление номера из blacklist и пересчет статусов в plates.
        """
        self.exec('DELETE FROM blacklist WHERE plate_text=?', (pt,))
        self.update_blacklist_status()

    def get_blacklist(self):
        """
        Возвращает все записи из blacklist,
        включая число детекций (detection_count) из таблицы plates.
        """
        return self.exec('''
            SELECT b.*,
                   (SELECT COUNT(*) FROM plates WHERE plate_text=b.plate_text) as detection_count
            FROM blacklist b
        ''').fetchall()

    def is_in_blacklist(self, pt):
        """
        Проверяет, существует ли номер pt в blacklist (точное совпадение).
        """
        return bool(self.exec('SELECT 1 FROM blacklist WHERE plate_text=?', (pt,)).fetchone())

    def add_blacklist_alert(self, plate_text, image_path):
        """
        Записывает факт обнаружения номера из blacklist в таблицу blacklist_alerts.
        """
        now = datetime.datetime.now().isoformat()
        self.exec('''
            INSERT INTO blacklist_alerts (plate_text, detection_time, image_path)
            VALUES (?,?,?)
        ''', (plate_text, now, image_path))

    def get_unprocessed_alerts(self):
        """
        Возвращает все необработанные (processed=0) алерты из blacklist_alerts.
        """
        return self.exec('SELECT * FROM blacklist_alerts WHERE processed=0').fetchall()

    def mark_alert_processed(self, alert_id):
        """
        Ставит флаг processed=1 для указанного alert_id.
        """
        self.exec('UPDATE blacklist_alerts SET processed=1 WHERE id=?', (alert_id,))

    def get_plate_stats(self):
        """
        Собирает сводную статистику по номерам в базе:
        - total_plates (уникальных)
        - blacklisted_detected (сколько из них в blacklisted)
        - avg_confidence (средняя уверенность)
        - total_detections (общее кол-во строк в plates)
        - unique_countries (кол-во уникальных country_code)
        """
        return {
            'total_plates': self.exec('SELECT COUNT(DISTINCT plate_text) FROM plates').fetchone()[0],
            'blacklisted_detected': self.exec('''
                SELECT COUNT(DISTINCT p.plate_text)
                FROM plates p
                JOIN blacklist b ON p.plate_text=b.plate_text
            ''').fetchone()[0],
            'avg_confidence': self.exec('SELECT AVG(confidence) FROM plates').fetchone()[0],
            'total_detections': self.exec('SELECT COUNT(*) FROM plates').fetchone()[0],
            'unique_countries': self.exec('SELECT COUNT(DISTINCT country_code) FROM plates').fetchone()[0]
        }

    def get_plate_id(self, pt):
        """
        Возвращает id записи с plate_text == pt или None.
        """
        return next((r[0] for r in self.exec('SELECT id FROM plates WHERE plate_text=?', (pt,))), None)

    def get_plate_by_id(self, pid):
        """
        Возвращает запись из plates по её id.
        """
        return self.exec('SELECT * FROM plates WHERE id=?', (pid,)).fetchone()

    def add_profile(self, pn):
        """
        Создает новую запись в таблице profiles.
        """
        self.exec('INSERT INTO profiles (profile_name, created_date, settings) VALUES (?,?,?)',
                  (pn, datetime.datetime.now().isoformat(), '{}'))

    def get_profiles(self):
        """
        Возвращает список имен профилей.
        """
        return [r['profile_name'] for r in self.exec('SELECT profile_name FROM profiles')]

    def get_setting(self, sn, default=None):
        """
        Возвращает значение настройки по её имени (sn).
        Если настройка не найдена, возвращается default.
        """
        result = self.exec('SELECT setting_value, setting_type FROM settings WHERE setting_name=?', (sn,)).fetchone()
        if not result:
            return default
        return self._convert_setting_value(result['setting_value'], result['setting_type'])

    def _convert_setting_value(self, value, type_):
        """
        Преобразует строковое значение в соответствующий тип (int, float, bool, str).
        """
        if type_ == 'integer':
            return int(value)
        elif type_ == 'float':
            return float(value)
        elif type_ == 'boolean':
            return value.lower() == 'true'
        return value

    def set_setting(self, sn, sv):
        """
        Сохраняет настройку sn со значением sv (в строковом виде).
        """
        self.exec('UPDATE settings SET setting_value=? WHERE setting_name=?', (str(sv), sn))

    def clear_database(self):
        """
        Полностью удаляет и пересоздает структуру базы данных.
        """
        with sqlite3.connect(self.path) as conn:
            conn.executescript('''
                DROP TABLE IF EXISTS plates;
                DROP TABLE IF EXISTS images;
                DROP TABLE IF EXISTS blacklist;
                DROP TABLE IF EXISTS blacklist_alerts;
                DROP TABLE IF EXISTS profiles;
                DROP TABLE IF EXISTS settings;
            ''')
        # Заново создаем структуру таблиц
        self._init_db()
