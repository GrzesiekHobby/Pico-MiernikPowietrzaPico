# Wspólna mapa pinów — używana przez testy i main.py
# Raspberry Pi Pico / Pico W + MicroPython

# OLED na I2C0 (osobna szyna)
OLED_SDA = 0   # GP0
OLED_SCL = 1   # GP1
OLED_I2C_ID = 0
OLED_ADDR = 0x3C

# Moduł AHT21 + ENS160 na I2C1 (osobna szyna)
SENS_SDA = 2   # GP2
SENS_SCL = 3   # GP3
SENS_I2C_ID = 1
AHT21_ADDR = 0x38
ENS160_ADDR = 0x53

# Przycisk: GP15 → GND przy wciśnięciu (wewnętrzny pull-up)
BUTTON_PIN = 15
