# ---------------------------
# Visca-basierte Controller Software
# für Optilia Mikroskope
# Basierend auf Raspberry Pi pico W 
# MAX3232 für UART
# mit bestem Dank an ChatGPT für die doch
# meist brauchbare Hilfe beim Coden!
# (C) eHaJo, 2024-2025
# ---------------------------

import time
import json
import board
import busio
import analogio
import digitalio
import rotaryio
from adafruit_ssd1306 import SSD1306_I2C
import wifi
import socketpool
import ssl
import adafruit_requests

# ---------------------------
# Globale Twitch-Variablen
# ---------------------------
TWITCH_USERNAME = ""          # wird über die Helix-API ermittelt
TWITCH_CHANNEL = "ehajo"       # ohne führendes "#"

# ---------------------------
# OLED-Display (I2C) einrichten
# ---------------------------
i2c = busio.I2C(scl=board.GP1, sda=board.GP0)
WIDTH = 128
HEIGHT = 64
oled = SSD1306_I2C(WIDTH, HEIGHT, i2c)

# ---------------------------
# UART für Kamera (VISCA) einrichten
# ---------------------------
uart = busio.UART(tx=board.GP4, rx=board.GP5, baudrate=9600, timeout=1)

# ---------------------------
# Potentiometer (manuelle Zoomsteuerung)
# ---------------------------
poti = analogio.AnalogIn(board.A0)

# ---------------------------
# Inkrementalgeber (Encoder) für Helligkeit an GP7 (A) und GP8 (B)
# ---------------------------
encoder = rotaryio.IncrementalEncoder(board.GP7, board.GP8)
prev_position = encoder.position
brightness_value = 4   # Standardhelligkeit (0x04)

# ---------------------------
# Tasten für Kamera-Steuerung
# ---------------------------
power_button = digitalio.DigitalInOut(board.GP15)   # System EIN/AUS
power_button.direction = digitalio.Direction.INPUT
power_button.pull = digitalio.Pull.UP

focus_button = digitalio.DigitalInOut(board.GP16)
focus_button.direction = digitalio.Direction.INPUT
focus_button.pull = digitalio.Pull.UP

freeze_button = digitalio.DigitalInOut(board.GP19)
freeze_button.direction = digitalio.Direction.INPUT
freeze_button.pull = digitalio.Pull.UP

# ---------------------------
# Taster für Connected-Modus (Twitch EIN/AUS) an GP11
# ---------------------------
connected_button = digitalio.DigitalInOut(board.GP11)
connected_button.direction = digitalio.Direction.INPUT
connected_button.pull = digitalio.Pull.UP

# ---------------------------
# LEDs für Kamera-Steuerung
# ---------------------------
autofocus_led_green = digitalio.DigitalInOut(board.GP17)
autofocus_led_green.direction = digitalio.Direction.OUTPUT

autofocus_led_red = digitalio.DigitalInOut(board.GP18)
autofocus_led_red.direction = digitalio.Direction.OUTPUT

freeze_led_green = digitalio.DigitalInOut(board.GP20)
freeze_led_green.direction = digitalio.Direction.OUTPUT

freeze_led_red = digitalio.DigitalInOut(board.GP21)
freeze_led_red.direction = digitalio.Direction.OUTPUT

power_led_green = digitalio.DigitalInOut(board.GP14)
power_led_green.direction = digitalio.Direction.OUTPUT

power_led_red = digitalio.DigitalInOut(board.GP13)
power_led_red.direction = digitalio.Direction.OUTPUT
power_led_red.value = True

# ---------------------------
# LEDs für Connected-Modus (Twitch Status)
# ---------------------------
connected_led_green = digitalio.DigitalInOut(board.GP10)  # grün: Twitch connected
connected_led_green.direction = digitalio.Direction.OUTPUT

connected_led_red = digitalio.DigitalInOut(board.GP9)      # rot: Twitch off
connected_led_red.direction = digitalio.Direction.OUTPUT

