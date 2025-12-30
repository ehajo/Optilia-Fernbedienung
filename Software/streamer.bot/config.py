# config.py - Zentrale Konfigurationsdatei (YouTube/Streamer.bot UDP)

# Pin-Konfiguration
PIN_CONFIG = {
    "i2c_scl": "GP1",
    "i2c_sda": "GP0",
    "uart_tx": "GP4",
    "uart_rx": "GP5",
    "poti": "A0",
    "encoder_a": "GP7",
    "encoder_b": "GP8",
    "power_button": "GP15",
    "focus_button": "GP16",
    "freeze_button": "GP19",
    "connected_button": "GP11",
    "autofocus_led_green": "GP17",
    "autofocus_led_red": "GP18",
    "freeze_led_green": "GP20",
    "freeze_led_red": "GP21",
    "power_led_green": "GP14",
    "power_led_red": "GP13",
    "connected_led_green": "GP10",
    "connected_led_red": "GP9",
}

# Zoomstufen (VISCA)
ZOOM_LEVELS = {
    1: 0x0000, 2: 0x16A1, 3: 0x2063, 4: 0x2628, 5: 0x2A1D,
    6: 0x2D13, 7: 0x2F6D, 8: 0x3161, 9: 0x330D, 10: 0x3486,
    11: 0x35D7, 12: 0x3709, 13: 0x3820, 14: 0x3920, 15: 0x3A0A,
    16: 0x3ADD, 17: 0x3B9C, 18: 0x3C46, 19: 0x3CDC, 20: 0x3D60,
    21: 0x3D9C, 22: 0x3DD8, 23: 0x3E14, 24: 0x3E50, 25: 0x3E8C,
    26: 0x3EC8, 27: 0x3F04, 28: 0x3F40, 29: 0x3F7C, 30: 0x3FFF,
}

# Display-Konfiguration
DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 64

# Timing
ZOOM_DEBOUNCE = 0.0
BRIGHTNESS_DEBOUNCE = 0.05

# Override-Timeout: wie lange !zoom per UDP aktiv bleibt
ZOOM_OVERRIDE_TIMEOUT = 20  # Sekunden

# UDP (Streamer.bot -> Pico)
UDP_PORT = 4242
