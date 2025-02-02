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

# UART-Verbindung für die Kamera (TX=GP4, RX=GP5)
uart = busio.UART(tx=board.GP4, rx=board.GP5, baudrate=9600, timeout=1)

# Potentiometer-Setup (analoger Eingang, z. B. GP26/ADC0)
poti = analogio.AnalogIn(board.A0)  # GPIO26 = ADC0

# Taste für Autofokus-Umschaltung (an GP16, gegen Masse schaltend)
focus_button = digitalio.DigitalInOut(board.GP16)
focus_button.direction = digitalio.Direction.INPUT
focus_button.pull = digitalio.Pull.UP  # Interner Pull-Up-Widerstand

# Taste für Freeze-Umschaltung (an GP19, gegen Masse schaltend)
freeze_button = digitalio.DigitalInOut(board.GP19)
freeze_button.direction = digitalio.Direction.INPUT
freeze_button.pull = digitalio.Pull.UP  # Interner Pull-Up-Widerstand

# LEDs zur Anzeige des Autofokus-Status
autofocus_led_green = digitalio.DigitalInOut(board.GP17)  # Autofokus EIN
autofocus_led_green.direction = digitalio.Direction.OUTPUT

autofocus_led_red = digitalio.DigitalInOut(board.GP18)  # Autofokus AUS
autofocus_led_red.direction = digitalio.Direction.OUTPUT

# LEDs zur Anzeige des Freeze-Status
freeze_led_green = digitalio.DigitalInOut(board.GP20)  # Freeze AUS (Grün)
freeze_led_green.direction = digitalio.Direction.OUTPUT

freeze_led_red = digitalio.DigitalInOut(board.GP21)  # Freeze EIN (Rot)
freeze_led_red.direction = digitalio.Direction.OUTPUT

# Zoomstufen-Definitionen (HEX) für VISCA-Befehle
ZOOM_LEVELS = {
    1: 0x0000, 2: 0x16A1, 3: 0x2063, 4: 0x2628, 5: 0x2A1D,
    6: 0x2D13, 7: 0x2F6D, 8: 0x3161, 9: 0x330D, 10: 0x3486,
    11: 0x35D7, 12: 0x3709, 13: 0x3820, 14: 0x3920, 15: 0x3A0A,
    16: 0x3ADD, 17: 0x3B9C, 18: 0x3C46, 19: 0x3CDC, 20: 0x3D60,
    21: 0x3D9C, 22: 0x3DD8, 23: 0x3E14, 24: 0x3E50, 25: 0x3E8C,
    26: 0x3EC8, 27: 0x3F04, 28: 0x3F40, 29: 0x3F7C, 30: 0x3FFF,
}

# Funktion: VISCA-Befehl mit Header & Endbyte automatisch erstellen
def send_command(command_bytes):
    command = [0x81, 0x01, 0x04] + command_bytes + [0xFF]
    uart.write(bytearray(command))
    print(f"Befehl gesendet: {command}")

