# main.py — Hauptlogik: Hardware, Anzeige, Twitch-Connect, Zoom-Handling
import time
import json
import wifi
import digitalio  # explizit, wie gewünscht

from config import (
    ZOOM_DEBOUNCE,
    BRIGHTNESS_DEBOUNCE,
    TWITCH_ZOOM_TIMEOUT,
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
)
from hardware_setup import setup_hardware
from visca_commands import ViscaCamera
from twitch_integration import TwitchController


class SystemState:
    OFF = 0
    MANUAL = 1
    TWITCH = 2


def twitch_is_connected(tw):
    if not tw:
        return False
    if hasattr(tw, "is_joined"):
        try:
            return bool(tw.is_joined())
        except Exception:
            return False
    return False


def scale_adc_to_zoom(adc_value):
    # Wie bisher: 0..65535 -> 30..1 (invertiert), ganzzahlig 1..30
    return 30 - int((adc_value / 65535) * 29)


# ---------- Setup ----------
pins, uart, i2c, oled, encoder, poti = setup_hardware()
visca = ViscaCamera(uart)

# Secrets
try:
    with open("secrets.json", "r") as f:
        secrets = json.load(f)
except Exception:
    secrets = {}

# WiFi verbinden (optional log)
try:
    if not wifi.radio.connected:
        wifi.radio.connect(secrets["wifi"]["ssid"], secrets["wifi"]["password"])
        print("Verbunden mit WiFi. IP:", wifi.radio.ipv4_address)
except Exception as e:
    print("WiFi-Verbindung fehlgeschlagen:", e)

twitch = TwitchController(oled, secrets)

# LEDs Grundzustand
pins["power_led_green"].value = True
pins["power_led_red"].value = False
pins["connected_led_green"].value = False
pins["connected_led_red"].value = False
pins["autofocus_led_green"].value = True
pins["autofocus_led_red"].value = False
pins["freeze_led_green"].value = True
pins["freeze_led_red"].value = False

# Kamera-Defaults
visca.set_power(True)
visca.set_freeze(False)
visca.set_autofocus(True)
brightness = 4
encoder.position = brightness
visca.set_brightness(brightness)

state = SystemState.MANUAL
last_button = {
    "power_button": pins["power_button"].value,
    "connected_button": pins["connected_button"].value,
    "focus_button": pins["focus_button"].value,
    "freeze_button": pins["freeze_button"].value,
}

last_zoom_sent = None
last_overlay_zoom = None
last_viewer = ""
zoom_override = None
zoom_timeout = 0
last_brightness_time = 0


def update_oled(zoom, autofocus, freeze, in_twitch):
    oled.fill(0)
    oled.text("Live" if not freeze else "Freeze", 0, 0, 1)
    oled.text("AF" if autofocus else "MF", 0, DISPLAY_HEIGHT - 10, 1)
    oled.text(f"Bright: {brightness}", 50, DISPLAY_HEIGHT - 30, 1)
    oled.text(f"Zoom: {zoom}x", 50, DISPLAY_HEIGHT - 20, 1)  # IMMER anzeigen
    oled.text("Twitch" if in_twitch else "Manual", 50, DISPLAY_HEIGHT - 10, 1)
    oled.show()


while True:
    now = time.monotonic()

    # ---------- Power ----------
    if not pins["power_button"].value and last_button["power_button"]:
        if state == SystemState.OFF:
            state = SystemState.MANUAL
            pins["power_led_green"].value = True
            pins["power_led_red"].value = False
            visca.set_power(True)
        else:
            state = SystemState.OFF
            pins["power_led_green"].value = False
            pins["power_led_red"].value = True
            visca.set_power(False)
            twitch.disconnect()
            pins["connected_led_green"].value = False
            pins["connected_led_red"].value = False
            oled.fill(0); oled.show()
        time.sleep(0.1)

    # ---------- Connected (Twitch) ----------
    if state != SystemState.OFF and (not pins["connected_button"].value and last_button["connected_button"]):
        if state == SystemState.MANUAL:
            state = SystemState.TWITCH
            twitch.connect()
        else:
            state = SystemState.MANUAL
            twitch.disconnect()
            visca.set_overlay_text("", line=0x1A)  # Zoomtext entfernen
            last_overlay_zoom = None
        # LED-Logik: bei dir war "rot an = verbunden" korrekt
        if twitch_is_connected(twitch):
            pins["connected_led_green"].value = False
            pins["connected_led_red"].value = True
        else:
            pins["connected_led_green"].value = True
            pins["connected_led_red"].value = False
        time.sleep(0.1)

    # ---------- Focus ----------
    if state != SystemState.OFF and (not pins["focus_button"].value and last_button["focus_button"]):
        visca.set_autofocus(not visca.autofocus)
        pins["autofocus_led_green"].value = visca.autofocus
        pins["autofocus_led_red"].value = not visca.autofocus
        time.sleep(0.1)

    # ---------- Freeze ----------
    if state != SystemState.OFF and (not pins["freeze_button"].value and last_button["freeze_button"]):
        visca.set_freeze(not visca.freeze)
        pins["freeze_led_green"].value = not visca.freeze
        pins["freeze_led_red"].value = visca.freeze
        time.sleep(0.1)

    # ---------- Brightness ----------
    if (now - last_brightness_time) > BRIGHTNESS_DEBOUNCE:
        pos = encoder.position
        if pos != brightness:
            brightness = max(0, min(20, pos))
            visca.set_brightness(brightness)
            last_brightness_time = now

    # ---------- Twitch lesen ----------
    if state == SystemState.TWITCH and twitch_is_connected(twitch):
        r = twitch.receive_zoom_command()
        if r:
            zoom_val, viewer = r
            zoom_override = zoom_val
            zoom_timeout = now + TWITCH_ZOOM_TIMEOUT
            last_viewer = viewer
            # Overlay: KAMERAKIND + Name
            visca.set_overlay_text("KAMERAKIND:", line=0x10)
            visca.set_overlay_text(str(viewer)[:10], line=0x11)

    # ---------- Override Timeout ----------
    if zoom_override is not None and now > zoom_timeout:
        zoom_override = None
        last_viewer = ""
        visca.set_overlay_text("", line=0x10)
        visca.set_overlay_text("", line=0x11)

    # ---------- Zoom berechnen & anwenden ----------
    zoom_now = zoom_override if zoom_override is not None else scale_adc_to_zoom(poti.value)
    if state != SystemState.OFF and zoom_now != last_zoom_sent:
        visca.set_zoom(zoom_now)
        last_zoom_sent = zoom_now

    # Twitch: Zoomzahl im Kamera-Overlay nur wenn verbunden
    if state == SystemState.TWITCH and twitch_is_connected(twitch):
        if zoom_now != last_overlay_zoom:
            visca.set_overlay_text(f"{zoom_now:2d}x", line=0x1A)  # oder visca.set_zoom_level(...)
            last_overlay_zoom = zoom_now

    # ---------- OLED ----------
    update_oled(zoom_now, visca.autofocus, visca.freeze, state == SystemState.TWITCH)

    # ---------- Buttons-State ----------
    for k in last_button:
        last_button[k] = pins[k].value

    time.sleep(0.02)
