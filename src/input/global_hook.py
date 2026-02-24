"""Global keyboard and mouse input hook using pynput."""

import sys
import platform
from typing import Callable, Optional, Union
from dataclasses import dataclass
from enum import IntEnum


@dataclass
class KeyEvent:
    keycode: int
    is_press: bool
    modifier: int = 0


@dataclass
class MouseEvent:
    x: int
    y: int
    button: int = 0
    is_press: bool = False
    is_release: bool = False
    scroll_delta: int = 0


InputCallback = Callable[[Union[KeyEvent, MouseEvent]], None]


class KeyCode(IntEnum):
    CTRL_L = 0xE0
    SHIFT_L = 0xE1
    ALT_L = 0xE2
    WIN_L = 0xE3
    CTRL_R = 0xE4
    SHIFT_R = 0xE5
    ALT_R = 0xE6
    WIN_R = 0xE7


class PermissionError(Exception):
    """Raised when accessibility permission is not granted."""
    pass


class GlobalInputHook:
    def __init__(self):
        self._keyboard_listener = None
        self._mouse_listener = None
        self._callback: Optional[InputCallback] = None
        self._modifier_state = 0
        self._is_active = False
        
        self._keyboard = None
        self._mouse = None
        self._Key = None
        self._Button = None
        self._KeyCode = None
        
        self._init_pynput()

    def _init_pynput(self):
        try:
            from pynput import keyboard, mouse
            self._keyboard = keyboard
            self._mouse = mouse
            self._Key = keyboard.Key
            self._Button = mouse.Button
            self._KeyCode = keyboard.KeyCode
        except ImportError:
            raise PermissionError("pynput not installed")

        self.MODIFIER_MAP = {
            self._Key.ctrl_l: KeyCode.CTRL_L,
            self._Key.ctrl_r: KeyCode.CTRL_R,
            self._Key.shift_l: KeyCode.SHIFT_L,
            self._Key.shift_r: KeyCode.SHIFT_R,
            self._Key.alt_l: KeyCode.ALT_L,
            self._Key.alt_r: KeyCode.ALT_R,
            self._Key.cmd: KeyCode.WIN_L,
            self._Key.cmd_r: KeyCode.WIN_R,
        }

        self.BUTTON_MAP = {
            self._Button.left: 0x01,
            self._Button.right: 0x02,
            self._Button.middle: 0x04,
        }

        self.KEY_MAP = {}
        for i, c in enumerate('abcdefghijklmnopqrstuvwxyz'):
            try:
                self.KEY_MAP[self._KeyCode.from_char(c)] = 0x04 + i
            except:
                pass
        for i, c in enumerate('1234567890'):
            try:
                self.KEY_MAP[self._KeyCode.from_char(c)] = 0x1E + i
            except:
                pass

        self.SPECIAL_KEY_MAP = {
            self._Key.enter: 0x28,
            self._Key.esc: 0x29,
            self._Key.backspace: 0x2A,
            self._Key.tab: 0x2B,
            self._Key.space: 0x2C,
            self._Key.caps_lock: 0x39,
            self._Key.f1: 0x3A,
            self._Key.f2: 0x3B,
            self._Key.f3: 0x3C,
            self._Key.f4: 0x3D,
            self._Key.f5: 0x3E,
            self._Key.f6: 0x3F,
            self._Key.f7: 0x40,
            self._Key.f8: 0x41,
            self._Key.f9: 0x42,
            self._Key.f10: 0x43,
            self._Key.f11: 0x44,
            self._Key.f12: 0x45,
            self._Key.home: 0x4A,
            self._Key.page_up: 0x4B,
            self._Key.delete: 0x4C,
            self._Key.end: 0x4D,
            self._Key.page_down: 0x4E,
            self._Key.right: 0x4F,
            self._Key.left: 0x50,
            self._Key.down: 0x51,
            self._Key.up: 0x52,
        }

    def set_callback(self, callback: InputCallback) -> None:
        self._callback = callback

    def start(self) -> None:
        if platform.system() == "Darwin":
            self._check_macos_permission()

        try:
            self._keyboard_listener = self._keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release
            )
            self._mouse_listener = self._mouse.Listener(
                on_move=self._on_mouse_move,
                on_click=self._on_mouse_click,
                on_scroll=self._on_mouse_scroll
            )
            self._keyboard_listener.start()
            self._mouse_listener.start()
            self._is_active = True
        except Exception as e:
            raise PermissionError(f"Failed to start input listeners: {e}")

    def _check_macos_permission(self):
        try:
            from AppKit import NSWorkspace
            import Quartz
            
            options = Quartz.kAXValueCGPointType
            result = Quartz.AXIsProcessTrusted()
            
            if not result:
                raise PermissionError(
                    "macOS Accessibility permission required.\n\n"
                    "Please go to:\n"
                    "System Preferences → Privacy & Security → Accessibility\n"
                    "and add Terminal (or your Python app) to the list."
                )
        except ImportError:
            pass

    def stop(self) -> None:
        self._is_active = False
        if self._keyboard_listener:
            try:
                self._keyboard_listener.stop()
            except:
                pass
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except:
                pass

    def is_active(self) -> bool:
        return self._is_active

    def _on_key_press(self, key) -> None:
        if not self._is_active or not self._callback:
            return

        modifier = self._update_modifier(key, True)
        keycode = self._get_keycode(key)

        if keycode:
            event = KeyEvent(keycode=keycode, is_press=True, modifier=modifier)
            self._callback(event)

    def _on_key_release(self, key) -> None:
        if not self._is_active or not self._callback:
            return

        self._update_modifier(key, False)

        keycode = self._get_keycode(key)
        if keycode:
            event = KeyEvent(keycode=keycode, is_press=False, modifier=self._modifier_state)
            self._callback(event)

    def _on_mouse_move(self, x: int, y: int) -> None:
        if not self._is_active or not self._callback:
            return

        event = MouseEvent(x=x, y=y)
        self._callback(event)

    def _on_mouse_click(self, x: int, y: int, button, pressed: bool) -> None:
        if not self._is_active or not self._callback:
            return

        button_code = self.BUTTON_MAP.get(button, 0)
        event = MouseEvent(
            x=x, y=y,
            button=button_code,
            is_press=pressed,
            is_release=not pressed
        )
        self._callback(event)

    def _on_mouse_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        if not self._is_active or not self._callback:
            return

        event = MouseEvent(x=x, y=y, scroll_delta=dy)
        self._callback(event)

    def _update_modifier(self, key, is_press: bool) -> int:
        mod_code = self.MODIFIER_MAP.get(key)
        if mod_code:
            bit_position = mod_code - KeyCode.CTRL_L
            if is_press:
                self._modifier_state |= (1 << bit_position)
            else:
                self._modifier_state &= ~(1 << bit_position)
        return self._modifier_state

    def _get_keycode(self, key) -> int:
        if key in self.SPECIAL_KEY_MAP:
            return self.SPECIAL_KEY_MAP[key]
        if key in self.KEY_MAP:
            return self.KEY_MAP[key]
        if isinstance(key, self._KeyCode):
            char = key.char
            if char:
                char_lower = char.lower()
                if char_lower in 'abcdefghijklmnopqrstuvwxyz0123456789':
                    try:
                        return self.KEY_MAP.get(self._KeyCode.from_char(char_lower), 0)
                    except Exception:
                        pass
        return 0

    def get_modifier_state(self) -> int:
        return self._modifier_state