# Funktion: Setzt oder entfernt "Freeze" als Overlay auf der Kamera
def set_freeze_overlay(is_freeze):
    """
    Hinweis: Deine hier gewählten Parameter 0x73, 0x10, 0x00, 0x06, ...
    sind nibble-codiert bzw. gerätespezifisch. Wenn du auf der Kamera
    nichts siehst, liegt es oft daran, dass Title Display (OSD) nicht
    eingeschaltet ist oder die Kodierung nicht passt.
    """
    if is_freeze:
        send_command([0x73, 0x10, 0x00, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        send_command([0x73, 0x20, 0x05, 0x11, 0x04, 0x04, 0x19, 0x04, 0x42, 0x42, 0x42, 0x42])
        send_command([0x73, 0x30, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42])
    else:
        # Mit Leerzeichen überschreiben (Text entfernen)
        send_command([0x73, 0x10, 0x00, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        send_command([0x73, 0x20, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42])
        send_command([0x73, 0x30, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42])

# Funktion: Zeigt die aktuelle Zoomstufe und Freeze-Status auf dem OLED-Display
def display_status(zoom_level, is_autofocus, is_freeze):
    oled.fill(0)
    oled.text("Freeze", 0, 0, 1)  # "Freeze" immer anzeigen, Position anpassen
    oled.text(f"Zoom: {zoom_level}x", 10, 30, 1)
    oled.text("AF" if is_autofocus else "MF", 0, HEIGHT - 10, 1)
    oled.show()

# Funktion zur Umschaltung des Autofokus
def toggle_autofocus(current_focus_state, zoom_level, is_freeze):
    if current_focus_state:
        # Autofokus AUS
        send_command([0x38, 0x03])
        autofocus_led_green.value = False
        autofocus_led_red.value = True
    else:
        # Autofokus EIN
        send_command([0x38, 0x02])
        autofocus_led_green.value = True
        autofocus_led_red.value = False
    display_status(zoom_level, not current_focus_state, is_freeze)
    return not current_focus_state

# Funktion zur Umschaltung des Freeze-Modus
def toggle_freeze(current_freeze_state, zoom_level, is_autofocus):

    # Overlay-Text anpassen
    set_freeze_overlay(not current_freeze_state)
    
    if current_freeze_state:
        # Freeze AUS
        send_command([0x62, 0x03])
        freeze_led_green.value = True
        freeze_led_red.value = False
    else:
        # Freeze EIN
        send_command([0x62, 0x02])
        freeze_led_green.value = False
        freeze_led_red.value = True


    # Aktualisiere OLED
    display_status(zoom_level, is_autofocus, not current_freeze_state)
    return not current_freeze_state

# -----------------------------
# Hauptprogramm: Vorbereitung
# -----------------------------

# (1) OSD aktivieren (Titelanzeige ON), damit du deinen Overlay-Text tatsächlich sehen kannst.
send_command([0x74, 0x2F])  # Title Display ON

# Fadenkreuz entfernen
send_command([0x7C, 0x03])

# Autofokus EIN
send_command([0x38, 0x02])
autofocus_led_green.value = True
autofocus_led_red.value = False

# Startzustand: Freeze AUS
freeze_led_green.value = True
freeze_led_red.value = False

last_adc_value = None
last_zoom_level = None
autofocus_state = True
freeze_state = False

# -----------------------------
# Hauptprogramm: Schleife
# -----------------------------
while True:
    current_adc_value = poti.value

    # Wert filtern (primitive Hysterese)
    if last_adc_value is None or abs(current_adc_value - last_adc_value) > 1000:
        filtered_adc_value = current_adc_value
    else:
        filtered_adc_value = last_adc_value

    # Auf Bereich 1..30 abbilden
    current_zoom_level = int(((65535 - filtered_adc_value) / 65535) * 29) + 1

    # Wenn sich die Zoomstufe ändert
    if current_zoom_level != last_zoom_level:
        send_command([
            0x47,
            (ZOOM_LEVELS[current_zoom_level] >> 12) & 0x0F,
            (ZOOM_LEVELS[current_zoom_level] >> 8) & 0x0F,
            (ZOOM_LEVELS[current_zoom_level] >> 4) & 0x0F,
            ZOOM_LEVELS[current_zoom_level] & 0x0F
        ])
        display_status(current_zoom_level, autofocus_state, freeze_state)
        last_zoom_level = current_zoom_level

    # Freeze-Taste
    if not freeze_button.value:
        freeze_state = toggle_freeze(freeze_state, current_zoom_level, autofocus_state)
        time.sleep(0.5)

    # Autofokus-Taste (wenn du sie brauchst, z. B. an focus_button)
    # if not focus_button.value:
    #     autofocus_state = toggle_autofocus(autofocus_state, current_zoom_level, freeze_state)
    #     time.sleep(0.5)

    last_adc_value = filtered_adc_value
    time.sleep(0.1)
