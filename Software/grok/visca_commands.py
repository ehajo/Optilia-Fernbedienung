# visca_commands.py - VISCA-Befehle und Kamerasteuerung

import busio
import time
from config import ZOOM_LEVELS

class ViscaCamera:
    def __init__(self, uart: busio.UART):
        self.uart = uart
        self.autofocus = True
        self.freeze = False
        self.power = False

    def send_command(self, command_bytes):
        command = [0x81, 0x01, 0x04] + command_bytes + [0xFF]
        self.uart.write(bytearray(command))

    def set_power(self, on: bool):
        self.power = on
        self.send_command([0x00, 0x02 if on else 0x03])
        if on:
            # Standard-Einstellungen bei Einschalten
            time.sleep(5) # Kurz warten, bis die Kamera gestartet ist
            print("On-State Standardwerte an Kamera schicken...")
            self.send_command([0x74, 0x1F])  # Textpuffer löschen
            self.send_command([0x59, 0x03])  # Spot AE off
            self.send_command([0x39, 0x00])  # Brightness Auto
            self.send_command([0x3E, 0x02])  # Exposure Comp On
            self.send_command([0x4E, 0x00, 0x00, 0x00, 0x04])  # exp fix
            self.send_command([0x35, 0x03])  # Weißabgleich OnePush
            self.send_command([0x62, 0x03])  # Freeze off
            self.send_command([0x38, 0x02])  # Autofokus ein

    def set_zoom(self, zoom_value: int):
        visca_val = ZOOM_LEVELS.get(zoom_value, 0x0000)
        self.send_command([
            0x47,
            (visca_val >> 12) & 0x0F,
            (visca_val >> 8) & 0x0F,
            (visca_val >> 4) & 0x0F,
            visca_val & 0x0F
        ])

    def set_brightness(self, brightness: int):
        high = (brightness >> 4) & 0x0F
        low = brightness & 0x0F
        self.send_command([0x4E, 0x00, 0x00, high, low])

    def set_freeze(self, is_freeze: bool):
        self.freeze = is_freeze
        self.send_command([0x74, 0x2F])
        if is_freeze:
            self.send_command([0x73, 0x10, 0x00, 0x0A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
            self.send_command([0x73, 0x20, 0x42, 0x42, 0x42, 0x42, 0x05, 0x11, 0x04, 0x04, 0x19, 0x04])
            self.send_command([0x62, 0x02])
        else:
            self.send_command([0x73, 0x20, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42])
            self.send_command([0x62, 0x03])

    def set_autofocus(self, enabled: bool):
        self.autofocus = enabled
        self.send_command([0x38, 0x02 if enabled else 0x03])

    def set_overlay_text(self, viewer_name: str):
        full_text = viewer_name.upper()
        def convert_char(ch):
            if 'A' <= ch <= 'Z': return ord(ch) - ord('A')
            elif '1' <= ch <= '9': return (ord(ch) - ord('1')) + 0x1e
            elif ch == '0': return 0x27
            else: return 0x42
        converted = [convert_char(ch) for ch in full_text]
        if len(converted) < 20:
            converted.extend([0x42] * (20 - len(converted)))
        else:
            converted = converted[:20]
        first_half = converted[:10]
        second_half = converted[10:]
        self.send_command([0x74, 0x2F])
        self.send_command([0x73, 0x10] + first_half)
        self.send_command([0x73, 0x30] + second_half)