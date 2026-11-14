"""Test 4: odczyt AHT21 + ENS160 co 2 s."""
from machine import I2C, Pin
import time
from aht21 import AHT21
from ens160 import ENS160
import pins

sf = getattr(pins, "SENS_I2C_FREQ", 100_000)
i2c = I2C(pins.SENS_I2C_ID, sda=Pin(pins.SENS_SDA), scl=Pin(pins.SENS_SCL), freq=sf)
print("Skan:", [hex(a) for a in i2c.scan()])

aht = AHT21(i2c, pins.AHT21_ADDR)
ens = ENS160(i2c, pins.ENS160_ADDR)
print("Czujniki gotowe. ENS160 moze potrzebowac ~3 min rozgrzewki.")

while True:
    t, h = aht.read()
    ens.set_compensation(t, h)
    ok = ens.update()
    print("T={:.1f}C  RH={:.1f}%  AQI={} ({})  eCO2={}  TVOC={}  ok={}".format(
        t, h, ens.aqi, ens.aqi_text(), ens.eco2, ens.tvoc, ok
    ))
    time.sleep(2)
