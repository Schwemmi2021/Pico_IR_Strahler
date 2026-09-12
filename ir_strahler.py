from machine import Pin, Timer


class IRStrahler:
    """Schaltet einen GPIO in einem frei konfigurierbaren An/Aus-Rhythmus,
    per Hardware-Timer (keine Blockierung, kein Busy-Loop).

    open_drain=True (Standard): simuliert einen potentialfreien Kontakt.
    "An" = Pin als Ausgang auf LOW (zieht die Leitung/kurzschliesst sie),
    "Aus" = Pin als Eingang (hochohmig/losgelassen). So wird nie aktiv
    Spannung auf die externe Leitung gelegt - sicher fuer Eingaenge wie
    den "Volt Free"-Trigger-Eingang des Raytec-Strahlers.

    open_drain=False: normaler Push-Pull-Ausgang (z.B. fuer ein Relais-
    oder MOSFET-Modul mit eigenem Steuersignal-Eingang)."""

    def __init__(self, pin_num, active_high=True, timer_id=-1, open_drain=True):
        self.pin_num = pin_num
        self.open_drain = open_drain
        self.active_high = active_high
        self.pin = Pin(pin_num, Pin.IN) if open_drain else Pin(pin_num, Pin.OUT)
        self.timer = Timer(timer_id)
        self.on_ms = 100
        self.off_ms = 50
        self.running = False
        self.state = False
        self._set(False)

    def _set(self, on):
        if self.open_drain:
            if on:
                self.pin.init(Pin.OUT)
                self.pin.value(0)
            else:
                self.pin.init(Pin.IN)
        else:
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

    def on(self):
        """Dauerhaft an, ohne Puls-Timer (fuer durchgehendes Leuchten)."""
        self.timer.deinit()
        self._set(True)
        self.state = True
        self.running = "on"

    def off(self):
        """Dauerhaft aus (Kontakt offen)."""
        self.timer.deinit()
        self._set(False)
        self.state = False
        self.running = False
