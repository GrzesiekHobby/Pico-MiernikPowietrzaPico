"""Test OLED — piny z pins.py (GP0/GP1)."""
from machine import I2C, Pin
import time
from ssd1306 import SSD1306_I2C
import pins

FREQ = getattr(pins, "OLED_I2C_FREQ", 100_000)
i2c = I2C(pins.OLED_I2C_ID, sda=Pin(pins.OLED_SDA), scl=Pin(pins.OLED_SCL), freq=FREQ)
time.sleep_ms(20)
print("test_oled freq", FREQ, "addr", hex(pins.OLED_ADDR))
found = i2c.scan()
print("scan", [hex(a) for a in found])
if pins.OLED_ADDR not in found:
    print("BRAK 0x3C — VCC/GND/SDA/SCL")
    raise SystemExit(1)
i2c.writeto(pins.OLED_ADDR, b"\x80\xae")
print("probe 0xAE OK")
oled = SSD1306_I2C(128, 64, i2c, addr=pins.OLED_ADDR)
oled.fill(0)
oled.text("OLED OK", 0, 0)
oled.text("Miernik powietrze", 0, 16)
oled.text("Pico W %dkHz" % (FREQ // 1000), 0, 32)
oled.text("GP0/1", 0, 48)
oled.show()
print("OK — patrz OLED")
