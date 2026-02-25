"""Main window for Software KVM application."""

import sys
from typing import Optional, Union, List

import serial.tools.list_ports
import cv2
import numpy as np
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QObject, pyqtSlot
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QImage, QPixmap, QAction
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QComboBox,
    QLabel,
    QMessageBox,
    QStatusBar,
    QCheckBox,
    QMenu,
    QMenuBar,
    QSpinBox,
    QGroupBox,
    QFormLayout,
    QDialog,
    QDialogButtonBox,
)

from ..capture.video_capture import VideoCapture, list_video_devices, get_supported_formats, VideoFormat
from ..hid.ch9329 import CH9329
from ..input.global_hook import GlobalInputHook, KeyEvent, MouseEvent, PermissionError


class MockCH9329:
    """Mock CH9329 for testing without hardware."""
    
    def __init__(self, port_name: str = "MOCK"):
        self.port_name = port_name
        self.left_status = 0
        self._is_moving = False
        print(f"[MOCK] CH9329 initialized on {port_name}")

    def close(self):
        print("[MOCK] CH9329 closed")

    def key_type(self, modifier: int, key: int, *args):
        print(f"[MOCK] Key: modifier={modifier:#x}, key={key:#x}")

    def key_down(self, *args):
        pass

    def key_up_all(self, *args):
        pass

    def mouse_move_rel(self, x: int, y: int):
        print(f"[MOCK] Mouse move rel: x={x}, y={y}")

    def mouse_move_abs(self, x: int, y: int, screen_width: int = 1920, screen_height: int = 1080):
        print(f"[MOCK] Mouse move abs: x={x}, y={y} (screen: {screen_width}x{screen_height})")

    def mouse_button_down(self, button: int):
        print(f"[MOCK] Mouse down: button={button:#x}")

    def mouse_button_up_all(self):
        print("[MOCK] Mouse up")

    def mouse_scroll(self, delta: int):
        print(f"[MOCK] Mouse scroll: delta={delta}")

    @property
    def is_moving(self) -> bool:
        moving = self._is_moving
        self._is_moving = False
        return moving


class VideoThread(QThread):
    """Thread for capturing video frames."""
    frame_ready = pyqtSignal(np.ndarray)
    fps_updated = pyqtSignal(float)
    
    def __init__(self, video_capture):
        super().__init__()
        self.video_capture = video_capture
        self._running = False
        self._frame_count = 0
        self._fps = 0.0
        
    def run(self):
        import time
        self._running = True
        self._frame_count = 0
        last_time = time.time()
        
        while self._running:
            if self.video_capture:
                ret, frame = self.video_capture.read_frame()
                if ret and frame is not None:
                    self.frame_ready.emit(frame)
                    self._frame_count += 1
            
            current_time = time.time()
            elapsed = current_time - last_time
            if elapsed >= 1.0:
                self._fps = self._frame_count / elapsed
                self.fps_updated.emit(self._fps)
                self._frame_count = 0
                last_time = current_time
    
    def stop(self):
        self._running = False
        self.wait()
    
    @property
    def current_fps(self):
        return self._fps


