"""Test 3: tekst na OLED."""
from machine import I2C, Pin
from ssd1306 import SSD1306_I2C
import pins

i2c = I2C(pins.OLED_I2C_ID, sda=Pin(pins.OLED_SDA), scl=Pin(pins.OLED_SCL), freq=400000)
oled = SSD1306_I2C(128, 64, i2c, addr=pins.OLED_ADDR)

oled.fill(0)
oled.text("OLED OK", 0, 0)
oled.text("Miernik powietrza", 0, 16)
oled.text("Pico W", 0, 32)
oled.show()
print("Jesli widzisz tekst na OLED — dziala.")
