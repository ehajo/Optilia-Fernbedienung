# twitch_integration.py - Twitch-IRC und API-Logik

import wifi
import socketpool
import ssl
import adafruit_requests
import time
import re
from config import TWITCH_CHANNEL, TWITCH_CUSTOM_REWARD_ID

class TwitchController:
    def __init__(self, oled, secrets):
        self.oled = oled
        self.pool = socketpool.SocketPool(wifi.radio)
        self.sock = None
        self.secrets = secrets
        self.username = self._get_twitch_username()
        self.zoom_cooldown = 0
        self.buffer = bytearray(1024)
        self.connected = False
        self.commands_sent = False
        self.connect_start_time = 0
        self.PRIVMSG_REGEX = re.compile(r"@(.+?)\s+:(.+?)!.+?\s+PRIVMSG\s+#(.+?)\s+:(.+)")

    def _get_twitch_username(self):
        try:
            session = adafruit_requests.Session(self.pool, ssl.create_default_context())
            token = self.secrets["twitch"]["access_token"].replace("oauth:", "")
            headers = {
                "Client-ID": self.secrets["twitch"]["client_id"],
                "Authorization": "Bearer " + token
            }
            response = session.get("https://api.twitch.tv/helix/users", headers=headers)
            data = response.json()
            if "data" in data and data["data"]:
                return data["data"][0]["login"]
            raise RuntimeError("Konnte Twitch-Username nicht ermitteln")
        except Exception as e:
            print("Fehler bei Twitch-API-Anfrage:", e)
            return "default_user"

    def connect(self):
        if not wifi.radio.connected or self.sock:
            print("Keine WiFi-Verbindung oder bereits verbunden")
            return False
        try:
            self.sock = self.pool.socket(self.pool.AF_INET, self.pool.SOCK_STREAM)
            self.sock.settimeout(0)  # Nicht-blockierend
            print("Verbinde mit Twitch IRC...")
            self.sock.connect(("irc.chat.twitch.tv", 6667))
            time.sleep(1)  # Warte auf Verbindungsaufbau
            self.connected = True
            self.commands_sent = False
            self.connect_start_time = time.monotonic()
            print("Verbindung gestartet")
            return True
        except Exception as e:
            if "EINPROGRESS" in str(e) or "[Errno 119]" in str(e):
                print("Verbindung wird aufgebaut (EINPROGRESS)")
                time.sleep(1)  # Warte auf Verbindungsaufbau
                self.connected = True
                self.commands_sent = False
                self.connect_start_time = time.monotonic()
                return True
            print("Verbindung fehlgeschlagen:", e)
            self.disconnect()
            return False

    def send_initial_commands(self):
        if not self.sock or not self.connected or self.commands_sent:
            return
        try:
            print("Sende IRC-Befehle...")
            self.sock.send(bytes(f"PASS {self.secrets['twitch']['access_token']}\r\n", "utf-8"))
            print("PASS gesendet")
            self.sock.send(bytes(f"NICK {self.username}\r\n", "utf-8"))
            print("NICK gesendet")
            self.sock.send(bytes("CAP REQ :twitch.tv/tags\r\n", "utf-8"))
            print("CAP tags gesendet")
            self.sock.send(bytes("CAP REQ :twitch.tv/commands\r\n", "utf-8"))
            print("CAP commands gesendet")
            self.sock.send(bytes(f"JOIN #{TWITCH_CHANNEL}\r\n", "utf-8"))
            print("JOIN gesendet")
            self.commands_sent = True
            print("IRC-Befehle gesendet")
        except Exception as e:
            if "[Errno 32]" in str(e):
                print("Broken pipe beim Senden der IRC-Befehle, Verbindung wird getrennt")
            else:
                print("Fehler beim Senden der Befehle:", e)
            self.disconnect()

    def disconnect(self):
        if self.sock:
            try:
                self.send_message("ehajoOptilia Kamera Offline!")
                self.sock.close()
            except Exception as e:
                print("Fehler beim Trennen:", e)
            self.sock = None
        self.connected = False
        self.commands_sent = False
        print("Twitch getrennt")

    def send_message(self, msg):
        if self.sock and self.connected and self.commands_sent:
            try:
                self.sock.send(bytes(f"PRIVMSG #{TWITCH_CHANNEL} :{msg}\r\n", "utf-8"))
                print(f"Nachricht gesendet: {msg}")
            except Exception as e:
                print("Fehler beim Senden:", e)

    def check_messages(self):
        if not self.sock or not self.connected:
            print("Keine aktive Verbindung")
            return None
        if not self.commands_sent:
            self.send_initial_commands()
            self.send_message("ehajoOptilia Kamera Online!!")
            return None
        try:
            n = self.sock.recv_into(self.buffer)
            if n == 0:
                print("Verbindung verloren")
                self.disconnect()
                return None
            data = self.buffer[:n].decode("utf-8")
            print("IRC-Daten:", data)
            lines = data.split("\r\n")
            for line in lines:
                if not line:
                    continue
                print("IRC-Zeile:", line)
                if line.startswith("PING"):
                    self.sock.send(bytes("PONG :tmi.twitch.tv\r\n", "utf-8"))
                    print("PONG gesendet")
                    continue
                match = self.PRIVMSG_REGEX.match(line)
                if match:
                    tags_str, sender, channel, message = match.groups()
                    print(f"PRIVMSG - Sender: {sender}, Kanal: {channel}, Nachricht: {message}")
                    tags = dict(tag.split("=", 1) for tag in tags_str.split(";"))
                    print("Tags:", tags)
                    if tags.get("custom-reward-id") != TWITCH_CUSTOM_REWARD_ID:
                        print(f"Reward-ID {tags.get('custom-reward-id')} != {TWITCH_CUSTOM_REWARD_ID}")
                        continue
                    text = message.strip().rstrip("xX")
                    print("Verarbeitete Nachricht:", text)
                    try:
                        zoom_val = int(text)
                        if 1 <= zoom_val <= 30:
                            current_time = time.monotonic()
                            if current_time < self.zoom_cooldown:
                                self.send_message("ehajoOptilia Bitte 10 Sekunden warten!")
                                return None
                            self.zoom_cooldown = current_time + 10
                            self.send_message(f"ehajoOptilia Zoom auf {zoom_val}x!")
                            return zoom_val, tags.get("display-name", sender)
                        else:
                            self.send_message("ehajoOptilia Zoom zwischen 1-30!")
                    except ValueError:
                        self.send_message("ehajoOptilia Ungültiger Zoomwert!")
        except Exception as e:
            if "[Errno 11]" in str(e) or "[Errno 116]" in str(e):
                return None  # Keine Daten verfügbar, normal für non-blocking
            print("Fehler beim Empfangen:", e)
            self.disconnect()
            return None