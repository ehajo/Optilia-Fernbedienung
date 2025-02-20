# Projekt: Twitch-gesteuerte Kamera-Fernbedienung mit Raspberry Pi Pico W

Dieses Projekt ist eine Fernbedienung für eine VISCA-kompatible Kamera (z.B. Optilia), die über einen Raspberry Pi Pico W gesteuert wird. Es ermöglicht die Steuerung von Zoom, Helligkeit, Autofokus und Freeze sowohl manuell als auch über Twitch-Chatbefehle. Ein OLED-Display zeigt den aktuellen Status an, und LEDs geben visuelles Feedback zu den Funktionen.

## Funktionen

1. **Manuelle Steuerung**:
   - **Power**: Ein-/Ausschalten der Kamera und Fernbedienung über einen Taster (GP15).
   - **Zoom**: Stufenloser Zoom (1-30x) über ein Potentiometer.
   - **Brightness**: Helligkeit (0-20) über einen Rotary Encoder.
   - **Autofokus**: Ein-/Ausschalten über einen Taster (GP14).
   - **Freeze**: Einfrieren des Kamerabildes über einen Taster (GP13).
   - **Twitch-Modus**: Umschalten zwischen manuellem und Twitch-Modus über einen Taster (GP11).

2. **Twitch-Steuerung**:
   - Im Twitch-Modus kann der Zoom über Chatbefehle mit einem Custom Reward gesteuert werden (z.B. `!zoom 5x`).
   - Der Zoomwert wird zwischen 1 und 30 akzeptiert, mit einem 10-Sekunden-Cooldown zwischen Änderungen.
   - Rückmeldungen werden in den Twitch-Chat gesendet (z.B. "ehajoOptilia Zoom auf 5x!").

3. **Display**:
   - Ein 128x64 OLED-Display (SSD1306, I2C) zeigt:
     - "Live" oder "Freeze" (oben links).
     - "AF" oder "MF" (unten links).
     - "Bright: [0-20]" (unten rechts).
     - "Zoom: [1-30]x" (mitte rechts).
     - "Manual" oder "Twitch" (unten rechts).
     - WiFi- und Twitch-Status als Smileys rechts oben ("wifi:" und "twitch:" mit lachendem oder traurigem Smiley).

4. **LEDs**:
   - **Power**: Rot im OFF-Zustand, Grün im ON-Zustand.
   - **Connected/Twitch**: Grün im Manual-Modus oder wenn Twitch nicht verbunden, Rot wenn Twitch verbunden.
   - **Autofokus**: Grün bei AF an, Rot bei AF aus.
   - **Freeze**: Grün bei Freeze aus, Rot bei Freeze an.
   - Alle LEDs sind im OFF-Zustand ausgeschaltet.

5. **Initialisierung**:
   - Beim Start wird die Kamera ausgeschaltet (OFF-Zustand).
   - Brightness wird auf 4 initialisiert und bleibt stabil, bis der Encoder bewegt wird.

## Hardwareanforderungen

- **Raspberry Pi Pico W**: Mikrocontroller mit WiFi für Twitch-Verbindung.
- **VISCA-kompatible Kamera**: Über UART (VISCA-Protokoll) gesteuert.
- **128x64 OLED-Display (SSD1306)**: Über I2C angeschlossen (SCL: GP9, SDA: GP8).
- **Rotary Encoder**: Für Helligkeit (DT: GP6, CLK: GP7).
- **Potentiometer**: Für Zoom (ADC0: GP26).
- **Taster**:
  - Power: GP15
  - Connected/Twitch: GP11
  - Autofokus: GP14
  - Freeze: GP13
- **LEDs**:
  - Power (Rot: GP10, Grün: GP18)
  - Connected (Rot: GP16, Grün: GP17)
  - Autofokus (Rot: GP19, Grün: GP20)
  - Freeze (Rot: GP21, Grün: GP22)

## Softwareanforderungen

- **CircuitPython**: Version 8.x oder höher auf dem Pico W installiert.
- **Bibliotheken**:
  - `adafruit_bus_device`
  - `adafruit_ssd1306` (für OLED)
  - `adafruit_requests` (für Twitch-API)

## Installation

1. **CircuitPython installieren**:
   - Lade die neueste CircuitPython-UF2-Datei für den Pico W von [circuitpython.org](https://circuitpython.org) herunter und installiere sie auf dem Pico W.

2. **Bibliotheken hinzufügen**:
   - Kopiere die erforderlichen Bibliotheken in den `lib`-Ordner des Pico W:
     - `adafruit_bus_device`
     - `adafruit_ssd1306`
     - `adafruit_requests`

3. **Code hochladen**:
   - Kopiere `main.py`, `twitch_integration.py`, `visca_commands.py`, `hardware_setup.py`, `config.py` und `secrets.json` auf den Pico W.

4. **Konfiguration**:
   - Passe `secrets.json` an:
     ```json
     {
         "wifi": {
             "ssid": "dein_wifi_name",
             "password": "dein_wifi_passwort"
         },
         "twitch": {
             "client_id": "dein_twitch_client_id",
             "access_token": "oauth:dein_twitch_access_token"
         }
     }
     ```
   - Passe `config.py` an:
     ```python
     TWITCH_CHANNEL = "dein_twitch_channel"
     TWITCH_CUSTOM_REWARD_ID = "deine_reward_id"
     ZOOM_DEBOUNCE = 0.1
     BRIGHTNESS_DEBOUNCE = 0.1
     TWITCH_ZOOM_TIMEOUT = 10
     DISPLAY_WIDTH = 128
     DISPLAY_HEIGHT = 64
     ```

5. **Hardware anschließen**:
   - Verbinde die Hardware gemäß den oben genannten Pin-Belegungen.

## Bedienung

1. **Start**:
   - Beim Einschalten zeigt das OLED "Booting...", "WiFi verbinden...", "WiFi OK", "Initialisiere..." und "Initialisiert!". Danach wird die Kamera ausgeschaltet, und das Display bleibt leer (OFF-Zustand).

2. **Power-Taster (GP15)**:
   - Einschalten: Wechselt in den Manual-Modus, Kamera wird eingeschaltet, grüne LEDs leuchten.
   - Ausschalten: Wechselt in den OFF-Zustand, Kamera wird ausgeschaltet, alle LEDs außer der roten Power-LED sind aus.

3. **Connected-Taster (GP11)**:
   - Schaltet zwischen Manual- und Twitch-Modus um. Im Twitch-Modus wird die Verbindung zu Twitch hergestellt.

4. **Focus-Taster (GP14)**:
   - Schaltet zwischen Autofokus (AF) und manuellem Fokus (MF) um.

5. **Freeze-Taster (GP13)**:
   - Friert das Kamerabild ein oder gibt es frei.

6. **Potentiometer**:
   - Stellt den Zoomwert (1-30x) ein, angezeigt als "Zoom: [wert]x".

7. **Rotary Encoder**:
   - Stellt die Helligkeit (0-20) ein, angezeigt als "Bright: [wert]".

8. **Twitch-Chat**:
   - Sende einen Befehl wie `!zoom 5x` mit dem passenden Custom Reward, um den Zoom im Twitch-Modus zu ändern.

## Lizenz

Dieses Projekt steht unter der MIT-Lizenz. Siehe [LICENSE](LICENSE) für Details.

## Dank

Vielen Dank an alle, die zur Entwicklung dieses Projekts beigetragen haben!