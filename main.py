"""
Miernik powietrza — Raspberry Pi Pico W
OLED + AHT21 + ENS160 + przycisk
- pomiary co 9 s
- strony OLED co 4 s (przycisk = nastepna strona)
- po 60 s OLED zasypia; przycisk budzi
"""
from machine import I2C, Pin
import time
from ssd1306 import SSD1306_I2C
from aht21 import AHT21
from ens160 import ENS160
import pins

MEASURE_MS = 9000
PAGE_MS = 4000
SLEEP_MS = 60000

# --- sprzet ---
i2c_oled = I2C(pins.OLED_I2C_ID, sda=Pin(pins.OLED_SDA), scl=Pin(pins.OLED_SCL), freq=400000)
i2c_sens = I2C(pins.SENS_I2C_ID, sda=Pin(pins.SENS_SDA), scl=Pin(pins.SENS_SCL), freq=400000)
oled = SSD1306_I2C(128, 64, i2c_oled, addr=pins.OLED_ADDR)
aht = AHT21(i2c_sens, pins.AHT21_ADDR)
ens = ENS160(i2c_sens, pins.ENS160_ADDR)
btn = Pin(pins.BUTTON_PIN, Pin.IN, Pin.PULL_UP)

# --- stan pomiarow ---
temp_c = 0.0
hum_rh = 0.0
aqi = 1
aqi_txt = "-"
eco2 = 400
tvoc = 0
ens_ok = False

# --- stan ekranu ---
page = 0
PAGE_COUNT = 4
awake = True
btn_prev = 1
now = time.ticks_ms()
t_wake = now
t_page = now
t_meas = time.ticks_add(now, -MEASURE_MS)  # od razu pierwszy pomiar


def measure():
    global temp_c, hum_rh, aqi, aqi_txt, eco2, tvoc, ens_ok
    try:
        temp_c, hum_rh = aht.read()
        ens.set_compensation(temp_c, hum_rh)
        ens_ok = ens.update()
        aqi = ens.aqi
        aqi_txt = ens.aqi_text()
        eco2 = ens.eco2
        tvoc = ens.tvoc
    except OSError as e:
        print("Blad I2C pomiaru:", e)


def draw_header(title):
    oled.text(title, 0, 0)
    oled.hline(0, 10, 128, 1)


def draw_page():
    oled.fill(0)
    if page == 0:
        draw_header("Klimat")
        oled.text("Temp: {:.1f} C".format(temp_c), 0, 20)
        oled.text("Wilg: {:.1f} %".format(hum_rh), 0, 36)
        oled.text("strona 1/4", 0, 56)
    elif page == 1:
        draw_header("Jakosc powietrza")
        oled.text("AQI: {}".format(aqi), 0, 20)
        oled.text(aqi_txt, 0, 36)
        if not ens_ok:
            oled.text("rozgrzewka...", 0, 48)
        else:
            oled.text("strona 2/4", 0, 56)
    elif page == 2:
        draw_header("eCO2")
        oled.text("{} ppm".format(eco2), 0, 24)
        oled.text("strona 3/4", 0, 56)
    else:
        draw_header("TVOC")
        oled.text("{} ppb".format(tvoc), 0, 24)
        oled.text("strona 4/4", 0, 56)
    oled.show()


def wake():
    global awake, t_wake, t_page
    oled.poweron()
    awake = True
    t_wake = time.ticks_ms()
    t_page = t_wake
    draw_page()


def sleep_display():
    global awake
    oled.poweroff()
    awake = False


def button_pressed():
    """Wykrywa zbocze: puszczony -> wcisniety, z odblokowaniem drgan."""
    global btn_prev
    stan = btn.value()
    pressed = stan == 0 and btn_prev == 1
    btn_prev = stan
    if pressed:
        time.sleep_ms(30)
        if btn.value() != 0:
            return False
    return pressed


# start
measure()
draw_page()
print("Miernik powietrza uruchomiony.")

while True:
    now = time.ticks_ms()

    if button_pressed():
        if not awake:
            wake()
        else:
            page = (page + 1) % PAGE_COUNT
            t_page = now
            t_wake = now  # wcisniecie przedluza czuwanie
            draw_page()

    if time.ticks_diff(now, t_meas) >= MEASURE_MS:
        measure()
        t_meas = now
        if awake:
            draw_page()

    if awake:
        if time.ticks_diff(now, t_page) >= PAGE_MS:
            page = (page + 1) % PAGE_COUNT
            t_page = now
            draw_page()
        if time.ticks_diff(now, t_wake) >= SLEEP_MS:
            sleep_display()

    time.sleep_ms(20)
