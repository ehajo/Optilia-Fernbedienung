# main.py - Hauptschleife und Programmfluss

import time
import json
import wifi
from config import ZOOM_DEBOUNCE, BRIGHTNESS_DEBOUNCE, TWITCH_ZOOM_TIMEOUT, DISPLAY_WIDTH, DISPLAY_HEIGHT
from hardware_setup import setup_hardware
from visca_commands import ViscaCamera
from twitch_integration import TwitchController

# Zustandsmaschine
class SystemState:
    OFF = 0
    MANUAL = 1
    TWITCH = 2

# Zwei 8x8 Bitmaps für den Twitch- und Wifi-Status (Smiley)
laughing_smiley = bytearray([
    0x3C, 0x42, 0xA5, 0x81, 0xA5, 0x99, 0x42, 0x3C
])
sad_smiley = bytearray([
    0x3C, 0x42, 0xA5, 0x81, 0x99, 0xA5, 0x42, 0x3C
])

# Secrets laden
with open("secrets.json", "r") as f:
    secrets = json.load(f)

# Hardware initialisieren
pins, uart, i2c, oled, encoder, poti = setup_hardware()

# Boot-Meldung auf OLED anzeigen
oled.fill(0)
oled.text("Booting...", 0, 0, 1)
oled.show()

# WiFi verbinden
print("WiFi verbinden...")
oled.text("WiFi verbinden...", 0, 10, 1)
oled.show()
try:
    wifi.radio.connect(secrets["wifi"]["ssid"], secrets["wifi"]["password"])
    wifi_connected = True
    oled.text("WiFi OK", 0, 20, 1)
    print("Verbunden mit WiFi. IP:", wifi.radio.ipv4_address)
except Exception as e:
    wifi_connected = False
    oled.text("Kein WiFi!", 0, 20, 1)
    print("WiFi-Verbindung fehlgeschlagen:", e)
oled.show()
time.sleep(1)  # Wartezeit hier, um die WiFi-Meldung sichtbar zu halten

oled.text("Initialisiere...", 0, 30, 1)
oled.show()

# VISCA und Twitch initialisieren
visca_camera = ViscaCamera(uart)
twitch = TwitchController(oled, secrets) if wifi_connected else None

oled.text("Initialisiert!", 0, 40, 1)
oled.show()
time.sleep(0.5)  # Kurze Wartezeit für die zusätzliche Meldung

# Kamera ausschalten nach Initialisierung (OFF-Zustand)
visca_camera.set_power(False)

# Display nach Bootvorgang leeren
oled.fill(0)
oled.show()

# Zustandsvariablen
state = SystemState.OFF
last_button_states = {key: True for key in ["power_button", "connected_button", "focus_button", "freeze_button"]}
last_zoom_time = 0
last_brightness_time = 0
zoom_override = None
zoom_timeout = 0
brightness = 4  # Standardwert 4
encoder.position = 4  # Encoder-Wert initial auf 4 setzen
last_encoder_position = encoder.position  # Initialer Encoder-Wert
last_display_state = None

# Initialzustand der LEDs setzen
pins["power_led_red"].value = True
pins["power_led_green"].value = False
pins["connected_led_red"].value = False
pins["connected_led_green"].value = False
pins["autofocus_led_green"].value = False
pins["autofocus_led_red"].value = False
pins["freeze_led_green"].value = False
pins["freeze_led_red"].value = False

# Funktion zum Zeichnen von Bitmaps (nur für Smileys)
def draw_bitmap(bitmap, x, y, width=8, height=8):
    for j in range(height):
        row = bitmap[j]
        for i in range(width):
            if row & (1 << (width - 1 - i)):
                oled.pixel(x + i, y + j, 1)
            else:
                oled.pixel(x + i, y + j, 0)

# Display-Funktionen
def update_display(zoom, autofocus, freeze, override, brightness):
    global last_display_state
    current_state = (state, zoom, autofocus, freeze, override, brightness, wifi_connected, twitch.connected if twitch else False)
    if current_state != last_display_state:
        oled.fill(0)
        if state != SystemState.OFF:
            oled.text("Freeze" if freeze else "Live", 0, 0, 1)
            oled.text("AF" if autofocus else "MF", 0, DISPLAY_HEIGHT-10, 1)
            oled.text(f"Bright: {brightness}", 50, DISPLAY_HEIGHT-30, 1)
            oled.text(f"Zoom: {zoom}x", 50, DISPLAY_HEIGHT-20, 1)
            oled.text("Twitch" if override else "Manual", 50, DISPLAY_HEIGHT-10, 1)
            # WiFi- und Twitch-Status rechts oben als grafische Smileys
            oled.text("wifi:", DISPLAY_WIDTH - 60, 0, 1)
            draw_bitmap(laughing_smiley if wifi_connected else sad_smiley, DISPLAY_WIDTH - 16, 0)
            oled.text("twitch:", DISPLAY_WIDTH - 60, 10, 1)
            draw_bitmap(laughing_smiley if twitch and twitch.connected else sad_smiley, DISPLAY_WIDTH - 16, 8)
        oled.show()
        last_display_state = current_state

