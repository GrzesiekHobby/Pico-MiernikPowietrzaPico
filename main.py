"""
Pico-Prosty_miernik_powietrza — ewolucja AP + WWW

BAZA = publiczne repo GrzesiekHobby/Pico-Prosty_miernik_powietrza (MIT)
Piny (pins.py) — NIE zmieniać względem publicznego kanonu:

  OLED          I2C0  SDA=GP0  SCL=GP1
  AHT21+ENS160  I2C1  SDA=GP2  SCL=GP3
  Przycisk      GP15 → GND

Bez WiFi działa jak main_oled_only.py (kopia publicznego main).
Z WiFi: hotspot → OLED pokazuje SSID/hasło/IP → WWW → join sieci domu.

Wymaga na Pico: pins.py, aht21.py, ens160.py, ssd1306.py, wifi_portal.py
Opcjonalnie: secrets.py (z secrets.py.example)
"""

from machine import I2C, Pin
import time
import socket
from ssd1306 import SSD1306_I2C
from aht21 import AHT21
from ens160 import ENS160
import pins
import wifi_portal as wifi

MEASURE_MS = 9000
PAGE_MS = 4000
SLEEP_MS = 60000  # poza trybem AP
PAGE_COUNT = 5
PAGE_NET = 4  # ekran hotspot / LAN

# --- sprzęt (kanon publiczny) ---
i2c_oled = None
i2c_sens = None
oled = None
aht = None
ens = None
btn = None

temp_c = 0.0
hum_rh = 0.0
aqi = 1
aqi_txt = "-"
eco2 = 400
tvoc = 0
ens_ok = False
sensor_err = ""

page = 0
awake = True
btn_prev = 1
net_mode = "brak"
ip = None
srv = None
flash = ""
port = 80


def web_port():
    try:
        import secrets

        return int(getattr(secrets, "WEB_PORT", 80) or 80)
    except Exception:
        return 80


def boot_hw():
    """Init I2C + urządzenia. Błędy nie zabijają startu sieci/OLED jeśli da się ocalić."""
    global i2c_oled, i2c_sens, oled, aht, ens, btn, sensor_err
    btn = Pin(pins.BUTTON_PIN, Pin.IN, Pin.PULL_UP)

    oled_freq = getattr(pins, "OLED_I2C_FREQ", 100_000)
    sens_freq = getattr(pins, "SENS_I2C_FREQ", 100_000)

    try:
        i2c_oled = I2C(
            pins.OLED_I2C_ID,
            sda=Pin(pins.OLED_SDA),
            scl=Pin(pins.OLED_SCL),
            freq=oled_freq,
        )
    except Exception as e:
        print("I2C OLED", e)
        sensor_err = "I2C OLED FAIL"
        return

    try:
        i2c_sens = I2C(
            pins.SENS_I2C_ID,
            sda=Pin(pins.SENS_SDA),
            scl=Pin(pins.SENS_SCL),
            freq=sens_freq,
        )
    except Exception as e:
        print("I2C SENS", e)
        sensor_err = "I2C SENS FAIL"

    time.sleep_ms(30)

    found_o = []
    found_s = []
    try:
        found_o = [hex(a) for a in i2c_oled.scan()]
    except Exception as e:
        print("scan oled", e)
    try:
        if i2c_sens:
            found_s = [hex(a) for a in i2c_sens.scan()]
    except Exception as e:
        print("scan sens", e)
    print("OLED bus GP0/1:", found_o, "oczekiwane 0x3c @", oled_freq)
    print("SENS bus GP2/3:", found_s, "oczekiwane 0x38 0x53 @", sens_freq)

    # Max 2 próby init OLED — BEZ recreacji I2C (re-map pinów = „zapchany” bus)
    oled = None
    for attempt in range(2):
        try:
            oled = SSD1306_I2C(128, 64, i2c_oled, addr=pins.OLED_ADDR)
            break
        except Exception as e:
            print("OLED init", attempt + 1, e)
            oled = None
            time.sleep_ms(30)
    if oled is None:
        sensor_err = (sensor_err + " OLED FAIL").strip()
    elif oled:
        # krótki banner (było 2 s — zbędne blokowanie pętli)
        oled.fill(0)
        oled.text("BOOT", 0, 0)
        oled.text(("O:" + (",".join(found_o) or "-"))[:16], 0, 16)
        oled.text(("S:" + (",".join(found_s) or "-"))[:16], 0, 32)
        oled.show()

    try:
        if i2c_sens:
            aht = AHT21(i2c_sens, pins.AHT21_ADDR)
    except Exception as e:
        print("AHT", e)
        aht = None
        sensor_err = (sensor_err + " AHT FAIL").strip()
    try:
        if i2c_sens:
            ens = ENS160(i2c_sens, pins.ENS160_ADDR)
    except Exception as e:
        print("ENS", e)
        ens = None
        sensor_err = (sensor_err + " ENS FAIL").strip()


