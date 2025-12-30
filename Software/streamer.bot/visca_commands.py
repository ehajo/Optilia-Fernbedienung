# visca_commands.py - VISCA-Befehle und Kamerasteuerung

import busio
import time
from config import ZOOM_LEVELS

class ViscaCamera:
    def __init__(self, uart):
        self.uart = uart
        self.autofocus = True
        self.freeze = False
        self.power = False

    # Zeichentabelle für VISCA-Text
    VISCA_CHARS = {
        'A': 0x00, 'B': 0x01, 'C': 0x02, 'D': 0x03, 'E': 0x04, 'F': 0x05, 'G': 0x06, 'H': 0x07,
        'I': 0x08, 'J': 0x09, 'K': 0x0A, 'L': 0x0B, 'M': 0x0C, 'N': 0x0D, 'O': 0x0E, 'P': 0x0F,
        'Q': 0x10, 'R': 0x11, 'S': 0x12, 'T': 0x13, 'U': 0x14, 'V': 0x15, 'W': 0x16, 'X': 0x17,
        'Y': 0x18, 'Z': 0x19, '&': 0x1A, '?': 0x1C, '!': 0x1D, '1': 0x1E, '2': 0x1F, '3': 0x20,
        '4': 0x21, '5': 0x22, '6': 0x23, '7': 0x24, '8': 0x25, '9': 0x26, '0': 0x27, 'À': 0x28,
        'È': 0x29, 'Ì': 0x2A, 'Ò': 0x2B, 'Ù': 0x2C, 'Á': 0x2D, 'É': 0x2E, 'Í': 0x2F, 'Ó': 0x30,
        'Ú': 0x31, 'Â': 0x32, 'Ê': 0x33, 'Ô': 0x34, 'Æ': 0x35, 'Ã': 0x37, 'Õ': 0x38, 'Ñ': 0x39,
        'Ç': 0x3A, 'ß': 0x3B, 'Ä': 0x3C, 'Ï': 0x3D, 'Ö': 0x3E, 'Ü': 0x3F, 'Å': 0x40, '$': 0x41,
        ' ': 0x42, '¥': 0x43, '£': 0x45, '¿': 0x46, '¡': 0x47, 'Ø': 0x48, '“': 0x49, ':': 0x4A,
        "'": 0x4B, '.': 0x4C, ',': 0x4D, '/': 0x4E, '-': 0x4F
    }

    def send_command(self, cmd_data):
        """Sendet einen VISCA-Befehl an die Kamera."""
        cmd = bytearray([0x81, 0x01, 0x04])
        cmd.extend(cmd_data)
        cmd.append(0xFF)
        self.uart.write(cmd)

    def set_overlay_text(self, text, line=0x10, x_pos=0x00, color=0x00, blink=0x00):
        """Setzt Overlay-Text in einer bestimmten Zeile mit drei Befehlen."""
        if len(text) > 10:
            text = text[:10]
        text_bytes = bytearray([self.VISCA_CHARS.get(char, 0x42) for char in text.upper()])
        text_block = text_bytes + bytearray([0x42] * (10 - len(text_bytes)))

        self.send_command([0x74, 0x2F])
        print(f"Sende Overlay-Aktivierungsbefehl: ['0x81', '0x1', '0x4', '0x74', '0x2f', '0xff']")

        cmd1 = bytearray([0x81, 0x01, 0x04, 0x73, line, 0x00, x_pos, color, blink, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF])
        self.uart.write(cmd1)
        print(f"Sende Einstellungs-Befehl: {[hex(b) for b in cmd1]}")

        cmd2 = bytearray([0x81, 0x01, 0x04, 0x73, line + 0x10])
        cmd2.extend(text_block)
        cmd2.append(0xFF)
        self.uart.write(cmd2)
        print(f"Sende Textblock 1: {[hex(b) for b in cmd2]}")

        cmd3 = bytearray([0x81, 0x01, 0x04, 0x73, line + 0x20])
        cmd3.extend(bytearray([0x42] * 10))
        cmd3.append(0xFF)
        self.uart.write(cmd3)
        print(f"Sende Textblock 2: {[hex(b) for b in cmd3]}")

    def set_zoom_level(self, zoom, line=0x1A, x_pos=0x00):
        """Setzt die Zoomstufe in der letzten Zeile (0x1A), linksbündig."""
        self.set_overlay_text(f"{zoom}x", line=line, x_pos=x_pos)

    def set_power(self, on: bool):
        self.power = on
        self.send_command([0x00, 0x02 if on else 0x03])
        if on:
            time.sleep(5)
            print("On-State Standardwerte an Kamera schicken...")
            self.send_command([0x74, 0x1F])
            self.send_command([0x59, 0x03])
            self.send_command([0x39, 0x00])
            self.send_command([0x3E, 0x02])
            self.send_command([0x4E, 0x00, 0x00, 0x00, 0x04])
            self.send_command([0x35, 0x07])
            self.send_command([0x62, 0x03])
            self.send_command([0x38, 0x02])

    def set_zoom(self, zoom):
        """Setzt den Objektiv-Zoom auf Stufe 1..30 per VISCA 'Zoom Direct'."""
        try:
            z = int(zoom)
        except Exception:
            return
        if z < 1: z = 1
        if z > 30: z = 30
        code = ZOOM_LEVELS.get(z)
        if code is None:
            return
        p = (code >> 12) & 0x0F
        q = (code >> 8) & 0x0F
        r = (code >> 4) & 0x0F
        s = code & 0x0F
        cmd = bytearray([0x81, 0x01, 0x04, 0x47, p, q, r, s, 0xFF])
        self.uart.write(cmd)

    def set_brightness(self, brightness):
        high = (brightness >> 4) & 0x0F
        low = brightness & 0x0F
        self.send_command([0x4E, 0x00, 0x00, high, low])

    def set_whitebalance(self, whitebalance):
        cmd = bytearray([0x81, 0x01, 0x04, 0x35, whitebalance, 0xFF])
        self.uart.write(cmd)

    def set_autofocus(self, autofocus_on):
        cmd = bytearray([0x81, 0x01, 0x04, 0x38, 0x02 if autofocus_on else 0x03, 0xFF])
        self.uart.write(cmd)
        self.autofocus = autofocus_on

    def set_freeze(self, is_freeze: bool):
        self.freeze = is_freeze
        self.send_command([0x62, 0x02 if is_freeze else 0x03])
        if is_freeze:
            self.set_overlay_text("FREEZE", line=0x10)
        else:
            self.set_overlay_text("", line=0x10)