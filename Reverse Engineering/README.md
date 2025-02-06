# Optilia – Kamera-Steuerung via Twitch und Hardware

Optilia ist ein Open-Source-Projekt, das es ermöglicht, eine Kamera (über VISCA) mithilfe eines Raspberry Pi Pico W und CircuitPython sowohl manuell (über Potentiometer und Taster) als auch über Twitch-Chat-Befehle zu steuern. Der Code unterstützt zusätzlich die Anzeige von Statusinformationen über ein OLED-Display.

## Features

- **Manuelle Kamera-Steuerung**  
  - Zoomsteuerung via Potentiometer  
  - Freeze-Funktion (Ein-/Ausschalten) per Taste  
  - Umschalten zwischen Autofokus (AF) und manueller Fokussierung (MF)

- **Twitch-Steuerung**  
  - `!zoom`-Befehl im Twitch-Chat, der **nur interpretiert wird**, wenn er in hervorgehobenen Nachrichten gesendet wird  
  - Anzeige des Zuschauernamens als Overlay (Format: `KAMERAKIND: [ZUSCHAUERNAME]`)  
  - 10-Sekunden-Cooldown für `!zoom`-Befehle

- **OLED-Display**  
  - Anzeige des Kamerastatus im unteren Bereich:  
    - **Links oben:** Fester Text `Freeze`  
    - **Links unten:** AF/MF-Status  
    - **Rechts unten:** Zoomwert und Modus (`Twitch` oder `Manual`)  
  - Anzeige des Verbindungsstatus im oberen rechten Bereich:  
    - WiFi-Status (z. B. `WiFi: connected`)  
    - Twitch-Status (z. B. `Twitch: connected` oder `Twitch: off`)  
    - Kleine Bitmap-Smileys zeigen den Twitch-Status an (lachend bei verbunden, traurig bei nicht verbunden)

- **Optimierte Kommunikation**  
  - VISCA-Befehle und Display-Updates werden nur gesendet, wenn sich relevante Werte (Zoom, Override) ändern

## Hardware

Für dieses Projekt benötigst du folgende Hardware:

- **Raspberry Pi Pico W** (oder ein kompatibles Board mit WLAN)
- **OLED-Display** (z. B. SSD1306, I²C, 128×64 Pixel)
- **UART-Verbindung** zur Kamera (VISCA-Steuerung)
- **Potentiometer** (z. B. 10 kΩ) für die Zoomsteuerung
- **Taster** für:  
  - **Power:** (EIN/AUS, z. B. an GP15)  
  - **Fokus:** (AF/MF, z. B. an GP16)  
  - **Freeze:** (z. B. an GP19)  
  - **Connected-Modus:** (Twitch EIN/AUS, z. B. an GP11)
- **LEDs** zur Statusanzeige:  
  - **Power-LED:** Grün bei System On, Rot bei System Off (z. B. an GP14/GP13)  
  - **Connected-LEDs:**  
    - Eine LED (z. B. an GP10, grün) leuchtet, wenn die Twitch-Verbindung aktiv ist  
    - Eine LED (z. B. an GP9, rot) zeigt an, dass der Connected-Modus nicht aktiviert ist
- **Verkabelung:**  
  - I²C-Leitungen (SCL, SDA) zum OLED-Display  
  - UART-Leitungen (TX, RX) zur Kamera  
  - Analoger Eingang für das Potentiometer  
  - Digitale Eingänge für die Taster (mit Pull-Up-Widerständen, falls nicht intern vorhanden)  
  - Digitale Ausgänge für die LEDs

## Software & Installation

### CircuitPython installieren

