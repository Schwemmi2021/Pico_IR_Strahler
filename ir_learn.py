from machine import Pin
import time

RX_PIN = 14
RX_PWR_PIN = 15
STATUS_LED_PIN = 13
IDLE_TIMEOUT_MS = 200
MAX_EDGES = 4000
BLINK_MS = 250


def capture(pin_num=RX_PIN, pwr_pin=RX_PWR_PIN, led_pin=STATUS_LED_PIN,
            idle_timeout_ms=IDLE_TIMEOUT_MS, max_edges=MAX_EDGES, timeout_s=10):
    """Zeichnet die rohen Flankenabstaende (us) eines IR-Telegramms auf.
    Blinkt die Status-LED waehrend des Wartens, leuchtet dauerhaft bei Erfolg.
    Gibt eine Liste von Impulsdauern zurueck (abwechselnd Mark/Space,
    beginnend mit Mark), oder None wenn nichts empfangen wurde."""
    Pin(pwr_pin, Pin.OUT).value(1)
    led = Pin(led_pin, Pin.OUT)
    pin = Pin(pin_num, Pin.IN)
    edges = []

    def _irq(p):
        if len(edges) < max_edges:
            edges.append(time.ticks_us())

    pin.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=_irq)

    start = time.ticks_ms()
    last_len = 0
    last_change = start
    last_blink = start
    blink_state = False
    while True:
        n = len(edges)
        if n != last_len:
            last_len = n
            last_change = time.ticks_ms()
        elif n > 0 and time.ticks_diff(time.ticks_ms(), last_change) > idle_timeout_ms:
            break
        if n >= max_edges:
            break
        if time.ticks_diff(time.ticks_ms(), start) > timeout_s * 1000:
            break
        if time.ticks_diff(time.ticks_ms(), last_blink) > BLINK_MS:
            blink_state = not blink_state
            led.value(blink_state)
            last_blink = time.ticks_ms()
        time.sleep_ms(5)

    pin.irq(handler=None)

    if len(edges) < 2:
        led.value(0)
        return None

    led.value(1)
    return [time.ticks_diff(edges[i + 1], edges[i]) for i in range(len(edges) - 1)]


def learn(name, pin_num=RX_PIN):
    from ir_codes import save_code
    print("Taste '%s': Fernbedienung aus wenigen cm auf die Diode richten und Taste druecken..." % name)
    durations = capture(pin_num=pin_num)
    if durations is None:
        print("Kein Signal erkannt, bitte erneut versuchen.")
        return None
    print("Erfasst: %d Impulse" % len(durations))
    save_code(name, durations)
    print("Gespeichert als '%s'" % name)
    return durations
