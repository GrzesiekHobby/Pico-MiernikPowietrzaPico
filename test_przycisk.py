"""Test 2: przycisk na GP15 (do GND). Wciśnij kilka razy."""
from machine import Pin
import time
import pins

btn = Pin(pins.BUTTON_PIN, Pin.IN, Pin.PULL_UP)
print("Przycisk gotowy. Wcisnij (polaczenie GP15 z GND)...")

ostatni = 1
while True:
    stan = btn.value()  # 1 = puszczony, 0 = wcisniety
    if stan == 0 and ostatni == 1:
        print("WCISNIETY")
        time.sleep_ms(50)  # proste odblokowanie drgan
    elif stan == 1 and ostatni == 0:
        print("puszczony")
    ostatni = stan
    time.sleep_ms(10)
