"""SSD1306 128x64 I2C — lekki, bez alokacji w pętli show()."""
from micropython import const
import framebuf
import time

_SET_CONTRAST = const(0x81)
_SET_ENTIRE_ON = const(0xA4)
_SET_NORM_INV = const(0xA6)
_SET_DISP = const(0xAE)
_SET_MEM_ADDR = const(0x20)
_SET_COL_ADDR = const(0x21)
_SET_PAGE_ADDR = const(0x22)
_SET_DISP_START_LINE = const(0x40)
_SET_SEG_REMAP = const(0xA0)
_SET_MUX_RATIO = const(0xA8)
_SET_COM_OUT_DIR = const(0xC0)
_SET_DISP_OFFSET = const(0xD3)
_SET_COM_PIN_CFG = const(0xDA)
_SET_DISP_CLK_DIV = const(0xD5)
_SET_PRECHARGE = const(0xD9)
_SET_VCOM_DESEL = const(0xDB)
_SET_CHARGE_PUMP = const(0x8D)


class SSD1306_I2C(framebuf.FrameBuffer):
    def __init__(self, width, height, i2c, addr=0x3C, external_vcc=False):
        self.width = width
        self.height = height
        self.i2c = i2c
        self.addr = addr
        self.pages = height // 8
        self.buffer = bytearray(self.pages * width)
        self._cmd = bytearray(2)
        self._cmd[0] = 0x80
        # 1 + szerokość strony — stały bufor, zero bytes() w show
        self._tx = bytearray(1 + width)
        self._tx[0] = 0x40
        super().__init__(self.buffer, width, height, framebuf.MONO_VLSB)
        time.sleep_ms(10)
        self._init(external_vcc)

    def _w(self, buf):
        try:
            self.i2c.writeto(self.addr, buf)
        except OSError:
            time.sleep_ms(2)
            self.i2c.writeto(self.addr, buf)

    def _write_cmd(self, cmd):
        self._cmd[1] = cmd & 0xFF
        self._w(self._cmd)

    def _init(self, external_vcc):
        for c in (
            _SET_DISP | 0x00,
            _SET_MEM_ADDR,
            0x00,
            _SET_DISP_START_LINE | 0x00,
            _SET_SEG_REMAP | 0x01,
            _SET_MUX_RATIO,
            self.height - 1,
            _SET_COM_OUT_DIR | 0x08,
            _SET_DISP_OFFSET,
            0x00,
            _SET_COM_PIN_CFG,
            0x12 if self.height == 64 else 0x02,
            _SET_DISP_CLK_DIV,
            0x80,
            _SET_PRECHARGE,
            0x22 if external_vcc else 0xF1,
            _SET_VCOM_DESEL,
            0x30,
            _SET_CONTRAST,
            0xFF,
            _SET_ENTIRE_ON,
            _SET_NORM_INV,
            _SET_CHARGE_PUMP,
            0x10 if external_vcc else 0x14,
            _SET_DISP | 0x01,
        ):
            self._write_cmd(c)
        self.fill(0)
        self.show()

    def show(self):
        # page-by-page: stabilne na DuPont, bez 64× alokacji 16 B
        self._write_cmd(_SET_COL_ADDR)
        self._write_cmd(0)
        self._write_cmd(self.width - 1)
        self._write_cmd(_SET_PAGE_ADDR)
        self._write_cmd(0)
        self._write_cmd(self.pages - 1)
        w = self.width
        buf = self.buffer
        tx = self._tx
        for p in range(self.pages):
            start = p * w
            tx[1:] = buf[start : start + w]
            self._w(tx)

    def poweroff(self):
        try:
            self._write_cmd(_SET_DISP | 0x00)
        except OSError:
            pass

    def poweron(self):
        try:
            self._write_cmd(_SET_DISP | 0x01)
        except OSError:
            pass