def measure():
    global temp_c, hum_rh, aqi, aqi_txt, eco2, tvoc, ens_ok, sensor_err
    if aht is None and ens is None:
        return
    try:
        if aht is not None:
            temp_c, hum_rh = aht.read()
        if ens is not None:
            ens.set_compensation(temp_c, hum_rh)
            ens_ok = ens.update()
            aqi = ens.aqi
            aqi_txt = ens.aqi_text()
            eco2 = ens.eco2
            tvoc = ens.tvoc
        # nie kasuj trwałego błędu init, tylko błędy odczytu
        if "FAIL" not in (sensor_err or ""):
            sensor_err = ""
    except OSError as e:
        print("Blad I2C pomiaru:", e)
        sensor_err = str(e)[:40]


def draw_header(title):
    oled.text(title, 0, 0)
    oled.hline(0, 10, 128, 1)


def draw_page():
    if oled is None:
        return
    try:
        oled.fill(0)
        if page == 0:
            draw_header("Klimat")
            oled.text("Temp: {:.1f} C".format(temp_c), 0, 20)
            oled.text("Wilg: {:.1f} %".format(hum_rh), 0, 36)
            foot = (ip or net_mode or "")[:16]
            oled.text(foot if foot else "strona 1/5", 0, 56)
        elif page == 1:
            draw_header("Jakosc powietrza")
            oled.text("AQI: {}".format(aqi), 0, 20)
            oled.text(str(aqi_txt)[:16], 0, 36)
            if not ens_ok:
                oled.text("rozgrzewka...", 0, 48)
            else:
                oled.text("strona 2/5", 0, 56)
        elif page == 2:
            draw_header("eCO2")
            oled.text("{} ppm".format(eco2), 0, 24)
            oled.text("strona 3/5", 0, 56)
        elif page == 3:
            draw_header("TVOC")
            oled.text("{} ppb".format(tvoc), 0, 24)
            oled.text("strona 4/5", 0, 56)
        else:
            # Sieć — 4 linie z wifi_portal (SSID + hasło AP + IP)
            lines = wifi.oled_net_lines(ip)
            y = 0
            for line in lines:
                oled.text(str(line)[:16], 0, y)
                y += 14
        if sensor_err and page != PAGE_NET:
            oled.text(str(sensor_err)[:16], 0, 56)
        oled.show()
    except Exception as e:
        print("draw", e)


def wake():
    global awake, t_wake, t_page
    if oled is None:
        return
    try:
        oled.poweron()
    except Exception:
        pass
    awake = True
    t_wake = time.ticks_ms()
    t_page = t_wake
    draw_page()


def sleep_display():
    global awake
    if oled is None:
        return
    # W AP nie gasimy — hasło musi zostać na OLED
    if net_mode == "ap":
        return
    try:
        oled.poweroff()
    except Exception:
        pass
    awake = False


def button_pressed():
    global btn_prev
    if btn is None:
        return False
    stan = btn.value()
    pressed = stan == 0 and btn_prev == 1
    btn_prev = stan
    if pressed:
        time.sleep_ms(30)
        if btn.value() != 0:
            return False
    return pressed


