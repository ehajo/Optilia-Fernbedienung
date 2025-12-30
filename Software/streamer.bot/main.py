# main.py — Optilia VISCA Controller (YouTube/Streamer.bot via UDP)
# + Zoom-Overlay Anzeige per Tastendruck umschaltbar (standard: EIN)
#   -> nutzt connected_button (GP11) als Toggle-Taste

import time
import json
import wifi
import socketpool
import digitalio  # wichtig
import gc

from config import (
    BRIGHTNESS_DEBOUNCE,
    ZOOM_OVERRIDE_TIMEOUT,
    DISPLAY_HEIGHT,
    UDP_PORT,
)
from hardware_setup import setup_hardware
from visca_commands import ViscaCamera


class SystemState:
    OFF = 0
    MANUAL = 1


def scale_adc_to_zoom(adc_value):
    # Invertiert: oben am Poti = 1x, unten = 30x
    return 30 - int((adc_value / 65535) * 29)


def clamp_zoom(z):
    try:
        z = int(z)
    except Exception:
        return None
    if z < 1:
        z = 1
    if z > 30:
        z = 30
    return z


def safe_decode(raw: bytes) -> str:
    """
    CircuitPython-freundliches Decoding:
    - bevorzugt UTF-8 (ohne errors keyword)
    - fallback: ASCII-like mit Ersetzung nicht-druckbarer Bytes durch Leerzeichen
    """
    try:
        return raw.decode("utf-8")
    except Exception:
        out = []
        for b in raw:
            if 32 <= b <= 126:
                out.append(chr(b))
            else:
                out.append(" ")
        return "".join(out)


def parse_udp_message(msg: str):
    """
    Unterstützte Formate (case-insensitive):
      - "ZOOM 12 Hannes"
      - "!zoom 12 Hannes"
      - "ZOOM:12:Hannes"
      - "ZOOM=12;Hannes"
      - "ZOOM 12" (Viewer optional)
      - "ZOOMOFF" / "ZOOM OFF" / "!zoomoff" => Override sofort aus

    Rückgabe: (zoom:int|None, viewer:str, force_off:bool)
    """
    if not msg:
        return None, "", False

    s = msg.strip()
    if not s:
        return None, "", False

    low = s.lower().strip()

    # Override sofort aus
    if low in ("zoomoff", "!zoomoff", "zoom off", "!zoom off", "zoom:off", "zoom=off"):
        return None, "", True

    # vereinheitlichen: trenner -> spaces
    s_norm = s.replace(";", " ").replace("=", " ").replace(":", " ")
    parts = [p for p in s_norm.split() if p]
    if not parts:
        return None, "", False

    p0 = parts[0].lower()

    if p0 in ("zoom", "!zoom"):
        if len(parts) >= 2 and parts[1].lower() == "off":
            return None, "", True

        if len(parts) >= 2:
            zoom = clamp_zoom(parts[1])
            viewer = parts[2] if len(parts) >= 3 else ""
            return zoom, viewer[:10], False

        return None, "", False

    # Fallback: "zoom12" / "!zoom12"
    if low.startswith("zoom") or low.startswith("!zoom"):
        digits = ""
        for ch in s:
            if ch.isdigit():
                digits += ch
            elif digits:
                break
        if digits:
            return clamp_zoom(digits), "", False

    return None, "", False


def update_oled(oled, zoom, autofocus, freeze, brightness, viewer, override_active, zoom_overlay_enabled):
    oled.fill(0)
    oled.text("Live" if not freeze else "Freeze", 0, 0, 1)
    oled.text("AF" if autofocus else "MF", 0, DISPLAY_HEIGHT - 10, 1)

    oled.text(f"Bright:{brightness:2d}", 50, DISPLAY_HEIGHT - 30, 1)
    oled.text(f"Zoom:  {zoom:2d}x",     50, DISPLAY_HEIGHT - 20, 1)

    # Statuszeile: zeigt zusätzlich, ob Zoom-Overlay an/aus ist
    if override_active:
        v = viewer if viewer else "YT"
        tail = "OVR"
        oled.text(f"!zoom: {v} {tail}", 50, DISPLAY_HEIGHT - 10, 1)
    else:
        tail = "ON" if zoom_overlay_enabled else "OFF"
        oled.text(f"Overlay:{tail}", 50, DISPLAY_HEIGHT - 10, 1)

    oled.show()


# =========================
# Setup
# =========================
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
        ssid = secrets["wifi"]["ssid"]
        pw = secrets["wifi"]["password"]
        print(f"Verbinde mit WLAN: {ssid}")
        wifi.radio.connect(ssid, pw)
        print("WiFi verbunden. IP:", wifi.radio.ipv4_address)
