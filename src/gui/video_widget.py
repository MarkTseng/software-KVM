"""Video display widget using OpenCV and PyQt6."""

from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class VideoWorker(QThread):
    frame_ready = pyqtSignal(np.ndarray)

    def __init__(self, capture_device, parent=None):
        super().__init__(parent)
        self.capture_device = capture_device
        self._is_running = False

    def run(self):
        self._is_running = True
        while self._is_running:
            ret, frame = self.capture_device.read_frame()
            if ret and frame is not None:
                self.frame_ready.emit(frame)
            self.msleep(1)

    def stop(self):
        self._is_running = False
        self.wait()


class VideoWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._init_ui()
        self._worker: Optional[VideoWorker] = None
        self._capture_device = None
        self._original_size = QSize(1920, 1080)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: black;")
        self.video_label.setMinimumSize(640, 480)

        layout.addWidget(self.video_label)
        self.setLayout(layout)

    def start_capture(self, capture_device):
        self._capture_device = capture_device
        if not capture_device.start():
            self.video_label.setText("Failed to start video capture")
            return False

        w, h = capture_device.get_actual_size()
        if w > 0 and h > 0:
            self._original_size = QSize(w, h)

        self._worker = VideoWorker(capture_device)
        self._worker.frame_ready.connect(self._update_frame)
        self._worker.start()
        return True

    def stop_capture(self):
        if self._worker:
            self._worker.stop()
            self._worker = None

        if self._capture_device:
            self._capture_device.stop()
            self._capture_device = None

    def _update_frame(self, frame: np.ndarray):
        if frame is None:
            return

        if len(frame.shape) == 3:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        else:
            rgb_frame = frame

        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w
        q_image = QImage(rgb_frame.tobytes(), w, h, bytes_per_line, QImage.Format.Format_RGB888)

        pixmap = QPixmap.fromImage(q_image)
        scaled_pixmap = pixmap.scaled(
            self.video_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.video_label.setPixmap(scaled_pixmap)

    def clear(self):
        self.video_label.clear()
        self.video_label.setText("No video signal")

    def closeEvent(self, a0):
        self.stop_capture()
        super().closeEvent(a0)
