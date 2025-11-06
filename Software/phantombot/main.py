# main.py — Hauptlogik: Hardware, Anzeige, HTTP-Server für PhantomBot-Zoom
import time
import json
import wifi
import socketpool
import digitalio
import gc

from config import (
    ZOOM_DEBOUNCE,
    BRIGHTNESS_DEBOUNCE,
    TWITCH_ZOOM_TIMEOUT,
    DISPLAY_WIDTH,
    DISPLAY_HEIGHT,
    TWITCH_CUSTOM_REWARD_ID,
)
from hardware_setup import setup_hardware
from visca_commands import ViscaCamera

# Secret für PhantomBot-Validierung
PHANTOM_SECRET = "ehajo"
HTTP_ENDPOINT = "/zoom"

class SystemState:
    OFF = 0
    MANUAL = 1

def scale_adc_to_zoom(adc_value):
    return 30 - int((adc_value / 65535) * 29)

# ---------- Setup ----------
pins, uart, i2c, oled, encoder, poti = setup_hardware()
visca = ViscaCamera(uart)

# Secrets (nur WiFi)
try:
    with open("secrets.json", "r") as f:
        secrets = json.load(f)
except Exception:
    secrets = {}

# WiFi verbinden
try:
    if not wifi.radio.connected:
        wifi.radio.connect(secrets["wifi"]["ssid"], secrets["wifi"]["password"])
        print("Verbunden mit WiFi. IP:", wifi.radio.ipv4_address)
except Exception as e:
    print("WiFi-Verbindung fehlgeschlagen:", e)

# HTTP-Server Setup
if wifi.radio.connected:
    pool = socketpool.SocketPool(wifi.radio)
    server = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
    server.setsockopt(pool.SOL_SOCKET, pool.SO_REUSEADDR, 1)
    server.bind(('', 80))
    server.listen(5)
    server.settimeout(0.02)
    print("HTTP-Server auf Port 80 gestartet.")
else:
    pool = None
    server = None
    print("Kein WiFi: HTTP-Server deaktiviert.")

# LEDs Grundzustand
pins["power_led_green"].value = True
pins["power_led_red"].value = False
pins["connected_led_green"].value = True
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

# Debouncing-Variablen
DEBOUNCE_TIME = 0.05  # 50 ms
button_debounce = {
    "power_button": {"last_time": 0, "stable_state": True},
    "focus_button": {"last_time": 0, "stable_state": True},
    "freeze_button": {"last_time": 0, "stable_state": True},
    "connected_button": {"last_time": 0, "stable_state": True}
}

last_zoom_sent = None
last_overlay_zoom = None
last_viewer = ""
zoom_override = None
zoom_timeout = 0
last_brightness_time = 0
last_oled_update = 0
OLED_UPDATE_INTERVAL = 0.1  # 100 ms