except Exception as e:
    print("WiFi-Verbindung fehlgeschlagen:", e)

# UDP-Server Setup (non-blocking)
udp = None
udp_buf = None
if wifi.radio.connected:
    pool = socketpool.SocketPool(wifi.radio)
    udp = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)
    udp.bind(("", UDP_PORT))
    udp.settimeout(0)  # non-blocking
    udp_buf = bytearray(256)
    print(f"UDP-Server bereit auf Port {UDP_PORT}")
else:
    print("Kein WiFi: UDP-Server deaktiviert.")

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
print("On-State Standardwerte an Kamera schicken...")
visca.set_power(True)
visca.set_freeze(False)
visca.set_autofocus(True)

brightness = 4
encoder.position = brightness
visca.set_brightness(brightness)

state = SystemState.MANUAL

# Debounce
DEBOUNCE_TIME = 0.05  # 50 ms
button_debounce = {
    "power_button": {"last_time": 0, "stable_state": True},
    "focus_button": {"last_time": 0, "stable_state": True},
    "freeze_button": {"last_time": 0, "stable_state": True},
    "connected_button": {"last_time": 0, "stable_state": True},  # Toggle Zoom-Overlay
}

last_zoom_sent = None
last_overlay_zoom = None

zoom_override = None
zoom_timeout = 0.0
last_viewer = ""

last_brightness_time = 0.0
last_oled_update = 0.0
OLED_UPDATE_INTERVAL = 0.1  # 100 ms

UDP_MAX_PACKETS_PER_LOOP = 12

# Debug Heartbeat
last_udp_heartbeat = time.monotonic()
UDP_HEARTBEAT_SEC = 10.0

# =========================
# Zoom-Overlay Toggle (NEU)
# =========================
zoom_overlay_enabled = True  # Standard: EIN (wie jetzt)