def _esc(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def sensor_dict():
    err = sensor_err or wifi.last_error() or ""
    return {
        "t": round(temp_c, 2) if temp_c is not None else None,
        "rh": round(hum_rh, 2) if hum_rh is not None else None,
        "aqi": aqi,
        "ens": aqi_txt,
        "eco2": eco2,
        "tvoc": tvoc,
        "ok": ens_ok,
        "err": err,
        "ip": ip or "",
        "mode": net_mode or "",
    }


def make_html(flash_msg=""):
    d = sensor_dict()
    ap_ssid, ap_pw = wifi.ap_settings()
    opts = []
    for ssid, rssi in wifi.LAST_SEEN:
        opts.append(
            '<option value="%s">%s (%d dBm)</option>'
            % (_esc(ssid), _esc(ssid), rssi)
        )
    if not opts:
        opts.append('<option value="">(skan pusty — wpisz recznie)</option>')
    saved = "".join(
        "<li>%s</li>" % _esc(n["ssid"]) for n in wifi.known_networks()
    ) or "<li>brak</li>"
    err = d.get("err") or ""

    p = []
    p.append("<!DOCTYPE html><html lang=pl><head><meta charset=utf-8>")
    p.append("<meta name=viewport content='width=device-width,initial-scale=1'>")
    # BEZ meta-refresh — formularz nie może się resetować
    p.append("<title>Miernik Pico</title><style>")
    p.append(
        "body{font-family:system-ui,sans-serif;background:#0b1f14;color:#e8f5e9;"
        "margin:0;padding:14px}"
    )
    p.append(
        ".card{max-width:460px;margin:10px auto;background:#143d28;border-radius:12px;"
        "padding:16px}"
    )
    p.append("h1{font-size:1.2rem;color:#a5d6a7}h2{font-size:1.05rem;color:#c8e6c9}")
    p.append(
        ".row{display:flex;justify-content:space-between;padding:8px 0;"
        "border-bottom:1px solid #1b5e20}"
    )
    p.append(".v{font-size:1.2rem;font-weight:700;color:#c8e6c9}.s{opacity:.85}")
    p.append(".err{color:#ffab91;background:#3e2723;padding:8px;border-radius:8px}")
    p.append(".ok{color:#c5e1a5;background:#1b5e20;padding:8px;border-radius:8px}")
    p.append("label{display:block;margin:8px 0 4px}")
    p.append("input,select,button{font-size:1rem;padding:8px;width:100%;box-sizing:border-box}")
    p.append(
        "button{margin-top:10px;background:#2e7d32;color:#fff;border:0;border-radius:8px}"
    )
    p.append("a{color:#81c784}</style></head><body>")

    p.append("<div class=card><h1>Prosty miernik — WWW</h1>")
    p.append(
        "<p class=s>tryb <b id=m_mode>%s</b> · IP <b id=m_ip>%s</b> · ENS <span id=m_ens>%s</span></p>"
        % (_esc(net_mode), _esc(ip or "-"), _esc(aqi_txt))
    )
    if flash_msg:
        p.append("<p class=ok>%s</p>" % _esc(flash_msg))
    if err:
        p.append("<p class=err id=m_err>%s</p>" % _esc(err))
    else:
        p.append("<p class=err id=m_err style='display:none'></p>")
    p.append(
        "<div class=row><span>Temp</span><span class=v id=m_t>%.1f °C</span></div>"
        % temp_c
    )
    p.append(
        "<div class=row><span>Wilg</span><span class=v id=m_rh>%.1f %%</span></div>"
        % hum_rh
    )
    p.append(
        "<div class=row><span>AQI</span><span class=v id=m_aqi>%s</span></div>"
        % _esc(str(aqi))
    )
    p.append(
        "<div class=row><span>eCO2</span><span class=v id=m_eco2>%s ppm</span></div>"
        % _esc(str(eco2))
    )
    p.append(
        "<div class=row><span>TVOC</span><span class=v id=m_tvoc>%s ppb</span></div>"
        % _esc(str(tvoc))
    )
    p.append(
        "<p class=s>Odczyty ~5 s w tle (bez przeładowania). Formularz Wi‑Fi się nie resetuje. "
        "Pomiary działają też bez sieci.</p></div>"
    )

    p.append("<div class=card><h2>Hotspot Pico</h2>")
    p.append(
        "<p class=s>SSID <b>%s</b><br>hasło <b>%s</b><br>http://%s/<br>tylko 2,4 GHz</p>"
        % (
            _esc(ap_ssid),
            _esc(ap_pw if ap_pw else "(otwarty)"),
            _esc(
                (wifi.AP_IP or wifi.AP_IP_FALLBACK)
                if net_mode == "ap"
                else (ip or "-")
            ),
        )
    )
    p.append("<h2>Zapisane sieci</h2><ul>%s</ul>" % saved)
    p.append(
        "<p><a href='/scan'>Odśwież skan</a> · <a href='/join'>Połącz z zapisanymi</a></p>"
    )
    p.append("<h2>Połącz z Wi‑Fi domu</h2>")
    p.append("<form method=GET action='/save'>")
    p.append("<label>Sieć ze skanu</label><select name=ssid_sel>%s</select>" % "".join(opts))
    p.append(
        "<label>SSID ręcznie</label>"
        "<input name=ssid maxlength=32 autocomplete=off>"
    )
    p.append(
        "<label>Hasło</label>"
        "<input name=password type=password maxlength=63 autocomplete=off>"
    )
    p.append("<button type=submit>Zapisz i połącz</button></form>")
    p.append(
        "<p class=s>Po join: hotspot OFF, nowe IP na OLED (bez hasła AP).</p></div>"
    )
    p.append(
        "<script>"
        "function nv(x){return(x===null||x===undefined)?'--':x;}"
        "function tick(){fetch('/api.json').then(function(r){return r.json();}).then(function(j){"
        "var e=document.getElementById('m_t');if(e)e.textContent=nv(j.t)+' °C';"
        "e=document.getElementById('m_rh');if(e)e.textContent=nv(j.rh)+' %';"
        "e=document.getElementById('m_aqi');if(e)e.textContent=nv(j.aqi);"
        "e=document.getElementById('m_eco2');if(e)e.textContent=nv(j.eco2)+' ppm';"
        "e=document.getElementById('m_tvoc');if(e)e.textContent=nv(j.tvoc)+' ppb';"
        "e=document.getElementById('m_ens');if(e)e.textContent=nv(j.ens);"
        "e=document.getElementById('m_ip');if(e)e.textContent=nv(j.ip);"
        "e=document.getElementById('m_mode');if(e)e.textContent=nv(j.mode);"
        "e=document.getElementById('m_err');"
        "if(e){if(j.err){e.style.display='block';e.textContent=j.err;}"
        "else{e.style.display='none';e.textContent='';}}"
        "}).catch(function(){});}"
        "setInterval(tick,5000);"
        "</script></body></html>"
    )
    return "".join(p)


def _json_body(d):
    def jv(v):
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        s = str(v).replace("\\", "\\\\").replace('"', '\\"')
        return '"%s"' % s

    keys = ("t", "rh", "aqi", "ens", "eco2", "tvoc", "ok", "err", "ip", "mode")
    return "{" + ",".join('"%s":%s' % (k, jv(d.get(k))) for k in keys) + "}"


def open_server(p):
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", p))
    s.listen(2)
    s.settimeout(0.05)
    return s


def _parse_qs(path):
    if "?" not in path:
        return path, {}
    base, q = path.split("?", 1)
    out = {}
    for part in q.split("&"):
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
        else:
            k, v = part, ""
        out[k] = wifi._udec(v)
    return base, out


def _http_send(cl, code, body, content_type="text/html; charset=utf-8"):
    if isinstance(body, str):
        body = body.encode()
    try:
        cl.send(
            (
                "HTTP/1.0 %s\r\nContent-Type: %s\r\nConnection: close\r\n"
                "Content-Length: %d\r\n\r\n"
                % (code, content_type, len(body))
            ).encode()
            + body
        )
    except Exception:
        pass
    try:
        cl.close()
    except Exception:
        pass


def rebind_http():
    global srv
    if srv is not None:
        try:
            srv.close()
        except Exception:
            pass
        srv = None
    if ip:
        try:
            srv = open_server(port)
            print("WWW http://%s:%d/" % (ip, port))
        except Exception as e:
            print("rebind", e)
            wifi.set_error("WWW: %s" % e)


def handle_http(cl):
    global ip, net_mode, flash, page, srv
    try:
        raw = cl.recv(1024)
    except Exception:
        try:
            cl.close()
        except Exception:
            pass
        return
    if not raw:
        try:
            cl.close()
        except Exception:
            pass
        return
    try:
        line = raw.decode().split("\r\n", 1)[0]
    except Exception:
        line = ""
    parts = line.split()
    path = parts[1] if len(parts) >= 2 else "/"
    base, qs = _parse_qs(path)

    if base == "/api.json":
        _http_send(cl, "200 OK", _json_body(sensor_dict()), "application/json")
        return

    if base == "/scan":
        try:
            wifi.scan_networks()
            flash = "Skan OK (%d sieci)" % len(wifi.LAST_SEEN)
        except Exception as e:
            flash = "Skan: %s" % e
            wifi.set_error(str(e))
        _http_send(cl, "200 OK", make_html(flash))
        return

    if base == "/join":
        flash = "Laczenie..."
        _http_send(cl, "200 OK", make_html(flash))
        time.sleep_ms(50)
        new_ip = wifi.join_saved()
        if new_ip:
            ip = new_ip
            net_mode = "sta"
            flash = "Polaczono. Nowe IP: %s" % ip
            page = 0
            rebind_http()
            wake()
        else:
            flash = wifi.last_error() or "Join FAIL"
            if wifi.mode() == "ap":
                net_mode = "ap"
                ip = wifi.AP_IP or wifi.AP_IP_FALLBACK
        return

    if base == "/save":
        ssid = (qs.get("ssid") or qs.get("ssid_sel") or "").strip()
        password = qs.get("password") or ""
        if not ssid:
            flash = "Podaj SSID"
            _http_send(cl, "200 OK", make_html(flash))
            return
        ok, msg = wifi.save_network(ssid, password)
        flash = msg
        _http_send(cl, "200 OK", make_html(flash))
        time.sleep_ms(80)
        if ok:
            # Najpierw ta sieć, potem ewentualnie join_saved
            new_ip = wifi.connect_sta(ssid, password)
            if new_ip:
                wifi.stop_ap()
            else:
                new_ip = wifi.join_saved()
            if new_ip:
                ip = new_ip
                net_mode = "sta"
                flash = "Polaczono z %s · IP %s" % (ssid, ip)
                page = 0
                rebind_http()
                wake()
            else:
                flash = wifi.last_error() or "Join FAIL — hotspot wraca"
                if wifi.mode() == "ap":
                    net_mode = "ap"
                    ip = wifi.AP_IP or wifi.AP_IP_FALLBACK
        return

    if base in ("/", "/index.html", "/wifi"):
        _http_send(cl, "200 OK", make_html(flash))
        return

    _http_send(cl, "404 Not Found", "404")


def poll_http():
    global srv
    if srv is None:
        return
    try:
        cl, _addr = srv.accept()
    except OSError:
        return
    except Exception as e:
        print("accept", e)
        return
    try:
        cl.settimeout(2)
    except Exception:
        pass
    try:
        handle_http(cl)
    except Exception as e:
        print("http", e)
        try:
            cl.close()
        except Exception:
            pass


def main():
    global page, ip, net_mode, srv, port, awake
    global t_wake, t_page, t_meas

    print("=== Pico-Prosty miernik + AP/WWW ===")
    print("banner: public pins GP0-3 dual I2C + AP-first")
    print("OLED GP0/GP1 | SENS GP2/GP3 | BTN GP15")

    boot_hw()
    measure()

    port = web_port()
    ip = None
    net_mode = "brak"
    try:
        ip = wifi.start_ap()
        if ip:
            net_mode = "ap"
            try:
                wifi.scan_networks()
            except Exception as e:
                print("scan0", e)
        else:
            print("AP FAIL — tryb offline OLED")
    except Exception as e:
        print("AP", e)
        wifi.set_error(str(e))

    if ip:
        try:
            srv = open_server(port)
            print("WWW http://%s:%d/" % (ip, port))
        except Exception as e:
            print("server", e)
            wifi.set_error("WWW: %s" % e)

    # Start na ekranie Sieć gdy AP — SSID + hasło bez klikania
    page = PAGE_NET if net_mode == "ap" else 0
    now = time.ticks_ms()
    t_wake = now
    t_page = now
    t_meas = time.ticks_add(now, -MEASURE_MS)
    awake = True
    draw_page()
    print("main OK mode=%s page=%s" % (net_mode, page))

    while True:
        now = time.ticks_ms()

        if button_pressed():
            if not awake:
                wake()
            else:
                page = (page + 1) % PAGE_COUNT
                t_page = now
                t_wake = now
                draw_page()

        if time.ticks_diff(now, t_meas) >= MEASURE_MS:
            measure()
            t_meas = now
            if awake:
                draw_page()

        # Auto-obrót stron tylko poza AP i poza ekranem Sieć
        if awake and net_mode != "ap" and page != PAGE_NET:
            if time.ticks_diff(now, t_page) >= PAGE_MS:
                page = (page + 1) % PAGE_COUNT
                if page == PAGE_NET and net_mode != "ap":
                    # pokaż LAN info krótko, OK
                    pass
                t_page = now
                draw_page()
            if time.ticks_diff(now, t_wake) >= SLEEP_MS:
                sleep_display()

        try:
            prev = net_mode
            poll_http()
            if prev == "ap" and net_mode == "sta":
                page = 0
                wake()
        except Exception as e:
            print("poll", e)

        time.sleep_ms(20)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FATAL", e)
        try:
            if oled:
                oled.fill(0)
                oled.text("FATAL", 0, 0)
                msg = str(e)
                y = 16
                while msg and y < 64:
                    oled.text(msg[:16], 0, y)
                    msg = msg[16:]
                    y += 12
                oled.show()
        except Exception:
            pass
        raise