class InputWidget(QWidget):
    """Widget that captures keyboard/mouse input and displays video."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._callback = None
        self._modifier_state = 0
        self._last_mouse_pos = None
        self._current_frame = None
        self._mouse_captured = False
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: #1a1a2e; color: #4a90d9;")
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setText("No Video Signal")
        self.video_label.setScaledContents(False)
        
        layout.addWidget(self.video_label)
        
        # Test with a simple colored background
        from PyQt6.QtGui import QPainter, QColor
        test_pixmap = QPixmap(640, 480)
        test_pixmap.fill(QColor("#2d3436"))
        self.video_label.setPixmap(test_pixmap)
        
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        
        from PyQt6.QtCore import QTimer
        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll_mouse_position)
        self._last_poll_pos = None
        self._poll_enabled = False

    def enterEvent(self, a0):
        self.setFocus()
        self._poll_enabled = True
        self._poll_timer.start(16)  # ~60fps polling
        super().enterEvent(a0)

    def leaveEvent(self, a0):
        self._poll_enabled = False
        self._poll_timer.stop()
        self._last_poll_pos = None
        super().leaveEvent(a0)

    def _poll_mouse_position(self):
        if not self._poll_enabled or not self._callback:
            return
        from PyQt6.QtGui import QCursor
        pos = QCursor.pos()
        widget_pos = self.mapFromGlobal(pos)
        if 0 <= widget_pos.x() <= self.width() and 0 <= widget_pos.y() <= self.height():
            if self._last_poll_pos is None or (widget_pos.x(), widget_pos.y()) != self._last_poll_pos:
                self._callback(MouseEvent(x=widget_pos.x(), y=widget_pos.y()))
                self._last_poll_pos = (widget_pos.x(), widget_pos.y())

    def set_callback(self, callback):
        self._callback = callback

    def update_frame(self, frame: np.ndarray):
        self._current_frame = frame
        if frame is not None:
            h, w, ch = frame.shape
            if ch == 3:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            else:
                rgb_frame = frame
            
            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w
            
            rgb_data = rgb_frame.tobytes()
            q_image = QImage(rgb_data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            
            pixmap = QPixmap.fromImage(q_image)
            
            label_size = self.video_label.size()
            
            if label_size.width() > 0 and label_size.height() > 0:
                scaled = pixmap.scaled(
                    label_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.video_label.setPixmap(scaled)
                self.video_label.repaint()
                self.repaint()

    def clear_video(self):
        self._current_frame = None
        self.video_label.clear()
        self.video_label.setText("No Video Signal")
        self.video_label.setPixmap(QPixmap())
        self.video_label.setStyleSheet("background-color: #1a1a2e; color: #4a90d9;")

    def keyPressEvent(self, a0: QKeyEvent):
        if a0.key() == Qt.Key.Key_F11:
            self._toggle_fullscreen()
            return
        
        key = a0.key()
        
        self._update_modifiers(a0)
        
        if key not in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            if self._callback:
                self._callback(KeyEvent(
                    keycode=key,
                    is_press=True,
                    modifier=self._modifier_state
                ))
        super().keyPressEvent(a0)

    def keyReleaseEvent(self, a0: QKeyEvent):
        key = a0.key()
        if key in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            self._update_modifiers(a0)
            return
        
        self._update_modifiers(a0)
        if self._callback:
            if key:
                self._callback(KeyEvent(
                    keycode=key,
                    is_press=False,
                    modifier=self._modifier_state
                ))
        super().keyReleaseEvent(a0)

    def mousePressEvent(self, a0: QMouseEvent):
        self.setFocus()
        self._mouse_captured = True
        
        if self._callback:
            # Get current mouse position
            from PyQt6.QtGui import QCursor
            pos = QCursor.pos()
            widget_pos = self.mapFromGlobal(pos)
            
            button = 0
            if a0.button() == Qt.MouseButton.LeftButton:
                button = 0x01
            elif a0.button() == Qt.MouseButton.RightButton:
                button = 0x02
            elif a0.button() == Qt.MouseButton.MiddleButton:
                button = 0x04
            
            if button:
                self._callback(MouseEvent(
                    x=widget_pos.x(),
                    y=widget_pos.y(),
                    button=button,
                    is_press=True,
                    is_release=False
                ))
        super().mousePressEvent(a0)

    def mouseReleaseEvent(self, a0: QMouseEvent):
        if self._callback:
            from PyQt6.QtGui import QCursor
            pos = QCursor.pos()
            widget_pos = self.mapFromGlobal(pos)
            self._callback(MouseEvent(
                x=widget_pos.x(),
                y=widget_pos.y(),
                button=0,
                is_press=False,
                is_release=True
            ))
        super().mouseReleaseEvent(a0)

    def eventFilter(self, a0, a1) -> bool:
        return False  # Disabled - using polling instead

    def mouseMoveEvent(self, a0: QMouseEvent):
        pass  # Disabled - using polling instead

    def wheelEvent(self, a0):
        if self._callback:
            delta = a0.angleDelta().y()
            if delta != 0:
                self._callback(MouseEvent(x=0, y=0, scroll_delta=1 if delta > 0 else -1))
        super().wheelEvent(a0)

    def _update_modifiers(self, event):
        mods = event.modifiers()
        self._modifier_state = 0
        if mods & Qt.KeyboardModifier.ControlModifier:
            self._modifier_state |= 0x01
        if mods & Qt.KeyboardModifier.ShiftModifier:
            self._modifier_state |= 0x02
        if mods & Qt.KeyboardModifier.AltModifier:
            self._modifier_state |= 0x04
        if mods & Qt.KeyboardModifier.MetaModifier:
            self._modifier_state |= 0x08

    def _toggle_fullscreen(self):
        window = self.window()
        if window.isFullScreen():
            window.showNormal()
        else:
            window.showFullScreen()


class MainWindow(QMainWindow):
    CH340_VID_PID = "VID:PID=1A86:7523"

    def __init__(self):
        super().__init__()
        self._ch9329: Optional[Union[CH9329, MockCH9329]] = None
        self._video_capture: Optional[VideoCapture] = None
        self._video_thread: Optional[VideoThread] = None
        self._input_hook: Optional[GlobalInputHook] = None
        self._is_remote_active = False
        self._modifier_state = 0
        self._test_mode = False
        self._window_mode = True
        self._debug_mode = False
        self._video_width = 1920
        self._video_height = 1080
        self._video_fps = 30
        self._last_mouse_position = None
        self._supported_formats: List[VideoFormat] = []
        self._last_delta_x = 0
        self._last_delta_y = 0

        self._init_ui()
        self._scan_devices()

    def _init_ui(self):
        self.setWindowTitle("Software KVM")
        self.setMinimumSize(900, 700)
        self.resize(1280, 800)

        self._create_menu_bar()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        row1_layout = QHBoxLayout()
        row1_layout.addWidget(QLabel("Serial:"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(100)
        row1_layout.addWidget(self.port_combo)

        row1_layout.addWidget(QLabel("Video:"))
        self.video_combo = QComboBox()
        self.video_combo.setMinimumWidth(150)
        self.video_combo.currentIndexChanged.connect(self._on_video_device_changed)
        row1_layout.addWidget(self.video_combo)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._scan_devices)
        row1_layout.addWidget(self.refresh_btn)

        row1_layout.addStretch()

        self.test_mode_cb = QCheckBox("Test Mode")
        self.test_mode_cb.stateChanged.connect(self._toggle_test_mode)
        row1_layout.addWidget(self.test_mode_cb)

        self.debug_mode_cb = QCheckBox("Debug Log")
        self.debug_mode_cb.stateChanged.connect(self._toggle_debug_mode)
        row1_layout.addWidget(self.debug_mode_cb)

        self.window_mode_cb = QCheckBox("Window Mode")
        self.window_mode_cb.setChecked(True)
        self.window_mode_cb.stateChanged.connect(self._toggle_window_mode)
        row1_layout.addWidget(self.window_mode_cb)

        self.fullscreen_btn = QPushButton("Fullscreen")
        self.fullscreen_btn.clicked.connect(self._toggle_fullscreen)
        row1_layout.addWidget(self.fullscreen_btn)

        layout.addLayout(row1_layout)

        row2_layout = QHBoxLayout()
        row2_layout.addWidget(QLabel("Resolution:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.setMinimumWidth(150)
        self.resolution_combo.addItem("Select video device first", None)
        self.resolution_combo.currentIndexChanged.connect(self._on_resolution_changed)
        row2_layout.addWidget(self.resolution_combo)

        row2_layout.addWidget(QLabel("FPS:"))
        self.fps_combo = QComboBox()
        self.fps_combo.setMinimumWidth(80)
        self.fps_combo.addItems(["15", "24", "30", "60"])
        self.fps_combo.setCurrentText("30")
        self.fps_combo.currentIndexChanged.connect(self._on_fps_changed)
        row2_layout.addWidget(self.fps_combo)

        self.fps_label = QLabel("--")
        self.fps_label.setMinimumWidth(60)
        self.fps_label.setStyleSheet("font-weight: bold; color: #2ecc71;")
        row2_layout.addWidget(self.fps_label)

        row2_layout.addWidget(QLabel("Delta:"))
        self.delta_label = QLabel("dx=0, dy=0")
        self.delta_label.setMinimumWidth(100)
        self.delta_label.setStyleSheet("font-weight: bold; color: #3498db;")
        row2_layout.addWidget(self.delta_label)

        row2_layout.addStretch()

        self.start_btn = QPushButton("Start")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.setMinimumWidth(100)
        self.start_btn.clicked.connect(self._toggle_remote_session)
        row2_layout.addWidget(self.start_btn)

        layout.addLayout(row2_layout)

        self.input_widget = InputWidget()
        self.input_widget.set_callback(self._handle_input_event)
        layout.addWidget(self.input_widget, 1)

        self.log_label = QLabel("Click 'Start' to begin. F11 = Fullscreen, ESC = Exit Fullscreen, Middle Mouse = Stop Session")
        self.log_label.setStyleSheet("font-family: Courier; font-size: 11px; color: #888; padding: 5px;")
        self.log_label.setMaximumHeight(40)
        layout.addWidget(self.log_label)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready - Window Mode (no permission required)")

    def _create_menu_bar(self):
        menubar = self.menuBar()
        
        view_menu = menubar.addMenu("View")
        
        fullscreen_action = QAction("Fullscreen (F11)", self)
        fullscreen_action.setShortcut("F11")
        fullscreen_action.triggered.connect(self._toggle_fullscreen)
        view_menu.addAction(fullscreen_action)
        
        view_menu.addSeparator()
        
        window_sizes_menu = view_menu.addMenu("Window Size")
        window_sizes = [
            ("640x480", 640, 480),
            ("800x600", 800, 600),
            ("1024x768", 1024, 768),
            ("1280x720", 1280, 720),
            ("1280x800", 1280, 800),
            ("1440x900", 1440, 900),
            ("1600x900", 1600, 900),
            ("1920x1080", 1920, 1080),
        ]
        for name, w, h in window_sizes:
            action = QAction(name, self)
            action.triggered.connect(lambda checked, w=w, h=h: self.resize(w, h))
            window_sizes_menu.addAction(action)
        
        video_menu = menubar.addMenu("Video")
        show_info_action = QAction("Show Video Info", self)
        show_info_action.triggered.connect(self._show_video_info)
        video_menu.addAction(show_info_action)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _restart_video_capture(self):
        if self._video_thread:
            self._video_thread.stop()
            self._video_thread = None
        
        if self._video_capture:
            self._video_capture.stop()
            self._video_capture = None
        
        video_index = self.video_combo.currentData()
        if video_index is not None and video_index >= 0:
            self._video_capture = VideoCapture(
                device_index=video_index,
                width=self._video_width,
                height=self._video_height,
                fps=self._video_fps
            )
            if self._video_capture.start():
                self._video_thread = VideoThread(self._video_capture)
                self._video_thread.frame_ready.connect(self.input_widget.update_frame)
                self._video_thread.start()
                self.statusBar().showMessage(f"Video: {self._video_width}x{self._video_height} @ {self._video_fps}fps")

    def _show_video_info(self):
        if self._video_capture:
            w, h = self._video_capture.get_actual_size()
            QMessageBox.information(
                self, "Video Info",
                f"Current Resolution: {w}x{h}\n"
                f"Requested: {self._video_width}x{self._video_height}\n"
                f"Frame Rate: {self._video_fps} FPS"
            )
        else:
            QMessageBox.information(self, "Video Info", "No video session active")

    def _toggle_test_mode(self, state):
        self._test_mode = state == Qt.CheckState.Checked.value

    def _toggle_debug_mode(self, state):
        self._debug_mode = state == Qt.CheckState.Checked.value

    def _on_video_device_changed(self, index):
        video_index = self.video_combo.currentData()
        if video_index is None or video_index < 0:
            self.resolution_combo.clear()
            self.resolution_combo.addItem("Select video device first", None)
            return
        
        self.statusBar().showMessage("Scanning device formats...")
        QApplication.processEvents()
        
        self._supported_formats = get_supported_formats(video_index)
        
        self.resolution_combo.clear()
        if self._supported_formats:
            resolutions = set()
            for fmt in self._supported_formats:
                resolutions.add((fmt.width, fmt.height))
            for w, h in sorted(resolutions, key=lambda x: (x[0], x[1])):
                self.resolution_combo.addItem(f"{w}x{h}", (w, h))
            self.resolution_combo.setCurrentIndex(0)
            data = self.resolution_combo.currentData()
            if data:
                self._video_width, self._video_height = data
                self._video_fps = int(self.fps_combo.currentText())
            self.statusBar().showMessage(f"Found {len(resolutions)} resolutions")
        else:
            self.resolution_combo.addItem("Default 1920x1080", (1920, 1080))
            self._video_width = 1920
            self._video_height = 1080
            self._video_fps = 30
            self.statusBar().showMessage("Using default format")

    def _on_resolution_changed(self, index):
        data = self.resolution_combo.currentData()
        if data:
            self._video_width, self._video_height = data
            self._video_fps = int(self.fps_combo.currentText())
            self.statusBar().showMessage(f"Resolution: {self._video_width}x{self._video_height} @ {self._video_fps}fps")
            if self._is_remote_active:
                self._restart_video_capture()

    def _on_fps_changed(self, index):
        self._video_fps = int(self.fps_combo.currentText())
        self.statusBar().showMessage(f"Resolution: {self._video_width}x{self._video_height} @ {self._video_fps}fps")
        if self._is_remote_active:
            self._restart_video_capture()

    def _toggle_window_mode(self, state):
        self._window_mode = state == Qt.CheckState.Checked.value
        if self._window_mode:
            self.statusBar().showMessage("Window Mode - Click video area to capture input")
        else:
            self.statusBar().showMessage("Global Mode - Requires Accessibility permission")

    def _scan_devices(self):
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            if "usbserial" in port.device.lower() or "ch340" in port.device.lower():
                self.port_combo.addItem(port.device, port.device)

        if self.port_combo.count() == 0:
            self.port_combo.addItem("No CH9329 found", None)

        self.video_combo.clear()
        devices = list_video_devices()
        for device in devices:
            self.video_combo.addItem(device.name, device.index)

        if not devices:
            self.video_combo.addItem("No video devices found", None)

    def _toggle_remote_session(self):
        if self._is_remote_active:
            self._stop_remote_session()
        else:
            self._start_remote_session()

    def _start_remote_session(self):
        video_index = self.video_combo.currentData()
        
        if video_index is not None and video_index >= 0:
            self._video_capture = VideoCapture(
                device_index=video_index,
                width=self._video_width,
                height=self._video_height,
                fps=self._video_fps
            )
            if self._video_capture.start():
                self._video_thread = VideoThread(self._video_capture)
                self._video_thread.frame_ready.connect(self.input_widget.update_frame)
                self._video_thread.fps_updated.connect(self._update_fps_display)
                self._video_thread.start()
                
                actual_w, actual_h = self._video_capture.get_actual_size()
                self.statusBar().showMessage(f"Video: {actual_w}x{actual_h} @ {self._video_fps}fps")
            else:
                self._video_capture = None

        if self._test_mode:
            self._ch9329 = MockCH9329("TEST_MODE")
        else:
            port_name = self.port_combo.currentData()
            if not port_name:
                self._ch9329 = MockCH9329("NO_PORT")
            else:
                try:
                    self._ch9329 = CH9329(port_name, debug=self._debug_mode)
                except Exception:
                    self._ch9329 = MockCH9329("FAILED")

        use_window_mode = self._window_mode
        
        if not use_window_mode:
            try:
                self._input_hook = GlobalInputHook()
                self._input_hook.set_callback(self._handle_input_event)
                self._input_hook.start()
            except Exception:
                use_window_mode = True
                self.window_mode_cb.setChecked(True)
                self.log_label.setText("Switched to Window Mode (permission not available)")

        self._is_remote_active = True
        self._last_mouse_position = None
        self._last_delta_x = 0
        self._last_delta_y = 0
        self.delta_label.setText("dx=0, dy=0")
        self.start_btn.setText("Stop")
        self.start_btn.setStyleSheet("background-color: #c0392b; color: white;")
        
        mode_text = "TEST MODE" if self._test_mode else "REMOTE SESSION"
        input_text = "Window Mode" if use_window_mode else "Global Mode"
        self.input_widget.video_label.setStyleSheet("border: 3px solid #2ecc71;")
        self.log_label.setText(f"{mode_text} | {input_text} | F11=Fullscreen | Middle Mouse=Stop")
        
        self.input_widget.setFocus()

    def _stop_remote_session(self):
        self._is_remote_active = False
        
        self.input_widget._poll_enabled = False
        self.input_widget._poll_timer.stop()
        
        QApplication.processEvents()

        if self._video_thread:
            try:
                self._video_thread.frame_ready.disconnect()
            except:
                pass
            self._video_thread.stop()
            self._video_thread = None

        if self._video_capture:
            self._video_capture.stop()
            self._video_capture = None

        if self._input_hook:
            self._input_hook.stop()
            self._input_hook = None

        if self._ch9329:
            self._ch9329.close()
            self._ch9329 = None

        if self.isFullScreen():
            self.showNormal()

        self.start_btn.setText("Start")
        self.start_btn.setStyleSheet("")
        self.fps_label.setText("--")
        self.fps_label.setStyleSheet("font-weight: bold; color: #2ecc71;")
        self.delta_label.setText("dx=0, dy=0")
        self.delta_label.setStyleSheet("font-weight: bold; color: #3498db;")
        self.input_widget.clear_video()
        self.input_widget.video_label.setStyleSheet("background-color: #1a1a2e; color: #4a90d9;")
        self.log_label.setText("Click 'Start' to begin. F11=Fullscreen | Ctrl+C=Stop | Ctrl+Q=Quit")
        self.statusBar().showMessage("Session stopped")

    def _update_fps_display(self, fps: float):
        self.fps_label.setText(f"{fps:.1f}")
        if fps >= self._video_fps * 0.9:
            self.fps_label.setStyleSheet("font-weight: bold; color: #2ecc71;")
        elif fps >= self._video_fps * 0.5:
            self.fps_label.setStyleSheet("font-weight: bold; color: #f39c12;")
        else:
            self.fps_label.setStyleSheet("font-weight: bold; color: #e74c3c;")

    def _handle_input_event(self, event):
        if not self._is_remote_active or not self._ch9329:
            return

        if isinstance(event, KeyEvent):
            self._handle_key_event(event)
        elif isinstance(event, MouseEvent):
            self._handle_mouse_event(event)

    def _handle_key_event(self, event: KeyEvent):
        if event.is_press:
            from ..hid.keymap import KeyMap
            hid_code = KeyMap.get_hid_code(event.keycode)
            if self._debug_mode:
                key_info = f"[KEY] Qt key={event.keycode}, mod={event.modifier:#x} -> HID={hid_code:#x}"
                self.log_label.setText(key_info)
            if hid_code:
                self._ch9329.key_type(event.modifier, hid_code)

    def _handle_mouse_event(self, event: MouseEvent):
        if not self._is_remote_active or not self._ch9329:
            return

        video_size = self.input_widget.video_label.size()
        widget_w = video_size.width()
        widget_h = video_size.height()
        
        in_video_area = False
        x = y = 0
        display_w = display_h = 1
        screen_w = screen_h = 1
        
        if widget_w > 0 and widget_h > 0:
            screen_w = self._video_width
            screen_h = self._video_height
            
            video_aspect = screen_w / screen_h if screen_h > 0 else 1
            widget_aspect = widget_w / widget_h if widget_h > 0 else 1
            
            if widget_aspect > video_aspect:
                display_h = widget_h
                display_w = int(widget_h * video_aspect)
                offset_x = (widget_w - display_w) // 2
                offset_y = 0
            else:
                display_w = widget_w
                display_h = int(widget_w / video_aspect)
                offset_x = 0
                offset_y = (widget_h - display_h) // 2
            
            x = event.x - offset_x
            y = event.y - offset_y
            
            in_video_area = 0 <= x <= display_w and 0 <= y <= display_h
        
        if not in_video_area:
            return

        if event.scroll_delta != 0:
            self._ch9329.mouse_scroll(event.scroll_delta)
        else:
            abs_x = int((x / display_w) * screen_w)
            abs_y = int((y / display_h) * screen_h)
            
            self._ch9329.mouse_move_abs(abs_x, abs_y, screen_w, screen_h)
            
            self._last_delta_x = abs_x
            self._last_delta_y = abs_y
            self.delta_label.setText(f"pos={abs_x},{abs_y}")
        
        if event.is_press:
            self._ch9329.mouse_button_down(event.button)
            if event.button == 0x04:
                self._stop_remote_session()
        elif event.is_release:
            self._ch9329.mouse_button_up_all()

    def closeEvent(self, a0):
        self._stop_remote_session()
        super().closeEvent(a0)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