while True:
    now = time.monotonic()

    # =========================
    # UDP Empfang + Debug
    # =========================
    if udp and udp_buf:
        packets_processed = 0

        while packets_processed < UDP_MAX_PACKETS_PER_LOOP:
            try:
                nbytes, addr = udp.recvfrom_into(udp_buf)  # CircuitPython!
                if not nbytes or nbytes <= 0:
                    break

                raw = bytes(udp_buf[:nbytes])
                decoded = safe_decode(raw)
                decoded_stripped = decoded.strip()

                print("UDP RX:", addr, "len=", nbytes)
                print("UDP RAW:", raw)
                print("UDP TXT:", repr(decoded_stripped))

                # Debug Tokens
                norm = decoded_stripped.replace(";", " ").replace("=", " ").replace(":", " ")
                parts_dbg = [p for p in norm.split() if p]
                print("UDP TOK:", parts_dbg)

                zoom_val, viewer, force_off = parse_udp_message(decoded_stripped)

                if force_off:
                    zoom_override = None
                    zoom_timeout = 0.0
                    last_viewer = ""
                    visca.set_overlay_text("", line=0x10)
                    visca.set_overlay_text("", line=0x11)
                    print("UDP PARSE: OVERRIDE OFF")

                elif zoom_val is not None:
                    zoom_override = zoom_val
                    zoom_timeout = now + ZOOM_OVERRIDE_TIMEOUT
                    last_viewer = viewer

                    visca.set_overlay_text("ZOOM BY:", line=0x10)
                    visca.set_overlay_text(viewer if viewer else "YT", line=0x11)

                    print(f"UDP PARSE: ZOOM={zoom_val} VIEWER='{last_viewer}' TIMEOUT={ZOOM_OVERRIDE_TIMEOUT}s")

                else:
                    print("UDP PARSE: (ignored)")

                packets_processed += 1

            except OSError:
                break
            except Exception as e:
                print("UDP-Fehler:", e)
                break

        if packets_processed:
            gc.collect()
            last_udp_heartbeat = now

    if (now - last_udp_heartbeat) > UDP_HEARTBEAT_SEC:
        if udp:
            print(f"[UDP] waiting... (port {UDP_PORT})")
        last_udp_heartbeat = now

    # =========================
    # Power
    # =========================
    current_power_state = pins["power_button"].value
    if current_power_state != button_debounce["power_button"]["stable_state"]:
        if (now - button_debounce["power_button"]["last_time"]) > DEBOUNCE_TIME:
            button_debounce["power_button"]["stable_state"] = current_power_state
            button_debounce["power_button"]["last_time"] = now
            if not current_power_state:  # active-low
                if state == SystemState.OFF:
                    state = SystemState.MANUAL
                    pins["power_led_green"].value = True
                    pins["power_led_red"].value = False
                    visca.set_power(True)
                    print("POWER: ON")
                else:
                    state = SystemState.OFF
                    pins["power_led_green"].value = False
                    pins["power_led_red"].value = True
                    visca.set_power(False)
                    print("POWER: OFF")

                    zoom_override = None
                    zoom_timeout = 0.0
                    last_viewer = ""
                    visca.set_overlay_text("", line=0x10)
                    visca.set_overlay_text("", line=0x11)

                    # Zoom-Overlay line ebenfalls leeren
                    visca.set_overlay_text("", line=0x1A)
                    last_overlay_zoom = None

                    oled.fill(0)
                    oled.show()

    # =========================
    # Focus
    # =========================
    current_focus_state = pins["focus_button"].value
    if current_focus_state != button_debounce["focus_button"]["stable_state"]:
        if (now - button_debounce["focus_button"]["last_time"]) > DEBOUNCE_TIME:
            button_debounce["focus_button"]["stable_state"] = current_focus_state
            button_debounce["focus_button"]["last_time"] = now
            if not current_focus_state and state != SystemState.OFF:
                visca.set_autofocus(not visca.autofocus)
                pins["autofocus_led_green"].value = visca.autofocus
                pins["autofocus_led_red"].value = not visca.autofocus
                print("FOCUS:", "AF" if visca.autofocus else "MF")

    # =========================
    # Freeze
    # =========================
    current_freeze_state = pins["freeze_button"].value
    if current_freeze_state != button_debounce["freeze_button"]["stable_state"]:
        if (now - button_debounce["freeze_button"]["last_time"]) > DEBOUNCE_TIME:
            button_debounce["freeze_button"]["stable_state"] = current_freeze_state
            button_debounce["freeze_button"]["last_time"] = now
            if not current_freeze_state and state != SystemState.OFF:
                visca.set_freeze(not visca.freeze)
                pins["freeze_led_green"].value = not visca.freeze
                pins["freeze_led_red"].value = visca.freeze
                print("FREEZE:", "ON" if visca.freeze else "OFF")

    # =========================
    # Toggle Zoom-Overlay per connected_button (NEU)
    # =========================
    current_conn_state = pins["connected_button"].value
    if current_conn_state != button_debounce["connected_button"]["stable_state"]:
        if (now - button_debounce["connected_button"]["last_time"]) > DEBOUNCE_TIME:
            button_debounce["connected_button"]["stable_state"] = current_conn_state
            button_debounce["connected_button"]["last_time"] = now
            if not current_conn_state and state != SystemState.OFF:
                zoom_overlay_enabled = not zoom_overlay_enabled
                print("ZOOM OVERLAY:", "ON" if zoom_overlay_enabled else "OFF")

                if not zoom_overlay_enabled:
                    # sofort ausblenden
                    visca.set_overlay_text("", line=0x1A)
                    last_overlay_zoom = None
                else:
                    # sofort aktuellen Zoom einblenden (wird weiter unten berechnet)
                    last_overlay_zoom = None  # erzwingt Update

    # =========================
    # Brightness
    # =========================
    if (now - last_brightness_time) > BRIGHTNESS_DEBOUNCE:
        pos = encoder.position
        if pos != brightness:
            brightness = max(0, min(20, pos))
            visca.set_brightness(brightness)
            last_brightness_time = now
            print("BRIGHT:", brightness)

    # =========================
    # Override Timeout
    # =========================
    if zoom_override is not None and now > zoom_timeout:
        print("ZOOM OVERRIDE: timeout -> back to manual")
        zoom_override = None
        zoom_timeout = 0.0
        last_viewer = ""
        visca.set_overlay_text("", line=0x10)
        visca.set_overlay_text("", line=0x11)

    # =========================
    # Zoom anwenden
    # =========================
    zoom_now = zoom_override if zoom_override is not None else scale_adc_to_zoom(poti.value)

    if state != SystemState.OFF and zoom_now != last_zoom_sent:
        visca.set_zoom(zoom_now)
        last_zoom_sent = zoom_now

    # =========================
    # Overlay Zoom (Line 0x1A) nur wenn enabled
    # =========================
    if zoom_overlay_enabled:
        if zoom_now != last_overlay_zoom:
            visca.set_overlay_text(f"{zoom_now:2d}x", line=0x1A)
            last_overlay_zoom = zoom_now
    else:
        # wenn disabled: nichts aktualisieren
        pass

    # =========================
    # OLED Update
    # =========================
    if now - last_oled_update > OLED_UPDATE_INTERVAL:
        update_oled(
            oled=oled,
            zoom=zoom_now,
            autofocus=visca.autofocus,
            freeze=visca.freeze,
            brightness=brightness,
            viewer=last_viewer,
            override_active=(zoom_override is not None),
            zoom_overlay_enabled=zoom_overlay_enabled,
        )
        last_oled_update = now

    time.sleep(0.005)
