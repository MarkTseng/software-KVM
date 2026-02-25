# Software KVM

Cross-platform KVM software using CH9329 and video capture card.

## Features

- Control remote PC keyboard and mouse via CH9329 USB module
- Display remote PC screen via MS2130 video capture card
- BIOS-level access (no driver required on remote device)
- Cross-platform support (Windows, macOS, Linux)

## Hardware Requirements

- **Video Capture**: MS2130-based HDMI capture card (USB) or any UVC device
- **Keyboard/Mouse**: CH9329 + CH340 USB-to-Serial module

Find cables on:
- eBay: "CH9329/CH340 KVM USB Cable"
- AliExpress: "ch9329+ch340uart"

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python -m src.main
```

## Controls

- **Middle Mouse Button**: Exit remote session

## Connection Diagram

<img width="1024" height="1024" alt="KVM-connect" src="https://github.com/user-attachments/assets/046c4a7a-d896-4ffa-85b2-3bd6de256d77" />


## Referance SW KVM link
- [Control3](https://github.com/sipper69/Control3)
- [SubConsole](https://github.com/ikemax2/SubConsole) 