1. **CircuitPython herunterladen:**  
   Besuche [CircuitPython.org](https://circuitpython.org/board/raspberry_pi_pico_w/) und lade die passende Firmware für deinen Raspberry Pi Pico W herunter.

2. **Board in den Bootloader-Modus versetzen:**  
   Halte die BOOTSEL-Taste gedrückt, während du den Pico W per USB anschließt, und lasse sie dann los.

3. **Firmware flashen:**  
   Kopiere die heruntergeladene UF2-Datei auf den Pico W (der als Wechseldatenträger erscheint).

4. **Benötigte Bibliotheken installieren:**  
   Lade das [Adafruit CircuitPython Bundle](https://circuitpython.org/libraries) herunter und kopiere die benötigten Bibliotheken (z. B. `adafruit_ssd1306`, `adafruit_requests`, `socketpool` etc.) in den `lib`-Ordner auf dem CIRCUITPY-Laufwerk.

### Code einrichten

1. **Repository klonen oder ZIP herunterladen:**  
   Klone das GitHub-Repository oder lade die ZIP-Datei herunter und entpacke sie.

2. **Secrets konfigurieren:**  
   Erstelle im Hauptverzeichnis eine Datei namens `secrets.json` mit folgendem Inhalt (ersetze die Platzhalter):

   ```json
   {
     "wifi": {
       "ssid": "dein-ssid",
       "password": "dein-passwort"
     },
     "twitch": {
       "client_id": "dein_client_id",
       "access_token": "oauth:deinaccesstoken"
     }
   }
   ```

3. **Code auf das Board kopieren:**  
   Kopiere die Datei `code.py` auf das CIRCUITPY-Laufwerk.

4. **Neustart:**  
   Schließe deinen Pico W an und starte ihn neu.

## Nutzung

- **System ein-/ausschalten:**  
  Drücke die Power-Taste (GP15), um das Gesamtsystem ein- oder auszuschalten.  
  - **System Off:**  
    Das Display ist leer, und nur die Power-LED leuchtet rot.  
  - **System On:**  
    Die Kamera wird aktiviert, die Power-LED wechselt zu grün, und im oberen rechten Bereich werden `WiFi: connected` und `Twitch: off` angezeigt. Im unteren Bereich erscheinen der Kamerastatus (Freeze, AF/MF, Zoom, Modus).

- **Twitch-Connected-Modus aktivieren:**  
  Drücke die Connected-Taste (GP11) im System-On-Zustand.  
  - Falls Twitch nicht aktiviert ist, leuchtet die zugehörige LED (GP9) rot.  
  - Wird der Modus aktiviert, baut die Software die Twitch-IRC-Verbindung auf, die grüne LED (GP10) leuchtet, und im Display erscheint `Twitch: connected`.  
  - Wird der Modus deaktiviert, bleibt `Twitch: off` und die LED (GP9) leuchtet rot.

- **Twitch-Chatsteuerung:**  
  Sende im Twitch-Chat einen `!zoom`-Befehl – dieser wird nur interpretiert, wenn die Nachricht hervorgehoben ist.  
  Beim Empfang eines hervorgehobenen Befehls wird zudem der Name des Zuschauers als Overlay (Format: `KAMERAKIND: [ZUSCHAUERNAME]`) angezeigt.

- **Manuelle Steuerung:**  
  Der Zoomwert wird standardmäßig über das Potentiometer gesteuert. Freeze- und Fokus-Tasten schalten den entsprechenden Modus um.

## Anpassungen und Erweiterungen

- **Overlay-Text für Zuschauername:**  
  Der Code enthält eine Funktion, die den Zuschauernamen in genau 20 Zeichen (aufgeteilt in zwei Blöcke à 10 Zeichen) umwandelt und per VISCA-Befehl an die Kamera sendet.  
  Die Umwandlung erfolgt wie folgt:  
  - Großbuchstaben A–Z: A → 0x00, …, Z → 0x19  
  - Ziffern: 1 → 0x1E, 2 → 0x1F, …, 9 → 0x26, 0 → 0x27  
  - Alle anderen Zeichen werden als Leerzeichen (0x42) kodiert  
  Die Daten werden in zwei VISCA-Befehle aufgeteilt:  
  - Erster Block: `0x73, 0x20, ... , 0xFF`  
  - Zweiter Block: `0x73, 0x30, ... , 0xFF`

- **Twitch-IRC-Capabilities:**  
  Der Code fordert die IRC-Capabilities `twitch.tv/tags` und `twitch.tv/commands` an, sodass Informationen wie `msg-id`, `highlighted` und `display-name` verfügbar sind.

- **Optimierung:**  
  VISCA-Befehle und Display-Updates werden nur gesendet, wenn sich relevante Werte (z. B. Zoomwert oder Override) geändert haben.

## Lizenz

Dieses Projekt ist Open Source und wird unter der MIT License bereitgestellt. Weitere Details findest du in der [LICENSE](LICENSE)-Datei.
