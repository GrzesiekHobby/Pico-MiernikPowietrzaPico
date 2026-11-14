"""
SzklarniaPico 01 — WiFi portal (AP-first → zapis sieci domu → STA).

Uproszczony wariant pod miernik powietrza (bez wody/MQTT).
Hasła sieci domu trafiają tylko do secrets.py na płytce — nie na OLED.
"""

import time

# Domyślne — i tak widać je na OLED (strona „Sieć”)
AP_SSID_DEFAULT = "Miernik-Pico"
AP_PASS_DEFAULT = "miernik123"
AP_IP_FALLBACK = "192.168.4.1"

MODE = "brak"  # ap | sta | brak
AP_IP = None
AP_SSID = AP_SSID_DEFAULT
AP_PASS = AP_PASS_DEFAULT
LAST_SEEN = []  # list of (ssid, rssi)
LAST_ERR = ""
NEED_JOIN = False
_ap = None
_sta = None


def _sec(name, default=None):
    try:
        import secrets

        return getattr(secrets, name, default)
    except Exception:
        return default


def ap_settings():
    ssid = _sec("AP_SSID", AP_SSID_DEFAULT) or AP_SSID_DEFAULT
    password = _sec("AP_PASSWORD", AP_PASS_DEFAULT)
    if password is None:
        password = AP_PASS_DEFAULT
    return str(ssid)[:32], str(password)


def known_networks():
    nets = _sec("WIFI_NETWORKS", None)
    if nets:
        out = []
        for entry in nets:
            ssid = entry.get("ssid") or entry.get("SSID")
            if not ssid:
                continue
            password = entry.get("password") or entry.get("pass") or ""
            out.append({"ssid": str(ssid), "password": str(password)})
        return out
    ssid = _sec("WIFI_SSID", None)
    if not ssid:
        return []
    password = _sec("WIFI_PASSWORD", None) or _sec("WIFI_PASS", "") or ""
    return [{"ssid": str(ssid), "password": str(password)}]


def mode():
    return MODE


def last_error():
    return LAST_ERR or ""


def set_error(msg):
    global LAST_ERR
    LAST_ERR = str(msg or "")[:80]


def try_seconds():
    try:
        return max(5, min(30, int(_sec("WIFI_TRY_SECONDS", 12) or 12)))
    except Exception:
        return 12


def _ssid_of(row):
    raw = row[0]
    if isinstance(raw, bytes):
        try:
            raw = raw.decode()
        except Exception:
            return ""
    return raw or ""


def scan_networks(max_n=12):
    """Skan 2,4 GHz przez STA_IF (AP może zostać włączony)."""
    global LAST_SEEN, _sta, LAST_ERR
    import network

    if _sta is None:
        _sta = network.WLAN(network.STA_IF)
    try:
        _sta.active(True)
    except Exception as e:
        set_error("STA active: %s" % e)
        return []
    try:
        raw = _sta.scan()
    except Exception as e:
        set_error("Skan: %s" % e)
        print("scan", e)
        raw = []
    seen = {}
    order = []
    for row in raw or []:
        ssid = _ssid_of(row)
        if not ssid:
            continue
        rssi = row[3] if len(row) > 3 else -100
        if ssid not in seen or rssi > seen[ssid]:
            seen[ssid] = rssi
            if ssid not in order:
                order.append(ssid)
    # sort po sile sygnału
    order.sort(key=lambda s: seen.get(s, -100), reverse=True)
    LAST_SEEN = [(s, seen[s]) for s in order[:max_n]]
    return LAST_SEEN


def stop_ap():
    global _ap, MODE, AP_IP
    if _ap is None:
        return
    try:
        _ap.active(False)
    except Exception:
        pass
    if MODE == "ap":
        MODE = "brak"
    AP_IP = None


