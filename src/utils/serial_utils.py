"""Serial port utilities for CH340 detection."""

from typing import Optional
import serial.tools.list_ports


def find_ch340_port() -> Optional[str]:
    """Find CH340 serial port by VID/PID."""
    VID = "1A86"
    PID = "7523"

    ports = serial.tools.list_ports.comports()
    for port in ports:
        if port.vid and port.pid:
            vid_str = f"{port.vid:04X}"
            pid_str = f"{port.pid:04X}"
            if vid_str == VID and pid_str == PID:
                return port.device
    return None


def list_all_ports() -> list:
    """List all available serial ports."""
    ports = serial.tools.list_ports.comports()
    return [(port.device, port.description, port.hwid) for port in ports]
