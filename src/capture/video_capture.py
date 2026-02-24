"""Cross-platform video capture using OpenCV."""

import platform
import subprocess
from typing import List, Optional, Tuple
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class VideoDevice:
    index: int
    name: str
    path: str = ""


@dataclass
class VideoFormat:
    width: int
    height: int
    fps: int
    
    def __str__(self):
        return f"{self.width}x{self.height} @ {self.fps}fps"


def list_video_devices() -> List[VideoDevice]:
    """List all available video capture devices."""
    devices = []
    system = platform.system()

    if system == "Windows":
        devices = _list_windows_devices()
    elif system == "Darwin":
        devices = _list_macos_devices()
    else:
        devices = _list_linux_devices()

    return devices


def _list_windows_devices() -> List[VideoDevice]:
    devices = []
    index = 0
    while True:
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            break
        devices.append(VideoDevice(index=index, name=f"Camera {index}"))
        cap.release()
        index += 1
    return devices


def _list_macos_devices() -> List[VideoDevice]:
    devices = []
    try:
        result = subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stderr.split("\n")
        for line in lines:
            if "[AVFoundation" in line and "video" in line.lower():
                devices.append(VideoDevice(index=len(devices), name=line.strip()))
    except Exception:
        pass

    if not devices:
        index = 0
        while index < 10:
            cap = cv2.VideoCapture(index)
            if cap.isOpened():
                devices.append(VideoDevice(index=index, name=f"Camera {index}"))
                cap.release()
            index += 1

    return devices


def _list_linux_devices() -> List[VideoDevice]:
    devices = []
    import os
    video_devices = [f for f in os.listdir("/dev") if f.startswith("video")]
    for i, dev in enumerate(sorted(video_devices)):
        devices.append(VideoDevice(index=i, name=dev, path=f"/dev/{dev}"))
    return devices


def get_supported_formats(device_index: int) -> List[VideoFormat]:
    """Get supported video formats for a device."""
    system = platform.system()
    formats = []
    
    if system == "Darwin":
        formats = _get_macos_formats(device_index)
    
    if not formats:
        formats = _probe_formats(device_index)
    
    return formats


def _get_macos_formats(device_index: int) -> List[VideoFormat]:
    """Get formats on macOS using avfoundation."""
    formats = []
    try:
        result = subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-list_formats", "true", "-i", str(device_index)],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stderr.split("\n")
        for line in lines:
            if "pixel_format" in line.lower() or "avfoundation" in line.lower():
                parts = line.split()
                for i, part in enumerate(parts):
                    if "x" in part and part.replace("x", "").isdigit():
                        try:
                            w, h = part.split("x")
                            w, h = int(w), int(h)
                            fps = 30
                            if i + 1 < len(parts) and "fps" in parts[i + 1].lower():
                                fps_str = parts[i + 1].replace("fps", "").replace("fps", "")
                                try:
                                    fps = int(float(fps_str))
                                except:
                                    pass
                            formats.append(VideoFormat(w, h, fps))
                        except:
                            pass
    except Exception:
        pass
    
    return formats


def _probe_formats(device_index: int) -> List[VideoFormat]:
    """Probe common formats to find supported ones."""
    common_formats = [
        (640, 480, 30), (640, 480, 60),
        (800, 600, 30), (800, 600, 60),
        (1024, 768, 30), (1024, 768, 60),
        (1280, 720, 30), (1280, 720, 60),
        (1280, 800, 30), (1280, 800, 60),
        (1280, 1024, 30), (1280, 1024, 60),
        (1440, 900, 30), (1440, 900, 60),
        (1600, 900, 30), (1600, 900, 60),
        (1680, 1050, 30), (1680, 1050, 60),
        (1920, 1080, 30), (1920, 1080, 60),
        (1920, 1200, 30), (1920, 1200, 60),
        (2560, 1440, 30), (2560, 1440, 60),
        (3840, 2160, 30),
    ]
    
    formats = []
    system = platform.system()
    
    if system == "Windows":
        cap = cv2.VideoCapture(device_index, cv2.CAP_DSHOW)
    elif system == "Darwin":
        cap = cv2.VideoCapture(device_index, cv2.CAP_AVFOUNDATION)
    else:
        cap = cv2.VideoCapture(device_index, cv2.CAP_V4L2)
    
    if not cap.isOpened():
        return formats
    
    tested = set()
    for w, h, fps in common_formats:
        key = (w, h, fps)
        if key in tested:
            continue
        tested.add(key)
        
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        cap.set(cv2.CAP_PROP_FPS, fps)
        
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = int(cap.get(cv2.CAP_PROP_FPS))
        
        if actual_w == w and actual_h == h:
            formats.append(VideoFormat(w, h, actual_fps if actual_fps > 0 else fps))
    
    cap.release()
    return formats


class VideoCapture:
    def __init__(self, device_index: int = 0, width: int = 1920, height: int = 1080, fps: int = 30):
        self.device_index = device_index
        self.width = width
        self.height = height
        self.fps = fps
        self.cap: Optional[cv2.VideoCapture] = None
        self._is_running = False
        self._last_error = ""

    def start(self) -> bool:
        system = platform.system()
        backends = []

        if system == "Windows":
            backends = [cv2.CAP_DSHOW, cv2.CAP_ANY]
        elif system == "Darwin":
            backends = [cv2.CAP_AVFOUNDATION, cv2.CAP_ANY]
        else:
            backends = [cv2.CAP_V4L2, cv2.CAP_ANY]

        for backend in backends:
            try:
                self.cap = cv2.VideoCapture(self.device_index, backend)
                if self.cap.isOpened():
                    break
                self.cap.release()
                self.cap = None
            except Exception as e:
                print(f"Backend {backend} failed: {e}")
                continue

        if not self.cap or not self.cap.isOpened():
            self._last_error = f"Cannot open device {self.device_index}"
            return False

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        
        try:
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        except:
            pass

        actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        if actual_w != self.width or actual_h != self.height:
            print(f"Warning: Requested {self.width}x{self.height}, got {actual_w}x{actual_h}")
            self.width = actual_w
            self.height = actual_h

        self._is_running = True
        return True

    def stop(self) -> None:
        if self.cap:
            self.cap.release()
            self.cap = None
        self._is_running = False

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        if not self.cap or not self._is_running:
            return False, None
        return self.cap.read()

    @property
    def is_running(self) -> bool:
        return self._is_running

    def get_actual_size(self) -> Tuple[int, int]:
        if self.cap:
            w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            return w, h
        return 0, 0
    
    @property
    def last_error(self) -> str:
        return self._last_error
