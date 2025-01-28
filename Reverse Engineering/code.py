import time
import board
import busio
import analogio
import digitalio
from adafruit_ssd1306 import SSD1306_I2C

# I2C-Setup für das OLED-Display (SCL=GP1, SDA=GP0)
i2c = busio.I2C(scl=board.GP1, sda=board.GP0)  # SCL=GP1, SDA=GP0
WIDTH = 128
HEIGHT = 64

# OLED-Display initialisieren
oled = SSD1306_I2C(WIDTH, HEIGHT, i2c)

# UART-Verbindung einrichten (für die Kamera, TX=GP4, RX=GP5)
uart = busio.UART(tx=board.GP4, rx=board.GP5, baudrate=9600, timeout=1)

# Potentiometer-Setup (analoger Eingang, z. B. GP26/ADC0)
poti = analogio.AnalogIn(board.A0)  # GPIO26 = ADC0

# Taste für Autofokus-Umschaltung (an GP16, gegen Masse schaltend)
focus_button = digitalio.DigitalInOut(board.GP16)
focus_button.direction = digitalio.Direction.INPUT
focus_button.pull = digitalio.Pull.UP  # Interner Pull-Up-Widerstand

# LEDs für Autofokus-Anzeige
green_led = digitalio.DigitalInOut(board.GP17)  # Autofokus EIN
green_led.direction = digitalio.Direction.OUTPUT

red_led = digitalio.DigitalInOut(board.GP18)  # Autofokus AUS
red_led.direction = digitalio.Direction.OUTPUT

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

# Autofokus-Befehle
AUTOFOCUS_ON = [0x81, 0x01, 0x04, 0x38, 0x02, 0xFF]
AUTOFOCUS_OFF = [0x81, 0x01, 0x04, 0x38, 0x03, 0xFF]

# Funktion: Ladeanimation anzeigen
def show_loading_animation():
    oled.fill(0)
    oled.text("System startet...", 10, 10, 1)
    oled.show()
    for i in range(0, 128, 8):  # Ladebalken in Schritten von 8 Pixeln
        oled.fill_rect(0, 30, i, 10, 1)  # Rechteck für Ladebalken
        oled.show()
        time.sleep(0.625)  # Gesamtdauer: ca. 10 Sekunden
    oled.fill(0)
    oled.text("Bereit!", 40, 30, 1)
    oled.show()
    time.sleep(1)

# Funktion zur Erstellung des VISCA-Befehls für die Zoomstufe
def get_zoom_command(level):
    if level not in ZOOM_LEVELS:
        raise ValueError(f"Zoomstufe {level} ist nicht definiert.")
    zoom_hex = ZOOM_LEVELS[level]
    return [
        0x81,  # Header
        0x01,  # Command Type
        0x04,  # Category (Lens)
        0x47,  # Command (Zoom Absolute Position)
        (zoom_hex >> 12) & 0x0F,  # High nibble Byte 1
        (zoom_hex >> 8) & 0x0F,   # Low nibble Byte 1
        (zoom_hex >> 4) & 0x0F,   # High nibble Byte 2
        zoom_hex & 0x0F,          # Low nibble Byte 2
        0xFF   # Terminator
    ]

# Funktion, um einen Befehl über UART zu senden
def send_command(command):
    uart.write(bytearray(command))
    print(f"Befehl gesendet: {command}")

# Funktion zur Umrechnung des Potentiometerwerts in eine Zoomstufe
def adc_to_zoom_level(adc_value):
    max_zoom = max(ZOOM_LEVELS.keys())
    min_zoom = min(ZOOM_LEVELS.keys())
    # Invertiere die Richtung: Höherer ADC-Wert = kleinerer Zoom
    return int(((65535 - adc_value) / 65535) * (max_zoom - min_zoom) + min_zoom)

# Funktion zur Hysterese auf den ADC-Wert
def apply_hysteresis(adc_value, last_adc_value, hysteresis=1000):
    if last_adc_value is None or abs(adc_value - last_adc_value) > hysteresis:
        return adc_value
    return last_adc_value

# Funktion: Zoomfaktor und Fokusstatus auf dem Display anzeigen
def display_status(zoom_level, is_autofocus):
    oled.fill(0)  # Lösche das Display
    oled.text(f"Zoom: {zoom_level}x", 10, 30, 1)  # Schreibe den Zoom mittig
    focus_text = "AF" if is_autofocus else "MF"  # Autofokusstatus
    oled.text(focus_text, 0, HEIGHT - 10, 1)  # Schreibe AF/MF unten links
    oled.show()  # Aktualisiere das Display

# Funktion zur Umschaltung des Autofokus
def toggle_autofocus(current_focus_state, zoom_level):
    if current_focus_state:  # Autofokus EIN -> AUS schalten
        send_command(AUTOFOCUS_OFF)
        green_led.value = False
        red_led.value = True
    else:  # Autofokus AUS -> EIN schalten
        send_command(AUTOFOCUS_ON)
        green_led.value = True
        red_led.value = False
    display_status(zoom_level, not current_focus_state)  # Aktualisiere den Status
    return not current_focus_state

# Hauptprogramm: Vorbereitung
show_loading_animation()  # Ladeanimation anzeigen
send_command(AUTOFOCUS_ON)  # Autofokus sicherstellen
green_led.value = True
red_led.value = False

# Variablen für Hauptschleife
last_adc_value = None
last_zoom_level = None
autofocus_state = True  # Startzustand: Autofokus EIN

# Hauptprogramm: Steuerung mit Potentiometer, Autofokus und Displayausgabe
while True:
    # Lese den aktuellen ADC-Wert
    current_adc_value = poti.value

    # Wende Hysterese an
    filtered_adc_value = apply_hysteresis(current_adc_value, last_adc_value)

    # Berechne die aktuelle Zoomstufe
    current_zoom_level = adc_to_zoom_level(filtered_adc_value)

    # Aktualisiere, wenn sich die Zoomstufe geändert hat
    if current_zoom_level != last_zoom_level:
        send_command(get_zoom_command(current_zoom_level))  # Sende den Zoom-Befehl
        display_status(current_zoom_level, autofocus_state)  # Zeige Zoom & AF/MF an
        last_zoom_level = current_zoom_level  # Aktualisiere den letzten Zoomwert

    # Prüfe die Taste für Autofokus-Umschaltung
    if not focus_button.value:  # Taste gedrückt (LOW)
        autofocus_state = toggle_autofocus(autofocus_state, current_zoom_level)
        time.sleep(0.5)  # Entprellung der Taste

    # Speichere den letzten ADC-Wert
    last_adc_value = filtered_adc_value

    # Kurze Verzögerung
    time.sleep(0.1)
