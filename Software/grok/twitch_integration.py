# twitch_integration.py — Twitch Device-Flow + IRC (CircuitPython)
# - Device Code Flow: zeigt URL+Code in Konsole & auf OLED, pollt bis bestätigt
# - Token-Handling: validate -> refresh -> device flow fallback
# - Speichert Access-/Refresh-Token in secrets.json (falls RW)
# - Blocking connect (5s) -> danach non-blocking recv_into(...)
# - Liest NUR Channel-Points (custom-reward-id == TWITCH_CUSTOM_REWARD_ID)
# - Rückgabe (zoom:int, sender:str) bei Erfolg, sonst None

import wifi
import socketpool
import ssl
import adafruit_requests
import time
import re
import json

from config import TWITCH_CHANNEL, TWITCH_CUSTOM_REWARD_ID

OAUTH_BASE = "https://id.twitch.tv/oauth2"
DEVICE_CODE_URL = OAUTH_BASE + "/device"
TOKEN_URL = OAUTH_BASE + "/token"
VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
SCOPES = "chat:read chat:edit"


class TwitchController:
    def __init__(self, oled, secrets):
        self.oled = oled
        self.secrets = secrets

        self.pool = socketpool.SocketPool(wifi.radio)
        self.sock = None
        self.socket_open = False
        self.joined_channel = False

        self.requests = None
        self._rx_buf = bytearray(4096)

    # ---------- Status ----------
    def is_socket_open(self):
        return self.socket_open

    def is_joined(self):
        return self.joined_channel

    # ---------- HTTP Session ----------
    def _requests(self):
        if self.requests is None:
            ctx = ssl.create_default_context()
            self.requests = adafruit_requests.Session(self.pool, ctx)
        return self.requests

    # ---------- Secrets speichern ----------
    def _save_tokens(self, access_token, refresh_token, login=None):
        try:
            self.secrets["twitch_token"] = access_token
            if refresh_token:
                self.secrets["twitch_refresh_token"] = refresh_token
            if login:
                self.secrets["twitch_nick"] = login

            try:
                with open("secrets.json", "r") as f:
                    data = json.load(f)
            except Exception:
                data = {}
            data.update(self.secrets)
            with open("secrets.json", "w") as f:
                json.dump(data, f)
            print("Tokens gespeichert (secrets.json).")
        except Exception as e:
            print("Token-Speichern fehlgeschlagen:", e)

    # ---------- Token Utilities ----------
    def _validate_token(self, token):
        if not token:
            return (None, None)
        try:
            r = self._requests().get(VALIDATE_URL, headers={"Authorization": "OAuth " + token})
            if r.status_code == 200:
                d = r.json()
                return (d.get("login"), d.get("expires_in"))
        except Exception as e:
            print("Validate-Fehler:", e)
        return (None, None)

    def _refresh_token(self):
        rt = self.secrets.get("twitch_refresh_token")
        cid = self.secrets.get("twitch_client_id")
        csec = self.secrets.get("twitch_client_secret")
        if not rt or not cid:
            return None
        try:
            data = {"grant_type": "refresh_token", "refresh_token": rt, "client_id": cid}
            if csec:
                data["client_secret"] = csec
            r = self._requests().post(TOKEN_URL, data=data)
            if r.status_code == 200:
                d = r.json()
                acc = d.get("access_token")
                ref = d.get("refresh_token") or rt
                login, _ = self._validate_token(acc)
                self._save_tokens(acc, ref, login)
                return acc
            else:
                print("Refresh-Fehler:", r.status_code)
        except Exception as e:
            print("Refresh-Exception:", e)
        return None

    def _show_device_code(self, user_code, verification_uri):
        try:
            if not self.oled:
                print("Gerätecode:", user_code, "URL:", verification_uri)
                return
            self.oled.fill(0)
            self.oled.text("Twitch Login", 0, 0, 1)
            self.oled.text("URL:", 0, 12, 1)
            uri = verification_uri or ""
            self.oled.text(uri[:20], 0, 22, 1)
            self.oled.text(uri[20:40], 0, 32, 1)
            self.oled.text(uri[40:60], 0, 42, 1)
            self.oled.text("Code:", 0, 54, 1)
            self.oled.text(user_code or "", 40, 54, 1)
            self.oled.show()
        except Exception as e:
            print("OLED-Fehler (Device-Code):", e)

    def _oled_info(self, line1, line2=""):
        try:
            if not self.oled:
                print(line1, line2)
                return
            self.oled.fill(0)
            self.oled.text(line1, 0, 0, 1)
            if line2:
                self.oled.text(line2, 0, 12, 1)
            self.oled.show()
        except Exception:
            pass

    def _device_code_flow(self):
        cid = self.secrets.get("twitch_client_id")
        csec = self.secrets.get("twitch_client_secret")
        if not cid:
            print("Kein twitch_client_id in secrets.json gefunden.")
            return None

        try:
            # Schritt 1: Device Code holen
            r = self._requests().post(DEVICE_CODE_URL, data={"client_id": cid, "scope": SCOPES})
            if r.status_code != 200:
                print("Device-Code-Fehler (init):", r.status_code)
                return None
            info = r.json()
            device_code = info.get("device_code")
            user_code = info.get("user_code")
            verification_uri = info.get("verification_uri") or "https://www.twitch.tv/activate"
            verification_uri_complete = info.get("verification_uri_complete")
            interval = int(info.get("interval", 5))
            expires_in = int(info.get("expires_in", 1800))
            deadline = time.monotonic() + expires_in

            # Anzeigen (OLED + Konsole)
            self._show_device_code(user_code, verification_uri)
            print("=== Twitch Device Login ===")
            print("Öffne am Handy/PC:", verification_uri)
            if verification_uri_complete:
                print("Direktlink:", verification_uri_complete)
            print("Gib diesen Code ein:", user_code)
            print(f"Zeitfenster: {expires_in} Sekunden.")

            # Schritt 2: Polling
            while time.monotonic() < deadline:
                time.sleep(interval)
                data = {
                    "client_id": cid,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                }
                if csec:
                    data["client_secret"] = csec
                tr = self._requests().post(TOKEN_URL, data=data)

                if tr.status_code == 200:
                    d = tr.json()
                    acc = d.get("access_token")
                    ref = d.get("refresh_token")
                    login, _ = self._validate_token(acc)
                    self._save_tokens(acc, ref, login)
                    self._oled_info("Twitch OK", "Token erhalten")
                    print("Twitch: Token erhalten. Login:", login)
                    return acc

                # Erwartete Warte-Antworten (400+JSON)
                j = None
                try:
                    j = tr.json()
                except Exception:
                    j = None
                err = (j.get("error") if j else "") or ""
                if err == "authorization_pending":
                    continue
                if err == "slow_down":
                    interval += 2
                    continue
                if err in ("expired_token", "access_denied", "unsupported_grant_type",
                           "invalid_device_code", "invalid_client", "invalid_grant"):
                    print("Device-Token-Fehler:", err)
                    return None
                if tr.status_code == 400:
                    # Manchmal 400 ohne JSON -> einfach weiter warten
                    continue

                print("Device-Token-Fehler, Status:", tr.status_code)
                return None

            print("Zeit abgelaufen, kein Token erhalten.")
            return None

        except Exception as e:
            print("Device-Flow-Exception:", e)
            return None

    def ensure_user_token(self):
        # 1) validate
        tok = self.secrets.get("twitch_token")
        login, exp = self._validate_token(tok)
        if login and exp and exp > 60:
            if not self.secrets.get("twitch_nick"):
                self.secrets["twitch_nick"] = login
            return tok
        # 2) refresh
        new_tok = self._refresh_token()
        if new_tok:
            return new_tok
        # 3) device flow
        return self._device_code_flow()

    # ---------- IRC ----------
    def connect(self):
        if not wifi.radio.connected:
            print("Twitch: Kein WiFi.")
            return False
        if self.sock:
            print("Twitch: Bereits verbunden.")
            return True
        try:
            token = self.ensure_user_token()
            if not token:
                print("Kein gültiges Twitch-User-Token verfügbar.")
                return False

            nick = (self.secrets.get("twitch_nick") or TWITCH_CHANNEL or "").lower()
            if not nick:
                login, _ = self._validate_token(token)
                if login:
                    nick = login.lower()
                    self.secrets["twitch_nick"] = nick
                    self._save_tokens(token, self.secrets.get("twitch_refresh_token"), login)

            self.sock = self.pool.socket(self.pool.AF_INET, self.pool.SOCK_STREAM)
            self.sock.settimeout(5)
            self.sock.connect(("irc.chat.twitch.tv", 6667))

            channel = f"#{TWITCH_CHANNEL}"
            self._send_line(f"PASS oauth:{token}")
            self._send_line(f"NICK {nick}")
            self._send_line("CAP REQ :twitch.tv/tags")
            self._send_line("CAP REQ :twitch.tv/commands")
            self._send_line("CAP REQ :twitch.tv/membership")
            self._send_line(f"JOIN {channel}")

            self.sock.settimeout(0)
            self.socket_open = True
            self.joined_channel = False

            if self.oled:
                try:
                    self.oled.fill(0)
                    self.oled.text("Twitch: Socket OK", 0, 0, 1)
                    self.oled.text("Warte auf JOIN...", 0, 10, 1)
                    self.oled.show()
                except Exception:
                    pass

            print("Twitch: Verbunden, JOIN wird erwartet...")
            return True
        except Exception as e:
            print("Twitch Connect Fehler:", e)
            self.disconnect()
            return False

    def disconnect(self):
        try:
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass
        finally:
            self.sock = None
            self.socket_open = False
            self.joined_channel = False

    # ---------- IRC I/O ----------
    def _send_line(self, line):
        if not self.sock:
            return
        try:
            self.sock.send(bytes(line + "\r\n", "utf-8"))
        except Exception as e:
            print("Twitch Sendefehler:", e)

    def _handle_system_ping(self, line):
        if line.startswith("PING"):
            try:
                self.sock.send(bytes(line.replace("PING", "PONG"), "utf-8"))
            except Exception:
                pass

    def _check_join_ack(self, line):
        if " 001 " in line:
            self.socket_open = True
        if (" JOIN #" + TWITCH_CHANNEL) in line or " 353 " in line:
            if not self.joined_channel:
                print("Twitch: JOIN bestätigt.")
            self.joined_channel = True
        if ("Login authentication failed" in line
            or "Improperly formatted auth" in line
            or "Error logging in" in line
            or "authentication failed" in line.lower()):
            print("Twitch IRC Auth FEHLGESCHLAGEN -> 'twitch_token' & 'twitch_nick' prüfen.")
            self.disconnect()

    def _parse_tags(self, tag_str):
        tags = {}
        for p in tag_str.split(";"):
            if "=" in p:
                k, v = p.split("=", 1)
                tags[k] = v
        return tags

    def receive_zoom_command(self):
        """
        Non-blocking: liest IRC, beantwortet PING, setzt join-Status.
        Erwartet PRIVMSG mit Tag 'custom-reward-id' == TWITCH_CUSTOM_REWARD_ID.
        Liest erste Zahl 1..30 aus der Nachricht.
        Rückgabe: (zoom:int, sender:str) oder None
        """
        if not self.sock:
            return None
        try:
            n = self.sock.recv_into(self._rx_buf)
            if n <= 0:
                return None
            data = bytes(memoryview(self._rx_buf)[:n]).decode("utf-8", "ignore")
            lines = data.split("\r\n")
        except OSError as e:
            err = getattr(e, "errno", None)
            if err in (11, 116, 110):
                return None
            print("Twitch Empfangsfehler:", e)
            self.disconnect()
            return None
        except Exception as e:
            print("Twitch Empfangsfehler:", e)
            self.disconnect()
            return None

        for line in lines:
            if not line:
                continue
            # print("IRC:", line)  # Debug bei Bedarf

            self._handle_system_ping(line)
            self._check_join_ack(line)

            if "PRIVMSG" not in line:
                continue

            tags = {}
            prefix_end = 0
            if line.startswith("@"):
                tag_end = line.find(" ")
                if tag_end > 0:
                    tag_str = line[1:tag_end]
                    tags = self._parse_tags(tag_str)
                    prefix_end = tag_end + 1

            # Nur Channel-Points-Reward
            reward_id = tags.get("custom-reward-id")
            if reward_id != TWITCH_CUSTOM_REWARD_ID:
                continue

            # Nachricht (nach " :")
            msg_start = line.find(" :", prefix_end)
            message = line[msg_start + 2:] if msg_start != -1 else ""
            m = re.search(r"\b(\d{1,2})\b", message)
            if not m:
                continue
            try:
                val = int(m.group(1))
            except ValueError:
                continue
            if not (1 <= val <= 30):
                continue

            sender = tags.get("display-name", "twitch")
            print(f"Twitch Reward: {sender} -> Zoom {val}x")
            return (val, sender)

        return None
