# hardware_setup.py - Hardware-Initialisierung

import board
import busio
import analogio
import digitalio
import rotaryio
from adafruit_ssd1306 import SSD1306_I2C
from config import PIN_CONFIG, DISPLAY_WIDTH, DISPLAY_HEIGHT

def setup_hardware():
    # I2C und OLED
    i2c = busio.I2C(
        scl=getattr(board, PIN_CONFIG["i2c_scl"]),
        sda=getattr(board, PIN_CONFIG["i2c_sda"])
    )
    oled = SSD1306_I2C(DISPLAY_WIDTH, DISPLAY_HEIGHT, i2c)

    # UART für VISCA
    uart = busio.UART(
        tx=getattr(board, PIN_CONFIG["uart_tx"]),
        rx=getattr(board, PIN_CONFIG["uart_rx"]),
        baudrate=9600,
        timeout=1
    )

    # Potentiometer
    poti = analogio.AnalogIn(getattr(board, PIN_CONFIG["poti"]))

    # Encoder
    encoder = rotaryio.IncrementalEncoder(
        getattr(board, PIN_CONFIG["encoder_a"]),
        getattr(board, PIN_CONFIG["encoder_b"])
    )

    # Taster und LEDs
    pins = {}
    for name, pin in PIN_CONFIG.items():
        if "button" in name:
            btn = digitalio.DigitalInOut(getattr(board, pin))
            btn.direction = digitalio.Direction.INPUT
            btn.pull = digitalio.Pull.UP
            pins[name] = btn
        elif "led" in name:
            led = digitalio.DigitalInOut(getattr(board, pin))
            led.direction = digitalio.Direction.OUTPUT
            led.value = False
            pins[name] = led

    return pins, uart, i2c, oled, encoder, poti