# ---------------------------
# Zoomstufen-Tabelle (VISCA)
# ---------------------------
ZOOM_LEVELS = {
    1: 0x0000, 2: 0x16A1, 3: 0x2063, 4: 0x2628, 5: 0x2A1D,
    6: 0x2D13, 7: 0x2F6D, 8: 0x3161, 9: 0x330D, 10: 0x3486,
    11: 0x35D7, 12: 0x3709, 13: 0x3820, 14: 0x3920, 15: 0x3A0A,
    16: 0x3ADD, 17: 0x3B9C, 18: 0x3C46, 19: 0x3CDC, 20: 0x3D60,
    21: 0x3D9C, 22: 0x3DD8, 23: 0x3E14, 24: 0x3E50, 25: 0x3E8C,
    26: 0x3EC8, 27: 0x3F04, 28: 0x3F40, 29: 0x3F7C, 30: 0x3FFF,
}

# ---------------------------
# VISCA-Befehl senden
# ---------------------------
def send_command(command_bytes):
    command = [0x81, 0x01, 0x04] + command_bytes + [0xFF]
    uart.write(bytearray(command))

# ---------------------------
# Freeze-Funktion (Overlay setzen/entfernen)
# ---------------------------
def set_freeze_overlay(is_freeze):
    send_command([0x74, 0x2F])
    if is_freeze:
        freeze_led_green.value = False
        freeze_led_red.value = True
        send_command([0x73, 0x10, 0x00, 0x0A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        send_command([0x73, 0x20, 0x42, 0x42, 0x42, 0x42, 0x05, 0x11, 0x04, 0x04, 0x19, 0x04])
        send_command([0x62, 0x02])
    else:
        freeze_led_green.value = True
        freeze_led_red.value = False
        send_command([0x73, 0x20, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42, 0x42])
        send_command([0x62, 0x03])

# ---------------------------
# Helligkeitsbefehl senden (Brightness)
# ---------------------------
def send_brightness_command(brightness):
    # brightness ist ein Integer von 0 bis 255
    high = (brightness >> 4) & 0x0F
    low = brightness & 0x0F
    send_command([0x4E, 0x00, 0x00, high, low])

def scale_adc_to_zoom(adc_value):
    return 30 - int((adc_value / 65535) * 29)

# ---------------------------
# Display-Bereiche aktualisieren
# ---------------------------
def update_connection_status(wifi_status, twitch_status):
    oled.fill_rect(50, 0, WIDTH-50, 20, 0)
    oled.text("WiFi:", 70, 0, 1)
    oled.text("Twitch:", 70, 10, 1)
    # Zeige Smiley für WiFi
    if wifi_status == 1:
        draw_bitmap(laughing_smiley, 120, 0)
    else:
        draw_bitmap(sad_smiley, 120, 0)
    # Zeige Smiley für Twitch
    if twitch_status == 1:
        draw_bitmap(laughing_smiley, 120, 10)
    else:
        draw_bitmap(sad_smiley, 120, 10)
    oled.show()

# ---------------------------
# Display-Status für Kamera-Steuerung (unterer Bereich)
# Hier wird nun zusätzlich der Helligkeitswert angezeigt.
# ---------------------------
def display_status(zoom_level, is_autofocus, is_freeze, override):
    # Wir löschen den Bereich von y=25 bis zum unteren Rand
    oled.fill_rect(0, 25, WIDTH, HEIGHT-25, 0)
    # Obere Statuszeile: links "Freeze", rechts "Bright: X"
    oled.text("Freeze", 0, 0, 1)
    # Links unten: AF/MF-Status
    af_status = "AF" if is_autofocus else "MF"
    oled.text(af_status, 0, HEIGHT-10, 1)
    # Rechts unten: Zoom und Mode
    oled.text("Bright: {}".format(brightness_value), 50, HEIGHT-30, 1)
    oled.text("Zoom: {}x".format(zoom_level), 50, HEIGHT-20, 1)
    mode = "Twitch" if override else "Manual"
    oled.text("Mode: {}".format(mode), 50, HEIGHT-10, 1)
    oled.show()

# ---------------------------
# Neue Funktion: Bitmap zeichnen (für Smiley)
# ---------------------------
def draw_bitmap(bitmap, x, y, width=8, height=8):
    for j in range(height):
        row = bitmap[j]
        for i in range(width):
            if row & (1 << (7 - i)):
                oled.pixel(x + i, y + j, 1)
            else:
                oled.pixel(x + i, y + j, 0)

# Zwei 8x8 Bitmaps für den Twitch-Status (Smiley)
# Lachender Smiley (verbunden)
laughing_smiley = [
    0x3C,
    0x42,
    0xA5,
    0x81,
    0xA5,
    0x99,
    0x42,
    0x3C
]
# Trauriger Smiley (nicht verbunden)
sad_smiley = [
    0x3C,
    0x42,
    0xA5,
    0x81,
    0x99,
    0xA5,
    0x42,
    0x3C
]

# ---------------------------
# Overlay-Text anzeigen (KAMERAKIND: [Zuschauername])
# ---------------------------
def overlay_text(viewer_name):
    # Gesamter Text in Großbuchstaben
    full_text = viewer_name.upper()
    
    def convert_char(ch):
        if 'A' <= ch <= 'Z':
            return ord(ch) - ord('A')  # A -> 0x00 ... Z -> 0x19
        elif '1' <= ch <= '9':
            return (ord(ch) - ord('1')) + 0x1e
        elif ch == '0':
            return 0x27
        else:
            return 0x42

    converted = [convert_char(ch) for ch in full_text]
    
    if len(converted) < 20:
        converted.extend([0x42] * (20 - len(converted)))
    else:
        converted = converted[:20]
    
    first_half = converted[:10]
    second_half = converted[10:]
    
    send_command([0x74, 0x2F])
    send_command([0x73, 0x10] + first_half)
    send_command([0x73, 0x30] + second_half)

# ---------------------------
# Globale Variablen für Verbindung und Optimierung
# ---------------------------
zoom_cooldown = 0       # 10s Cooldown für !zoom
zoom_override = None
twitch_enabled = False   # Twitch (Connected-Modus) initial aus
twitch_sock = None       # Twitch-IRC-Socket
system_on = False        # Gesamtsystem (Kamera-Steuerung) initial aus
wifi_connected = True    # WiFi wird beim Start automatisch verbunden
autofocus_state = True   # Standard: AF aktiv
freeze_state = False     # Standard: Freeze aus

# ---------------------------
# Secrets laden
# ---------------------------
with open("secrets.json", "r") as f:
    secrets = json.load(f)
WIFI_SSID = secrets["wifi"]["ssid"]
WIFI_PASSWORD = secrets["wifi"]["password"]
TWITCH_CLIENT_ID = secrets["twitch"]["client_id"]
TWITCH_ACCESS_TOKEN = secrets["twitch"]["access_token"]

# ---------------------------
# WiFi verbinden (immer aktiv)
# ---------------------------
oled.fill(0)
oled.text("Starting...", 0, 0, 1)
oled.show()
print("WiFi verbinden...")
oled.text("WiFi verbinden...", 0, 10, 1)
oled.show()
try:
    wifi.radio.connect(WIFI_SSID, WIFI_PASSWORD)
    wifi_connected = True
    oled.text("WiFi verbunden...", 0, 20, 1)
except Exception as e:
    wifi_connected = False
    oled.text("Kein WiFi!", 0, 20, 1)
oled.show()
time.sleep(0.5)

# ---------------------------
# Globalen SocketPool erstellen
# ---------------------------
pool = socketpool.SocketPool(wifi.radio)

# ---------------------------
# Kamera Startzustand
# ---------------------------
send_command([0x74, 0x1F])  # Textpuffer löschen
send_command([0x59, 0x03])  # Spot AE off
send_command([0x39, 0x00])  # Brightness Auto
send_command([0x3E, 0x02])  # Exposure Comp On
send_command([0x4E, 0x00, 0x00, 0x00, 0x04])  # exp fix for perfect lightning
send_command([0x35, 0x03])  # Weißabgleich OnePush
send_command([0x62, 0x03])  # Freeze off
send_command([0x00, 0x03])  # Kamera ausschalten
power_led_red.value = True
power_led_green.value = False
connected_led_green.value = False
connected_led_red.value = False

def display_zoom_timer(zoom_timeout, total=20):
    # Zoom-Timer nur anzeigen, solange noch Zeit übrig ist
    remaining = zoom_timeout - time.monotonic()
    if remaining <= 1:
        oled.fill_rect(5, 23, WIDTH-10, 4, 0)
        oled.show()
        print("reset")
        return
    fraction = remaining / total
    bar_width = WIDTH - 10
    bar_height = 4
    x = 5
    y = 23
    oled.fill_rect(x, y, bar_width, bar_height, 0)
    oled.rect(x, y, bar_width, bar_height, 1)
    fill_width = int(fraction * (bar_width - 2))
    oled.fill_rect(x+1, y+1, fill_width, bar_height-2, 1)
    oled.show()

# ---------------------------
# Funktion: Twitch-IRC-Verbindung aufbauen (wird erst im Connected-Modus gestartet)
# ---------------------------
def connect_twitch():
    global twitch_sock
    # Nur versuchen, wenn WiFi verfügbar ist:
    if not wifi_connected:
        print("Kein WiFi – Twitch wird nicht gestartet.")
        return
    irc_server = "irc.chat.twitch.tv"
    irc_port = 6667
    twitch_sock = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
    twitch_sock.settimeout(0.5)
    print("Verbinde mit Twitch IRC...")
    twitch_sock.connect((irc_server, irc_port))
    twitch_sock.send(bytes("PASS " + TWITCH_ACCESS_TOKEN + "\r\n", "utf-8"))
    twitch_sock.send(bytes("NICK " + TWITCH_USERNAME + "\r\n", "utf-8"))
    # Hier die Capabilities anfordern:
    twitch_sock.send(bytes("CAP REQ :twitch.tv/tags\r\n", "utf-8"))
    twitch_sock.send(bytes("CAP REQ :twitch.tv/commands\r\n", "utf-8"))
    twitch_sock.send(bytes("JOIN #" + TWITCH_CHANNEL + "\r\n", "utf-8"))
    print("Mit Twitch IRC verbunden. Gejoint: #" + TWITCH_CHANNEL)
    send_chat_message("ehajoOptilia Kamera Online!!")
    update_connection_status(1, 1)

# ---------------------------
# Funktion: Twitch-IRC-Verbindung trennen
# ---------------------------
def disconnect_twitch():
    global twitch_sock
    if twitch_sock:
        try:
            send_chat_message("ehajoOptilia Kamera Offline!")
            twitch_sock.close()
        except Exception:
            pass
        twitch_sock = None
    update_connection_status(1, 0)
    print("Twitch IRC getrennt.")

# ---------------------------
# Funktion: Twitch-Chat auswerten (Custom Reward)
# ---------------------------
def check_twitch_messages(sock):
    global zoom_cooldown
    buf = bytearray(1024)
    try:
        n = sock.recv_into(buf)
    except Exception:
        return None
    if not n:
        return None
    try:
        data = buf[:n].decode("utf-8")
    except Exception:
        data = ""
    lines = data.split("\r\n")
    for line in lines:
        if not line:
            continue
        # Parse IRC-Tags, falls vorhanden:
        tags = {}
        message_body = line
        if line.startswith("@"):
            parts = line.split(" ", 1)
            tag_str = parts[0][1:]
            message_body = parts[1] if len(parts) > 1 else ""
            for token in tag_str.split(";"):
                if "=" in token:
                    key, value = token.split("=", 1)
                    tags[key] = value
                else:
                    tags[token] = ""
        print("IRC:", line)
        if line.startswith("PING"):
            sock.send(bytes("PONG :tmi.twitch.tv\r\n", "utf-8"))
        elif "PRIVMSG" in message_body:
            if not ("custom-reward-id" in tags and tags["custom-reward-id"] == "66cbd19b-5a24-49cf-affd-412fc5b2b31d"):
                print("Nachricht ohne Custom Reward, ignoriere!")
                continue
            text = message_body.split(" :", 1)[1].strip() if " :" in message_body else message_body.strip()
            if text.endswith("x") or text.endswith("X"):
                text = text[:-1]
            try:
                zoom_val = int(text)
                if 1 <= zoom_val <= 30:
                    current_time = time.monotonic()
                    if current_time < zoom_cooldown:
                        send_chat_message("ehajoOptilia Bitte warte 10 Sekunden, bevor du einen neuen Befehl sendest.")
                        return None
                    send_chat_message("ehajoOptilia Zoom auf {}x gestellt!".format(zoom_val))
                    zoom_cooldown = current_time + 10
                    if "display-name" in tags and tags["display-name"]:
                        viewer_name = tags["display-name"]
                    else:
                        if message_body.startswith(":"):
                            viewer_name = message_body[1:].split("!")[0]
                        else:
                            viewer_name = "UNKNOWN"
                    overlay_text(viewer_name)
                    return zoom_val
                else:
                    send_chat_message("ehajoOptilia Bitte einen Wert zwischen 1 und 30 eingeben.")
                    return None
            except ValueError:
                send_chat_message("ehajoOptilia Ungültiger Zoomwert.")
                return None
    return None

# ---------------------------
# Funktion: Twitch-Chat-Nachricht senden
# ---------------------------
def send_chat_message(msg):
    global twitch_sock
    if twitch_sock is None:
        return
    s = "PRIVMSG #{} :{}\r\n".format("ehajo", msg)
    twitch_sock.send(bytes(s, "utf-8"))

# ---------------------------
# Ermittele Twitch-Benutzernamen über Helix-API (nur wenn WiFi verfügbar)
# ---------------------------
if wifi_connected:
    oled.text("Twitch verbinden...", 0, 30, 1)
    oled.show()
    pool = socketpool.SocketPool(wifi.radio)
    session = adafruit_requests.Session(pool, ssl.create_default_context())
    token_no_prefix = TWITCH_ACCESS_TOKEN.replace("oauth:", "")
    helix_url = "https://api.twitch.tv/helix/users"
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": "Bearer " + token_no_prefix
    }
    response = session.get(helix_url, headers=headers)
    data = response.json()
    if "data" in data and len(data["data"]) > 0:
        TWITCH_USERNAME = data["data"][0]["login"]
    else:
        raise RuntimeError("Konnte den Twitch-Benutzernamen nicht ermitteln")
    print("Ermittelter Twitch-Username:", TWITCH_USERNAME)
    oled.text("Twitch verbunden!  ", 0, 40, 1)
    oled.show()
    time.sleep(0.5)
    oled.fill(0)
    oled.show()

# ---------------------------
# Hauptschleife
# ---------------------------
last_zoom_value = None
last_override = None

while True:
    if not power_button.value:
        system_on = not system_on
        if system_on:
            send_command([0x00, 0x02])  # Kamera EIN
            send_command([0x74, 0x1F])  # Textpuffer löschen
            send_command([0x59, 0x03])  # Spot AE off
            send_command([0x39, 0x00])  # Brightness Auto
            send_command([0x3E, 0x02])  # Exposure Comp On
            send_command([0x4E, 0x00, 0x00, 0x00, 0x04])  # exp fix for perfect lightning
            send_command([0x35, 0x03])  # Weißabgleich OnePush
            send_command([0x62, 0x03])  # Freeze off
            send_command([0x38, 0x02])  # Autofokus ein
            power_led_red.value = False
            power_led_green.value = True
            autofocus_state = True
            freeze_state = False
            autofocus_led_green.value = True
            autofocus_led_red.value = False
            freeze_led_green.value = True
            freeze_led_red.value = False
            update_connection_status(1, 0)
        else:
            send_command([0x00, 0x03])  # Kamera AUS
            power_led_red.value = True
            power_led_green.value = False
            if twitch_enabled:
                disconnect_twitch()
                twitch_enabled = False
            update_connection_status(1, 0)
            oled.fill(0)
            oled.show()
            autofocus_led_green.value = False
            autofocus_led_red.value = False
            freeze_led_green.value = False
            freeze_led_red.value = False
            connected_led_green.value = False
            connected_led_red.value = False
            last_zoom_value = None
            last_override = None
        time.sleep(0.1)
    
    if system_on and not twitch_enabled:
        connected_led_green.value = False
        connected_led_red.value = True
    
    if system_on:
        if not connected_button.value:
            time.sleep(0.1)
            # Wenn kein WiFi vorhanden ist, wird der Connected-Modus ignoriert
            if wifi_connected:
                twitch_enabled = not twitch_enabled
                if twitch_enabled:
                    connected_led_green.value = True
                    connect_twitch()
                    connected_led_red.value = False
                else:
                    disconnect_twitch()
                    connected_led_green.value = False
                    connected_led_red.value = True
            time.sleep(0.1)
    
    if system_on and twitch_enabled and wifi_connected and (twitch_sock is not None):
        zoom_command = check_twitch_messages(twitch_sock)
    else:
        zoom_command = None
    
    if zoom_command is not None:
        if zoom_command == "auto":
            zoom_override = None
            print("Zoom-Override aufgehoben. Steuerung erfolgt wieder über Potentiometer.")
        else:
            zoom_override = zoom_command
            zoom_timeout = time.monotonic() + 20 # 20s lang die vom User eingestellte Zoomstufe behalten
            print("Zoom-Override: Setze Zoom auf {}x".format(zoom_override))
    
    if system_on:
        # Zuerst: Helligkeitsanpassung per Inkrementalgeber abfragen
        new_position = encoder.position
        if new_position != prev_position:
            delta = new_position - prev_position
            prev_position = new_position
            brightness_value += delta
            if brightness_value < 0:
                brightness_value = 0
            if brightness_value > 255:
                brightness_value = 255
            # Sende neuen Helligkeitsbefehl:
            send_brightness_command(brightness_value)
            display_status(current_zoom_level, autofocus_state, freeze_state, override=is_override)

        if zoom_override is not None:
            display_zoom_timer(zoom_timeout, total=20)
            
        if zoom_override is not None:
            current_zoom_level = zoom_override
            is_override = True
        else:
            current_zoom_level = scale_adc_to_zoom(poti.value)
            is_override = False
        
        if (current_zoom_level != last_zoom_value) or (is_override != last_override):
            display_status(current_zoom_level, autofocus_state, freeze_state, override=is_override)
            visca_val = ZOOM_LEVELS[current_zoom_level]
            send_command([0x47,
                          (visca_val >> 12) & 0x0F,
                          (visca_val >> 8) & 0x0F,
                          (visca_val >> 4) & 0x0F,
                          visca_val & 0x0F])
            last_zoom_value = current_zoom_level
            last_override = is_override
        
        if not freeze_button.value:
            freeze_state = not freeze_state
            set_freeze_overlay(freeze_state)
            time.sleep(0.1)
        
        if not focus_button.value:
            autofocus_state = not autofocus_state
            send_command([0x38, 0x02] if autofocus_state else [0x38, 0x03])
            autofocus_led_green.value = autofocus_state
            autofocus_led_red.value = not autofocus_state
            display_status(current_zoom_level, autofocus_state, freeze_state, override=is_override)
            time.sleep(0.1)
    

    if zoom_override is not None and time.monotonic() > zoom_timeout:
        zoom_override = None
        print("Zoom-Override abgelaufen, wechsle zurück auf manuelle Steuerung.")
        send_command([0x74, 0x2F])
        send_command([0x73, 0x20] + [0x42]*10)
        send_command([0x73, 0x21] + [0x42]*10)
        send_command([0x73, 0x31] + [0x42]*10)
    
    time.sleep(0.01)
