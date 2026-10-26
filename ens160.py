"""Prosty sterownik ENS160 (jakość powietrza) dla MicroPython."""
import time
import struct


class ENS160:
    AQI_PL = {
        1: "Swietna",
        2: "Dobra",
        3: "Srednia",
        4: "Slaba",
        5: "Zla",
    }

    def __init__(self, i2c, address=0x53):
        self.i2c = i2c
        self.addr = address
        self.aqi = 1
        self.tvoc = 0
        self.eco2 = 400
        self.ok = False
        # Reset → Idle → Standard
        self._w(0x10, 0xF0)
        time.sleep_ms(20)
        self._w(0x10, 0x01)
        time.sleep_ms(10)
        self.set_compensation(25.0, 50.0)
        self._w(0x10, 0x02)
        time.sleep_ms(10)

    def set_compensation(self, temp_c, hum_rh):
        t = int((temp_c + 273.15) * 64)
        h = int(hum_rh * 512)
        self.i2c.writeto_mem(self.addr, 0x13, struct.pack("<H", t))
        self.i2c.writeto_mem(self.addr, 0x15, struct.pack("<H", h))

    def update(self):
        """Odczyt. True = dane poprawne (po rozgrzewce)."""
        status = self._r(0x20)
        if not (status & 0x02):
            return False
        data = self.i2c.readfrom_mem(self.addr, 0x20, 6)
        validity = (data[0] >> 2) & 0x03
        self.aqi = data[1] & 0x07
        self.tvoc = struct.unpack("<H", data[2:4])[0]
        self.eco2 = struct.unpack("<H", data[4:6])[0]
        self.ok = validity == 0
        return self.ok

    def aqi_text(self):
        return self.AQI_PL.get(self.aqi, "?")

    def _w(self, reg, val):
        self.i2c.writeto_mem(self.addr, reg, bytes([val]))

    def _r(self, reg):
        return self.i2c.readfrom_mem(self.addr, reg, 1)[0]
