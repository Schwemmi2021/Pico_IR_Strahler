from machine import Pin, PWM
import time

TX_PIN = 18
CARRIER_FREQ = 38000
CARRIER_DUTY_U16 = 21845  # ~33% Tastgrad, ueblich fuer IR-Fernbedienungen


def send(durations, pin_num=TX_PIN, carrier_freq=CARRIER_FREQ):
    """Spielt eine Liste von Impulsdauern (us, abwechselnd Mark/Space,
    beginnend mit Mark) ueber eine IR-Sende-LED ab."""
    pwm = PWM(Pin(pin_num))
    pwm.freq(carrier_freq)
    pwm.duty_u16(0)
    try:
        for i, dur in enumerate(durations):
            if i % 2 == 0:
                pwm.duty_u16(CARRIER_DUTY_U16)
            else:
                pwm.duty_u16(0)
            time.sleep_us(dur)
    finally:
        pwm.duty_u16(0)
        pwm.deinit()


def send_by_name(name, pin_num=TX_PIN):
    from ir_codes import load_codes
    codes = load_codes()
    if name not in codes:
        print("Unbekannter Code:", name, "- vorhanden:", list(codes.keys()))
        return
    send(codes[name], pin_num=pin_num)