def handle_http_request(conn):
    try:
        request = conn.recv(1024).decode('utf-8')
        if not request:
            return False
        lines = request.split('\r\n')
        if len(lines) < 2:
            return False
        first_line = lines[0]
        parts = first_line.split(' ')
        if len(parts) < 2 or parts[0] != 'POST' or parts[1] != HTTP_ENDPOINT:
            conn.send(b'HTTP/1.1 404 Not Found\r\n\r\n')
            return True
        body_start = request.find('\r\n\r\n') + 4
        body = request[body_start:].strip()
        try:
            data = json.loads(body)
            if data.get('secret') != PHANTOM_SECRET:
                conn.send(b'HTTP/1.1 401 Unauthorized\r\n\r\n{"ok": false, "error": "Invalid secret"}')
                return True
            zoom_val = int(data.get('zoom', 0))
            viewer = str(data.get('viewer', 'unknown'))[:10]
            if 1 <= zoom_val <= 30:
                global zoom_override, zoom_timeout, last_viewer
                zoom_override = zoom_val
                zoom_timeout = time.monotonic() + TWITCH_ZOOM_TIMEOUT
                last_viewer = viewer
                visca.set_overlay_text("KAMERAKIND:", line=0x10)
                visca.set_overlay_text(viewer, line=0x11)
                print(f"PhantomBot: {viewer} -> Zoom {zoom_val}x")
                conn.send(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{"ok": true}')
            else:
                conn.send(b'HTTP/1.1 400 Bad Request\r\n\r\n{"ok": false, "error": "Invalid zoom"}')
        except json.JSONDecodeError:
            conn.send(b'HTTP/1.1 400 Bad Request\r\n\r\n{"ok": false, "error": "Invalid JSON"}')
        gc.collect()
        return True
    except Exception as e:
        print(f"HTTP-Fehler: {e}")
        try:
            conn.send(b'HTTP/1.1 500 Internal Server Error\r\n\r\n')
        except:
            pass
        return True

def update_oled(zoom, autofocus, freeze):
    oled.fill(0)
    oled.text("Live" if not freeze else "Freeze", 0, 0, 1)
    oled.text("AF" if autofocus else "MF", 0, DISPLAY_HEIGHT - 10, 1)
    oled.text(f"Bright: {brightness}", 50, DISPLAY_HEIGHT - 30, 1)
    oled.text(f"Zoom: {zoom}x", 50, DISPLAY_HEIGHT - 20, 1)
    oled.text("Manual", 50, DISPLAY_HEIGHT - 10, 1)
    oled.show()

while True:
    now = time.monotonic()

    # ---------- HTTP-Server (non-blocking) ----------
    if server:
        try:
            conn, addr = server.accept()
            if conn:
                handle_http_request(conn)
                conn.close()
        except OSError:
            pass

    # ---------- Power ----------
    current_power_state = pins["power_button"].value
    if current_power_state != button_debounce["power_button"]["stable_state"]:
        if (now - button_debounce["power_button"]["last_time"]) > DEBOUNCE_TIME:
            button_debounce["power_button"]["stable_state"] = current_power_state
            button_debounce["power_button"]["last_time"] = now
            if not current_power_state:  # Button gedrückt (active-low)
                print("Power button pressed")  # Debugging
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
                    zoom_override = None
                    last_viewer = ""
                    visca.set_overlay_text("", line=0x10)
                    visca.set_overlay_text("", line=0x11)
                    if server:
                        try:
                            server.close()
                        except:
                            pass
                    oled.fill(0)
                    oled.show()

    # ---------- Focus ----------
    current_focus_state = pins["focus_button"].value
    if current_focus_state != button_debounce["focus_button"]["stable_state"]:
        if (now - button_debounce["focus_button"]["last_time"]) > DEBOUNCE_TIME:
            button_debounce["focus_button"]["stable_state"] = current_focus_state
            button_debounce["focus_button"]["last_time"] = now
            if not current_focus_state and state != SystemState.OFF:
                print("Focus button pressed")  # Debugging
                visca.set_autofocus(not visca.autofocus)
                pins["autofocus_led_green"].value = visca.autofocus
                pins["autofocus_led_red"].value = not visca.autofocus

    # ---------- Freeze ----------
    current_freeze_state = pins["freeze_button"].value
    if current_freeze_state != button_debounce["freeze_button"]["stable_state"]:
        if (now - button_debounce["freeze_button"]["last_time"]) > DEBOUNCE_TIME:
            button_debounce["freeze_button"]["stable_state"] = current_freeze_state
            button_debounce["freeze_button"]["last_time"] = now
            if not current_freeze_state and state != SystemState.OFF:
                print("Freeze button pressed")  # Debugging
                visca.set_freeze(not visca.freeze)
                pins["freeze_led_green"].value = not visca.freeze
                pins["freeze_led_red"].value = visca.freeze

    # ---------- Brightness ----------
    if (now - last_brightness_time) > BRIGHTNESS_DEBOUNCE:
        pos = encoder.position
        if pos != brightness:
            brightness = max(0, min(20, pos))
            visca.set_brightness(brightness)
            last_brightness_time = now

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

    # ---------- Overlay Zoom ----------
    if zoom_now != last_overlay_zoom:
        visca.set_overlay_text(f"{zoom_now:2d}x", line=0x1A)
        last_overlay_zoom = zoom_now

    # ---------- OLED Update (weniger häufig) ----------
    if now - last_oled_update > OLED_UPDATE_INTERVAL:
        update_oled(zoom_now, visca.autofocus, visca.freeze)
        last_oled_update = now

    # ---------- Minimale Schleifenverzögerung ----------
    time.sleep(0.005)  # 5 ms für schnellere Reaktion