def start_ap():
    """Własna sieć Pico. Zwraca IP AP albo None."""
    global _ap, MODE, AP_IP, AP_SSID, AP_PASS
    import network

    AP_SSID, AP_PASS = ap_settings()
    if _ap is None:
        _ap = network.WLAN(network.AP_IF)
    try:
        if _ap.active() and MODE == "ap" and AP_IP:
            return AP_IP
    except Exception:
        pass
    try:
        _ap.active(False)
    except Exception:
        pass
    time.sleep_ms(150)
    try:
        if AP_PASS and len(AP_PASS) >= 8:
            _ap.config(essid=AP_SSID, password=AP_PASS)
        else:
            _ap.config(essid=AP_SSID)
            AP_PASS = ""
    except Exception as e:
        print("AP config", e)
        set_error("AP config: %s" % e)
        try:
            _ap.config(essid=AP_SSID)
            AP_PASS = ""
        except Exception as e2:
            set_error("AP fail: %s" % e2)
            print("AP fail", e2)
            return None
    try:
        _ap.active(True)
    except Exception as e:
        set_error("AP active: %s" % e)
        print("AP active", e)
        return None
    time.sleep_ms(250)
    try:
        AP_IP = _ap.ifconfig()[0]
    except Exception:
        AP_IP = AP_IP_FALLBACK
    MODE = "ap"
    set_error("")
    print("HOTSPOT", AP_SSID, AP_IP, "haslo" if AP_PASS else "otwarty")
    return AP_IP


def _pm_none(wlan):
    try:
        import network

        for pm in (getattr(network.WLAN, "PM_NONE", None), 0xA11140, 0):
            if pm is None:
                continue
            try:
                wlan.config(pm=pm)
                break
            except Exception:
                pass
    except Exception:
        pass


def connect_sta(ssid, password, seconds=None):
    """Połączenie z siecią domu. Zwraca IP lub None."""
    global _sta, MODE, NEED_JOIN
    import network

    if seconds is None:
        seconds = try_seconds()
    if _sta is None:
        _sta = network.WLAN(network.STA_IF)
    try:
        _sta.active(True)
    except Exception as e:
        set_error("STA: %s" % e)
        return None
    try:
        _sta.disconnect()
    except Exception:
        pass
    time.sleep_ms(200)
    print("WiFi try:", ssid)
    try:
        _sta.connect(ssid, password or "")
    except OSError as e:
        set_error("connect: %s" % e)
        return None
    t0 = time.ticks_ms()
    while not _sta.isconnected():
        if time.ticks_diff(time.ticks_ms(), t0) > seconds * 1000:
            set_error("Timeout WiFi: %s" % ssid)
            print(" timeout", ssid)
            return None
        time.sleep_ms(200)
    ip = _sta.ifconfig()[0]
    _pm_none(_sta)
    MODE = "sta"
    NEED_JOIN = False
    set_error("")
    print("STA OK", ssid, ip)
    return ip


def join_saved():
    """Próbuje zapisane sieci (po sile / kolejności secrets)."""
    nets = known_networks()
    if not nets:
        set_error("Brak zapisanych sieci w secrets.py")
        return None
    seen = {s: r for s, r in scan_networks()}
    ordered = []
    for n in nets:
        if n["ssid"] in seen:
            ordered.append((seen[n["ssid"]], n))
    ordered.sort(key=lambda x: x[0], reverse=True)
    # niewidoczne na końcu (może ukryte SSID)
    for n in nets:
        if n["ssid"] not in seen:
            ordered.append((-999, n))
    for _rssi, n in ordered:
        ip = connect_sta(n["ssid"], n["password"])
        if ip:
            stop_ap()
            return ip
    return None


def _udec(raw):
    if isinstance(raw, str):
        raw = raw.encode()
    raw = raw.replace(b"+", b" ")
    out = bytearray()
    i = 0
    n = len(raw)
    while i < n:
        if raw[i] == 37 and i + 2 < n:  # %
            try:
                out.append(int(raw[i + 1 : i + 3], 16))
                i += 3
                continue
            except Exception:
                pass
        out.append(raw[i])
        i += 1
    try:
        return out.decode()
    except Exception:
        return out.decode("utf-8", "replace")


