from machine import Pin
import time

PIN = 16              # GPIO am Signal-Abgriff der Fotodiode
IDLE_TIMEOUT_MS = 200  # Pause ohne Flankenwechsel, ab der ein Telegramm als beendet gilt
MAX_EDGES = 400

pin = Pin(PIN, Pin.IN)

edges = []


def _irq(p):
    if len(edges) < MAX_EDGES:
        edges.append(time.ticks_us())


pin.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=_irq)

print("Warte auf IR-Signal (Fernbedienung aus wenigen cm auf die Fotodiode richten)...")

last_len = 0
last_change = time.ticks_ms()
while True:
    n = len(edges)
    if n != last_len:
        last_len = n
        last_change = time.ticks_ms()
    elif n > 0 and time.ticks_diff(time.ticks_ms(), last_change) > IDLE_TIMEOUT_MS:
        break
    if n >= MAX_EDGES:
        break
    time.sleep_ms(5)

pin.irq(handler=None)

print("Erfasste Flanken:", len(edges))
if len(edges) >= 2:
    durations = [time.ticks_diff(edges[i + 1], edges[i]) for i in range(len(edges) - 1)]
    print("Impulsdauern (us):")
    print(durations)
else:
    print("Kein Signal erkannt - Verkabelung/Abstand/Ausrichtung pruefen")
