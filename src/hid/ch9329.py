"""CH9329 USB HID controller for keyboard and mouse emulation."""

import threading
from typing import List, Optional
from enum import IntEnum

import serial


class CommandCode(IntEnum):
    GET_INFO = 0x01
    SEND_KB_GENERAL_DATA = 0x02
    SEND_KB_MEDIA_DATA = 0x03
    SEND_MS_ABS_DATA = 0x04
    SEND_MS_REL_DATA = 0x05
    READ_MY_HID_DATA = 0x07
    GET_PARA_CFG = 0x08
    GET_USB_STRING = 0x0A


class KeyGroup(IntEnum):
    CharKey = 0x02
    MediaKey = 0x03


class MediaKey:
    EJECT = (0x02, 0x80, 0x00, 0x00)
    CDSTOP = (0x02, 0x40, 0x00, 0x00)
    PREVTRACK = (0x02, 0x20, 0x00, 0x00)
    NEXTTRACK = (0x02, 0x10, 0x00, 0x00)
    PLAYPAUSE = (0x02, 0x08, 0x00, 0x00)
    MUTE = (0x02, 0x04, 0x00, 0x00)
    VOLUMEDOWN = (0x02, 0x02, 0x00, 0x00)
    VOLUMEUP = (0x02, 0x01, 0x00, 0x00)


