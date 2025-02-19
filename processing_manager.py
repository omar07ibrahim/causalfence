# processing_manager.py

import threading
import time
from queue import Queue
import logging

import cv2

from video_processor import VideoProcessor
from database import DB
from constants import MAX_CONCURRENT_STREAMS


class VideoProcessingManager:
    """
    Менеджер для управления параллельной (или последовательной) обработкой видео.
    Использует очередь (Queue) для хранения путей к файлам.
    Количество одновременно обрабатываемых потоков ограничено MAX_CONCURRENT_STREAMS.
    """
    def __init__(self, profile, progress_frame):
        self.video_queue = Queue()
        self.active_threads = []
        self.total_videos = 0
        self.processed_count = 0
        self.total_plates_found = 0
        self.total_blacklisted = 0

        self.profile = profile
        self.stop_event = threading.Event()
        self.progress_frame = progress_frame
        self.status_widgets = {}
        self.db = DB()

    def add_video(self, video_path):
        """
        Добавляет видео в очередь на обработку,
        одновременно добавляя в progress_frame отображение прогресса этого видео.
        """
        self.total_videos += 1
        self.video_queue.put(video_path)

        # Пробуем определить длительность ролика (секунды) — для прогресса
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        duration = 0
        if fps and fps > 0:
            duration = total_frames / fps

        self.status_widgets[video_path] = self.progress_frame.add_video(video_path, duration)
        self.progress_frame.update_progress(
            self.processed_count, self.total_videos, self.total_plates_found, self.total_blacklisted
        )

    def process_batch(self):
        """
        Извлекает все видео из очереди и обрабатывает их в потоках,
        не превышая одновременное количество MAX_CONCURRENT_STREAMS.
        После завершения всех потоков обновляет итоговый прогресс.
        """
        while not self.video_queue.empty():
            # Контролируем лимит активных потоков
            while len(self.active_threads) >= MAX_CONCURRENT_STREAMS:
                self._cleanup_finished_threads()
                time.sleep(0.3)

            video_path = self.video_queue.get()
            status_widgets = self.status_widgets[video_path]

            processor = VideoProcessor(
                video_path,
                len(self.active_threads) + 1,
                self.profile,
                self.stop_event,
                status_widgets
            )

            thread = threading.Thread(
                target=self._process_video_wrapper,
                args=(processor,),
                daemon=True
            )
            thread.start()

            self.active_threads.append((thread, processor))

        # Дождёмся завершения всех потоков
        while self.active_threads:
            self._cleanup_finished_threads()
            time.sleep(0.3)

        # Финальный апдейт прогресса
        self.progress_frame.update_progress(
            self.total_videos, self.total_videos,
            self.total_plates_found, self.total_blacklisted
        )
        logging.info("All videos processed")

    def _process_video_wrapper(self, processor):
        """
        Функция-обёртка для обработки одного видео.
        При завершении обновляет счётчики (processed_count, total_plates_found, total_blacklisted).
        """
        try:
            processor.start_processing()

            # Суммируем общее число распознанных номеров
            self.total_plates_found += processor.plates_found
            self.total_blacklisted += processor.blacklist_found

            # Сигнализируем, что одно видео полностью обработано
            self.processed_count += 1
            self.progress_frame.update_progress(
                self.processed_count,
                self.total_videos,
                self.total_plates_found,
                self.total_blacklisted
            )
        except Exception as e:
            logging.error(f"Error in processing wrapper: {e}", exc_info=True)

    def _cleanup_finished_threads(self):
        """
        Убирает из списка все завершившиеся потоки.
        """
        alive_threads = []
        for t, proc in self.active_threads:
            if t.is_alive():
                alive_threads.append((t, proc))
        self.active_threads = alive_threads

    def stop_all(self):
        """
        Останавливает все потоки (через установку stop_event) и дожидается их завершения.
        """
        self.stop_event.set()
        for t, _ in self.active_threads:
            t.join()
