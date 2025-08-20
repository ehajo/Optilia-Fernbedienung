# boot.py — Wartungsmodus über Power-Taste (GP15)
# Beim Einstecken/Reset:
#   - Power-Taste gedrückt halten  -> USB-Laufwerk für den PC sichtbar & SCHREIBBAR (RW)
#   - Power-Taste NICHT gedrückt   -> USB-Laufwerk für den PC AUS (versteckt),
#                                     ABER Dateisystem bleibt für das Programm SCHREIBBAR

import time
import board
import digitalio
import storage

# Power-Button an GP15 (active-low)
btn = digitalio.DigitalInOut(board.GP15)
btn.switch_to_input(pull=digitalio.Pull.UP)
time.sleep(0.1)  # kurze Stabilisierung

pressed = (btn.value == False)

if pressed:
    # Wartungsmodus: Host darf zugreifen & schreiben
    storage.enable_usb_drive()
    storage.remount("/", False)   # RW für Programm & Host
else:
    # Betriebsmodus: Host sieht kein Laufwerk, Programm darf schreiben (für Tokens/Logs)
    storage.disable_usb_drive()
    storage.remount("/", False)   # RW für Programm