class CH9329:
    HEAD = bytes([0x57, 0xAB])
    ADDR = 0x00

    CHAR_KEY_UP_PACKET = bytes([
        0x57, 0xAB, 0x00, 0x02, 0x08, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x0c
    ])
    MEDIA_KEY_UP_PACKET = bytes([
        0x57, 0xAB, 0x00, 0x03, 0x04, 0x02, 0x00, 0x00, 0x00, 0x0B
    ])

    def __init__(self, port_name: str = "COM3", baud_rate: int = 9600, debug: bool = False):
        self.port_name = port_name
        self.baud_rate = baud_rate
        self.debug = debug
        self.left_status = 0
        self.serial_port: Optional[serial.Serial] = None
        self._is_moving = False
        self._absolute_mode = False
        self._connect()
        self._init_device()

    def _init_device(self):
        """Initialize CH9329 and enable absolute mouse mode."""
        import time
        time.sleep(0.1)
        
        # Try to set absolute mouse mode
        # Command: 0x57, 0xAB, 0x00, 0x08, 0x04, 0x01, 0x00, checksum
        # This sets mouse to absolute mode
        data = [0x57, 0xAB, 0x00, 0x08, 0x04, 0x01, 0x00]
        packet = self._create_packet(data, True)
        
        def _send_init():
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.write(packet)
                self.serial_port.flush()
                if self.debug:
                    print(f"[CH9329] Init: {packet.hex()}")
        
        thread = threading.Thread(target=_send_init, daemon=True)
        thread.start()
        time.sleep(0.1)

    def _connect(self) -> None:
        try:
            self.serial_port = serial.Serial(
                port=self.port_name,
                baudrate=self.baud_rate,
                timeout=0.1
            )
        except serial.SerialException as e:
            raise ConnectionError(f"Failed to connect to {self.port_name}: {e}")

    def close(self) -> None:
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()

    def _send_packet(self, data: bytes) -> None:
        def _send():
            if self.serial_port and self.serial_port.is_open:
                bytes_written = self.serial_port.write(data)
                self.serial_port.flush()
                if self.debug:
                    print(f"[CH9329] Sent {bytes_written} bytes: {data.hex()}")
            else:
                if self.debug:
                    print(f"[CH9329] Serial port not open!")
            self._is_moving = False

        thread = threading.Thread(target=_send, daemon=True)
        thread.start()

    def _create_packet(self, data_list: List[int], add_checksum: bool = True) -> bytes:
        packet = bytes(data_list)
        if add_checksum:
            checksum = sum(data_list) & 0xFF
            packet = packet + bytes([checksum])
        return packet

    def get_info(self) -> dict:
        packet = bytes([0x57, 0xAB, 0x00, CommandCode.GET_INFO, 0x00, 0x03])
        self._send_packet(packet)
        return {"version": 0, "status": 0}

    def key_down(
        self,
        key_group: KeyGroup,
        modifier: int,
        key1: int = 0,
        key2: int = 0,
        key3: int = 0,
        key4: int = 0,
        key5: int = 0,
        key6: int = 0,
    ) -> None:
        if self.debug:
            print(f"[CH9329] key_down: modifier={modifier:#x}, key1={key1:#x}")
        data = [
            0x57, 0xAB, 0x00,
            key_group, 0x08,
            modifier, 0x00,
            key1, key2, key3, key4, key5, key6
        ]
        packet = self._create_packet(data, True)
        self._send_packet(packet)

    def key_up_all(self, key_group: KeyGroup = KeyGroup.CharKey) -> None:
        if key_group == KeyGroup.CharKey:
            self._send_packet(self.CHAR_KEY_UP_PACKET)
        else:
            self._send_packet(self.MEDIA_KEY_UP_PACKET)

    def key_type(
        self,
        modifier: int,
        key: int,
        key2: int = 0,
        key3: int = 0,
        key4: int = 0,
        key5: int = 0,
        key6: int = 0,
    ) -> None:
        import time
        self.key_down(KeyGroup.CharKey, modifier, key, key2, key3, key4, key5, key6)
        time.sleep(0.02)
        self.key_up_all(KeyGroup.CharKey)

    def media_key(self, media_key: tuple) -> None:
        self.key_down(KeyGroup.MediaKey, media_key[0], media_key[1], media_key[2], media_key[3])
        self.key_up_all(KeyGroup.MediaKey)

    def mouse_move_rel(self, x: int, y: int) -> None:
        if self._is_moving:
            return

        x = max(-128, min(127, x))
        y = max(-128, min(127, y))
        if x < 0:
            x = 0x100 + x
        if y < 0:
            y = 0x100 + y

        data = [
            0x57, 0xAB, 0x00,
            CommandCode.SEND_MS_REL_DATA, 0x05,
            0x01, self.left_status,
            x & 0xFF, y & 0xFF, 0x00
        ]
        packet = self._create_packet(data, True)
        self._is_moving = True
        self._send_packet(packet)

    def mouse_move_abs(self, x: int, y: int, screen_width: int = 1920, screen_height: int = 1080) -> None:
        """Move mouse to absolute position."""
        max_coord = 4096
        
        norm_x = int((x / screen_width) * max_coord) if screen_width > 0 else 0
        norm_y = int((y / screen_height) * max_coord) if screen_height > 0 else 0
        
        norm_x = max(0, min(max_coord - 1, norm_x))
        norm_y = max(0, min(max_coord - 1, norm_y))
        
        HEAD = bytes([0x57, 0xAB])
        ADDR = bytes([0x00])
        CMD = bytes([0x04])
        LEN = bytes([0x07])
        DATA = bytearray([0x02])
        
        DATA.append(self.left_status)
        DATA += norm_x.to_bytes(2, byteorder='little')
        DATA += norm_y.to_bytes(2, byteorder='little')
        
        while len(DATA) < 7:
            DATA.append(0)
        DATA = DATA[:7]
        
        HEAD_sum = sum(HEAD)
        DATA_sum = sum(DATA)
        SUM = (HEAD_sum + int.from_bytes(ADDR, 'big') + int.from_bytes(CMD, 'big') + int.from_bytes(LEN, 'big') + DATA_sum) & 0xFF
        
        packet = HEAD + ADDR + CMD + LEN + DATA + bytes([SUM])
        if self.debug:
            print(f"[CH9329] ABS: x={x}/{screen_width}, y={y}/{screen_height} -> {norm_x},{norm_y} | packet={packet.hex()}")
        self._send_packet(packet)

    def mouse_button_down(self, button: int) -> None:
        if button == 0x01:
            self.left_status = 1

        data = [
            0x57, 0xAB, 0x00,
            CommandCode.SEND_MS_REL_DATA, 0x05,
            0x01, button, 0x00, 0x00, 0x00
        ]
        packet = self._create_packet(data, True)
        self._send_packet(packet)

    def mouse_button_up_all(self) -> None:
        self.left_status = 0
        packet = bytes([0x57, 0xAB, 0x00, 0x05, 0x05, 0x01, 0x00, 0x00, 0x00, 0x00, 0x0D])
        self._send_packet(packet)

    def mouse_scroll(self, delta: int) -> None:
        scroll = 1 if delta > 0 else -1
        if scroll < 0:
            scroll = 0x100 + scroll

        data = [
            0x57, 0xAB, 0x00,
            CommandCode.SEND_MS_REL_DATA, 0x05,
            0x01, 0x00, 0x00, 0x00, scroll & 0xFF
        ]
        packet = self._create_packet(data, True)
        self._send_packet(packet)

    @property
    def is_moving(self) -> bool:
        return self._is_moving
