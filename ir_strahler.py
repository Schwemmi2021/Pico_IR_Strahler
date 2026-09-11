from machine import Pin, Timer


class IRStrahler:
    """Schaltet einen GPIO (z.B. Relais/MOSFET fuer den IR-Strahler)
    in einem frei konfigurierbaren An/Aus-Rhythmus, per Hardware-Timer
    (keine Blockierung, kein Busy-Loop)."""

    def __init__(self, pin_num, active_high=True, timer_id=-1):
        self.pin = Pin(pin_num, Pin.OUT)
        self.active_high = active_high
        self.timer = Timer(timer_id)
        self.on_ms = 100
        self.off_ms = 50
        self.running = False
        self.state = False
        self._set(False)

    def _set(self, on):
        self.pin.value(on if self.active_high else not on)

    def _tick(self, t):
        self.state = not self.state
        self._set(self.state)
        period = self.on_ms if self.state else self.off_ms
        self.timer.init(mode=Timer.ONE_SHOT, period=period, callback=self._tick)

    def start(self, on_ms=None, off_ms=None):
        if on_ms is not None:
            self.on_ms = on_ms
        if off_ms is not None:
            self.off_ms = off_ms
        self.state = True
        self._set(True)
        self.timer.init(mode=Timer.ONE_SHOT, period=self.on_ms, callback=self._tick)
        self.running = True

    def stop(self):
        self.timer.deinit()
        self._set(False)
        self.running = False