def scale_adc_to_zoom(adc_value):
    return 30 - int((adc_value / 65535) * 29)

# Hauptschleife
while True:
    # Power-Button
    if not pins["power_button"].value and last_button_states["power_button"]:
        print("Power-Taster erkannt")
        state = SystemState.MANUAL if state == SystemState.OFF else SystemState.OFF
        visca_camera.set_power(state != SystemState.OFF)
        pins["power_led_green"].value = state != SystemState.OFF
        pins["power_led_red"].value = state == SystemState.OFF
        print(f"Power State: {state}")
        if state == SystemState.OFF:
            oled.fill(0)
            oled.show()
            # Alle LEDs im OFF-Zustand ausschalten
            pins["freeze_led_green"].value = False
            pins["freeze_led_red"].value = False
            pins["autofocus_led_green"].value = False
            pins["autofocus_led_red"].value = False
            pins["connected_led_green"].value = False
            pins["connected_led_red"].value = False
        else:
            # Grüne LEDs für Freeze, AF und Connected zu Beginn an
            visca_camera.set_freeze(False)
            pins["freeze_led_green"].value = True
            pins["freeze_led_red"].value = False
            visca_camera.set_autofocus(True)
            pins["autofocus_led_green"].value = True
            pins["autofocus_led_red"].value = False
            pins["connected_led_green"].value = True
            pins["connected_led_red"].value = False
            # Brightness und Encoder auf Standardwert 4 setzen
            brightness = 4
            encoder.position = 4
            last_encoder_position = 4
            visca_camera.set_brightness(brightness)
            # Display sofort aktualisieren
            last_display_state = None
            update_display(scale_adc_to_zoom(poti.value), visca_camera.autofocus, visca_camera.freeze, zoom_override is not None, brightness)
        time.sleep(0.1)  # Entprellung

    # Connected-Button
    if state != SystemState.OFF and not pins["connected_button"].value and last_button_states["connected_button"]:
        print("Connected-Taster erkannt")
        pins["connected_led_red"].value = True
        state = SystemState.TWITCH if state == SystemState.MANUAL else SystemState.MANUAL
        if state == SystemState.TWITCH and wifi_connected and twitch:
            twitch.connect()
        elif twitch:
            twitch.disconnect()
        # LEDs basierend auf Twitch-Verbindung setzen
        if twitch and twitch.connected:
            pins["connected_led_green"].value = False
            pins["connected_led_red"].value = True
        else:
            pins["connected_led_green"].value = True
            pins["connected_led_red"].value = False
        print(f"Connected State: {state}")
        time.sleep(0.1)  # Entprellung

    if state != SystemState.OFF:
        # Twitch-Nachrichten prüfen
        if state == SystemState.TWITCH and wifi_connected and twitch:
            result = twitch.check_messages()
            if result:
                zoom_override, viewer = result
                zoom_timeout = time.monotonic() + TWITCH_ZOOM_TIMEOUT
                visca_camera.set_overlay_text(viewer)
            # LEDs für Connected-Button aktualisieren
            if twitch.connected:
                pins["connected_led_green"].value = False
                pins["connected_led_red"].value = True
            else:
                pins["connected_led_green"].value = True
                pins["connected_led_red"].value = False

        current_time = time.monotonic()
        if zoom_override and current_time > zoom_timeout:
            zoom_override = None
            visca_camera.set_overlay_text("")

        zoom = zoom_override if zoom_override else scale_adc_to_zoom(poti.value)
        if current_time - last_zoom_time > ZOOM_DEBOUNCE:
            visca_camera.set_zoom(zoom)
            last_zoom_time = current_time

        new_brightness = encoder.position
        if new_brightness != last_encoder_position and current_time - last_brightness_time > BRIGHTNESS_DEBOUNCE:
            brightness = max(0, min(20, new_brightness))  # Maximalwert auf 20 beschränkt
            visca_camera.set_brightness(brightness)
            last_brightness_time = current_time
            last_encoder_position = new_brightness

        # Focus-Button
        if not pins["focus_button"].value and last_button_states["focus_button"]:
            print("Focus-Taster erkannt")
            visca_camera.set_autofocus(not visca_camera.autofocus)
            pins["autofocus_led_green"].value = visca_camera.autofocus
            pins["autofocus_led_red"].value = not visca_camera.autofocus
            time.sleep(0.1)  # Entprellung

        # Freeze-Button
        if not pins["freeze_button"].value and last_button_states["freeze_button"]:
            print("Freeze-Taster erkannt")
            visca_camera.set_freeze(not visca_camera.freeze)
            pins["freeze_led_green"].value = not visca_camera.freeze
            pins["freeze_led_red"].value = visca_camera.freeze
            time.sleep(0.1)  # Entprellung

        update_display(zoom, visca_camera.autofocus, visca_camera.freeze, zoom_override is not None, brightness)

    # Button-States aktualisieren
    for key in last_button_states:
        last_button_states[key] = pins[key].value

    time.sleep(0.05)