def qmap(query):
    d = {}
    if not query:
        return d
    if isinstance(query, str):
        query = query.encode()
    for part in query.split(b"&"):
        if b"=" not in part:
            continue
        k, v = part.split(b"=", 1)
        try:
            d[k.decode()] = _udec(v)
        except Exception:
            pass
    return d


def splice_networks(text, block):
    key = "WIFI_NETWORKS"
    i = text.find(key)
    if i < 0:
        if text and not text.endswith("\n"):
            text += "\n"
        return text + "\n" + block
    j = text.find("[", i)
    if j < 0:
        return text[:i] + block + text[i + len(key) :]
    depth = 0
    k = j
    while k < len(text):
        ch = text[k]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                k += 1
                if k < len(text) and text[k] == "\n":
                    k += 1
                return text[:i] + block + text[k:]
        k += 1
    return text[:i] + block


def render_nets(nets):
    lines = ["WIFI_NETWORKS = ["]
    for n in nets:
        lines.append(
            '    {"ssid": %s, "password": %s},'
            % (repr(n["ssid"]), repr(n["password"]))
        )
    lines.append("]")
    return "\n".join(lines) + "\n"


def save_network(ssid, password):
    global NEED_JOIN
    ssid = (ssid or "").strip()
    password = password or ""
    if not ssid:
        return False, "Brak nazwy sieci."
    if len(ssid) > 32:
        return False, "Nazwa za dluga (max 32)."
    if len(password) > 63:
        return False, "Haslo za dlugie (max 63)."
    ap_ssid, _ = ap_settings()
    if ssid == ap_ssid:
        return False, "To nazwa hotspotu Pico — wybierz siec domu."
    nets = known_networks()
    replaced = False
    for n in nets:
        if n["ssid"] == ssid:
            n["password"] = password
            replaced = True
            break
    if not replaced:
        if len(nets) >= 8:
            return False, "Limit 8 sieci — usun jedna w secrets.py."
        nets.append({"ssid": ssid, "password": password})
    block = render_nets(nets)
    try:
        with open("secrets.py") as f:
            text = f.read()
    except OSError:
        text = (
            "# dopisane z portalu WWW miernika\n"
            "WIFI_TRY_SECONDS = 12\n"
            "WEB_PORT = 80\n"
            'AP_SSID = "%s"\n' % AP_SSID_DEFAULT
            + 'AP_PASSWORD = "%s"\n' % AP_PASS_DEFAULT
        )
    new_text = splice_networks(text, block)
    try:
        with open("secrets.py", "w") as f:
            f.write(new_text)
    except OSError as e:
        return False, "Zapis secrets.py: %s" % e
    try:
        import sys

        sys.modules.pop("secrets", None)
        secrets = __import__("secrets")
        secrets.WIFI_NETWORKS = nets
    except Exception as e:
        print("reload secrets", e)
    NEED_JOIN = True
    if replaced:
        return True, "Zaktualizowano %s." % ssid
    return True, "Dopisano %s do secrets.py." % ssid


def oled_net_lines(ip=None):
    """Dokładnie 4 linie × max 16 znaków (OLED 128×64).

    Tryb AP — wymaganie produktowe (bez Thonny):
      1 HOTSPOT
      2 SSID hotspota
      3 hasło hotspota (całe, bez prefiksu „haslo ” który ucinał wartość)
      4 IP (zwykle 192.168.4.1)
    Hasła sieci domu NIGDY tu nie ma.
    """
    if MODE == "sta":
        return [
            "LAN OK",
            (ip or "-")[:16],
            "http://IP/",
            "AP wylaczony",
        ]
    if MODE == "ap":
        pw = AP_PASS if AP_PASS else "(otwarty)"
        return [
            "HOTSPOT",
            AP_SSID[:16],
            str(pw)[:16],
            (AP_IP or AP_IP_FALLBACK)[:16],
        ]
    return ["Siec", "brak AP/STA", (last_error() or "...")[:16], ""]
