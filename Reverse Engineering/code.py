import time
import board
import busio
import analogio

# UART-Verbindung einrichten (TX = GP4, RX = GP5)
uart = busio.UART(tx=board.GP4, rx=board.GP5, baudrate=9600, timeout=1)

# Potentiometer-Setup (analoger Eingang, z. B. GP26/ADC0)
poti = analogio.AnalogIn(board.A0)  # GPIO26 = ADC0

# Zoomstufen-Definitionen (HEX) für VISCA-Befehle
ZOOM_LEVELS = {
    1: 0x0000,
    2: 0x16A1,
    3: 0x2063,
    4: 0x2628,
    5: 0x2A1D,
    6: 0x2D13,
    7: 0x2F6D,
    8: 0x3161,
    9: 0x330D,
    10: 0x3486,
    11: 0x35D7,
    12: 0x3709,
    13: 0x3820,
    14: 0x3920,
    15: 0x3A0A,
    16: 0x3ADD,
    17: 0x3B9C,
    18: 0x3C46,
    19: 0x3CDC,
    20: 0x3D60,
    21: 0x3D9C,
    22: 0x3DD8,
    23: 0x3E14,
    24: 0x3E50,
    25: 0x3E8C,
    26: 0x3EC8,
    27: 0x3F04,
    28: 0x3F40,
    29: 0x3F7C,
    30: 0x3FFF,
}

# Funktion zur Erzeugung eines VISCA-Befehls für eine beliebige Zoomstufe
def get_zoom_command_from_level(level):
    if level not in ZOOM_LEVELS:
        raise ValueError(f"Zoomstufe {level} ist nicht definiert.")
    zoom_value_hex = ZOOM_LEVELS[level]
    return [
        0x81,  # Header (Adresse)
        0x01,  # Command Type
        0x04,  # Category (Lens)
        0x47,  # Command (Zoom Absolute Position)
        (zoom_value_hex >> 12) & 0x0F,  # High nibble von Byte 1
        (zoom_value_hex >> 8) & 0x0F,   # Low nibble von Byte 1
        (zoom_value_hex >> 4) & 0x0F,   # High nibble von Byte 2
        zoom_value_hex & 0x0F,          # Low nibble von Byte 2
        0xFF   # Terminator
    ]

# Funktion, um einen Zoombefehl über UART zu senden
def send_zoom_command(level):
    command = get_zoom_command_from_level(level)
    uart.write(bytearray(command))
    print(f"Zoom auf {level}x gesendet: {command}")


# Hauptprogramm: Steuerung mit Rückmeldungsanalyse
# Autofokus einschalten:
uart.write(bytearray([0x81,0x01,0x04,0x38,0x02,0xFF]))
last_zoom_level = None
while True:
    # Zoomstufe berechnen und senden
    current_adc_value = poti.value
    current_zoom_level = int((current_adc_value / 65535) * 30) + 1
    if current_zoom_level != last_zoom_level:
        send_zoom_command(current_zoom_level)
        last_zoom_level = current_zoom_level

    
    time.sleep(0.2)  # Kurze Verzögerung für Stabilität
