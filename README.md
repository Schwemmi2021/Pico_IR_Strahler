# Pico_IR_Strahler

MicroPython-Projekt fuer Raspberry Pi Pico 2 W: lernt die IR-Codes einer
Raytec-VARIO2-Fernbedienung ein und kann sie ueber eine IR-Sende-LED
wieder abspielen. Zusaetzlich eine frei konfigurierbare Blitz-Steuerung
fuer den IR-Strahler per Relais/MOSFET.

## Hardware

- Raspberry Pi Pico 2 W
- IR-Empfangsdiode an GP14 (Signal) / GP15 (Software-Versorgung, dauerhaft HIGH)
  mit externem Pull-Down-Widerstand (~4,7-10kOhm) von GP14 nach GND
- IR-Sende-LED an GP18 mit Vorwiderstand (100-220 Ohm) nach GND
- Status-LED an GP13 (blinkt beim Warten, leuchtet dauerhaft bei Erfolg)
- IR-Strahler-Relais/MOSFET an frei waehlbarem GPIO (siehe `ir_strahler.py`)

## Dateien

- `ir_learn.py` - nimmt IR-Signale roh auf (Interrupt-basiert) und speichert
  sie unter einem Namen
- `ir_send.py` - spielt einen gespeicherten Code ueber die Sende-LED ab
  (38kHz-Traegerfrequenz)
- `ir_codes.py` - Speichern/Laden der gelernten Codes als JSON (`/codes.json`
  auf dem Pico-Flash)
- `ir_strahler.py` - konfigurierbare An/Aus-Blitzsteuerung per Hardware-Timer
- `ir_raw_capture.py` - einfaches Debug-Skript zum Anzeigen roher Impulszeiten
- `codes.json` - Sicherung der bereits eingelernten Tasten der Raytec-Fernbedienung

## Verwendung

```python
from ir_learn import learn
learn('power_5')          # Taste drücken waehrend die Status-LED blinkt

from ir_send import send_by_name
send_by_name('power_5')   # gespeicherten Code abspielen
```
