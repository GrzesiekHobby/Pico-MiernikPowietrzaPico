"""Test 1: skan obu szyn I2C — czy widać OLED i czujniki."""
from machine import I2C, Pin
import pins

i2c_oled = I2C(pins.OLED_I2C_ID, sda=Pin(pins.OLED_SDA), scl=Pin(pins.OLED_SCL), freq=400000)
i2c_sens = I2C(pins.SENS_I2C_ID, sda=Pin(pins.SENS_SDA), scl=Pin(pins.SENS_SCL), freq=400000)

print("Szyna OLED (I2C0, GP0/GP1):", [hex(a) for a in i2c_oled.scan()])
print("  Oczekiwane: 0x3c (OLED)")
print("Szyna czujnikow (I2C1, GP2/GP3):", [hex(a) for a in i2c_sens.scan()])
print("  Oczekiwane: 0x38 (AHT21) i 0x53 (ENS160)")
