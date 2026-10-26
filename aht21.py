"""Prosty sterownik AHT21 (temperatura + wilgotność) dla MicroPython."""
import time


class AHT21:
    def __init__(self, i2c, address=0x38):
        self.i2c = i2c
        self.addr = address
        time.sleep_ms(40)
        self.i2c.writeto(self.addr, b"\xBE\x08\x00")  # init / kalibracja
        time.sleep_ms(10)

    def read(self):
        """Zwraca (temperatura_C, wilgotnosc_%)."""
        self.i2c.writeto(self.addr, b"\xAC\x33\x00")
        time.sleep_ms(80)
        raw = self.i2c.readfrom(self.addr, 6)
        hum_raw = ((raw[1] << 12) | (raw[2] << 4) | (raw[3] >> 4)) & 0xFFFFF
        temp_raw = ((raw[3] & 0x0F) << 16) | (raw[4] << 8) | raw[5]
        humidity = hum_raw * 100.0 / 1048576.0
        temperature = temp_raw * 200.0 / 1048576.0 - 50.0
        return temperature, humidity
