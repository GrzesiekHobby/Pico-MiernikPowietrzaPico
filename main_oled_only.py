"""
Miernik powietrza — publiczny kanon, bez WiFi.
OLED GP0/1 · AHT+ENS GP2/3 · BTN GP15
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
PAGE_COUNT = 4

of = getattr(pins, "OLED_I2C_FREQ", 100_000)
sf = getattr(pins, "SENS_I2C_FREQ", 100_000)

# Jedna para busów — nie re-init I2C w pętli (to „zapycha” RP2040)
i2c_oled = I2C(pins.OLED_I2C_ID, sda=Pin(pins.OLED_SDA), scl=Pin(pins.OLED_SCL), freq=of)
i2c_sens = I2C(pins.SENS_I2C_ID, sda=Pin(pins.SENS_SDA), scl=Pin(pins.SENS_SCL), freq=sf)
time.sleep_ms(20)
print("OLED", [hex(a) for a in i2c_oled.scan()], "SENS", [hex(a) for a in i2c_sens.scan()])

oled = None
err = None
for n in range(2):
    try:
        oled = SSD1306_I2C(128, 64, i2c_oled, addr=pins.OLED_ADDR)
        break
    except OSError as e:
        err = e
        print("OLED init", n + 1, e)
        time.sleep_ms(30)
if oled is None:
    raise SystemExit("OLED EIO — styki/USB off 5s. %r" % (err,))

aht = AHT21(i2c_sens, pins.AHT21_ADDR)
ens = ENS160(i2c_sens, pins.ENS160_ADDR)
btn = Pin(pins.BUTTON_PIN, Pin.IN, Pin.PULL_UP)

temp_c = 0.0
hum_rh = 0.0
aqi = 1
aqi_txt = "-"
eco2 = 400
tvoc = 0
ens_ok = False
page = 0
awake = True
btn_prev = 1
now = time.ticks_ms()
t_wake = now
t_page = now
t_meas = time.ticks_add(now, -MEASURE_MS)


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
        print("I2C meas", e)


def draw_page():
    try:
        oled.fill(0)
        if page == 0:
            oled.text("Klimat", 0, 0)
            oled.hline(0, 10, 128, 1)
            oled.text("Temp: {:.1f} C".format(temp_c), 0, 20)
            oled.text("Wilg: {:.1f} %".format(hum_rh), 0, 36)
            oled.text("strona 1/4", 0, 56)
        elif page == 1:
            oled.text("Jakosc powietrza", 0, 0)
            oled.hline(0, 10, 128, 1)
            oled.text("AQI: {}".format(aqi), 0, 20)
            oled.text(str(aqi_txt)[:16], 0, 36)
            oled.text("rozgrzewka..." if not ens_ok else "strona 2/4", 0, 48 if not ens_ok else 56)
        elif page == 2:
            oled.text("eCO2", 0, 0)
            oled.hline(0, 10, 128, 1)
            oled.text("{} ppm".format(eco2), 0, 24)
            oled.text("strona 3/4", 0, 56)
        else:
            oled.text("TVOC", 0, 0)
            oled.hline(0, 10, 128, 1)
            oled.text("{} ppb".format(tvoc), 0, 24)
            oled.text("strona 4/4", 0, 56)
        oled.show()
    except OSError as e:
        print("OLED", e)


def wake():
    global awake, t_wake, t_page
    oled.poweron()
    awake = True
    t_wake = t_page = time.ticks_ms()
    draw_page()


def button_pressed():
    global btn_prev
    stan = btn.value()
    pressed = stan == 0 and btn_prev == 1
    btn_prev = stan
    if pressed:
        time.sleep_ms(30)
        if btn.value() != 0:
            return False
    return pressed


measure()
draw_page()
print("main_oled_only OK", of)

while True:
    now = time.ticks_ms()
    if button_pressed():
        if not awake:
            wake()
        else:
            page = (page + 1) % PAGE_COUNT
            t_page = t_wake = now
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
            try:
                oled.poweroff()
            except OSError:
                pass
            awake = False
    time.sleep_ms(20)
