import network
import socket
import time
import ujson
from ir_send import send_by_name
from ir_codes import list_codes
from ir_strahler import IRStrahler
from ir_learn import capture as rx_capture

WIFI_CONFIG_FILE = "/wifi_config.json"


def load_wifi_config():
    with open(WIFI_CONFIG_FILE) as f:
        cfg = ujson.load(f)
    return cfg["ssid"], cfg["password"]

STRAHLER_PIN = 16  # GP17 war defekt (haengt fest auf LOW), auf GP16 gewechselt
CONFIG_FILE = "/config.json"

strahler = IRStrahler(STRAHLER_PIN)

LAST_FILE = "/last_sent.json"
LAST_RX_FILE = "/last_rx.json"
STRAHLER_STATE_FILE = "/strahler_state.json"


def load_strahler_state():
    try:
        with open(STRAHLER_STATE_FILE) as f:
            state = ujson.load(f)
    except OSError:
        state = {}
    state.setdefault("mode", "off")
    state.setdefault("on_ms", 100)
    state.setdefault("off_ms", 50)
    state.setdefault("level", None)
    return state


def save_strahler_state(update):
    state = load_strahler_state()
    state.update(update)
    with open(STRAHLER_STATE_FILE, "w") as f:
        ujson.dump(state, f)
    return state


EVENT_LOG_FILE = "/event_log.jsonl"
MAX_LOG_ENTRIES = 300  # begrenzt die Logdatei, damit der Flash-Speicher nicht vollgeschrieben wird


def _format_ts(ts):
    try:
        y, mo, d, h, mi, s, _, _ = time.localtime(ts)
        return "{:04d}-{:02d}-{:02d}".format(y, mo, d), "{:02d}:{:02d} UTC".format(h, mi)
    except Exception:
        return str(ts), ""


def log_event(event, **kwargs):
    entry = {"ts": time.time(), "event": event}
    entry.update(kwargs)
    try:
        with open(EVENT_LOG_FILE, "a") as f:
            f.write(ujson.dumps(entry) + "\n")
    except OSError:
        return
    # Nur gelegentlich (bei deutlichem Ueberschreiten) neu schreiben und
    # kuerzen, um nicht bei jedem einzelnen Eintrag den ganzen Log neu zu
    # schreiben (schont den Flash-Speicher)
    try:
        with open(EVENT_LOG_FILE) as f:
            lines = f.readlines()
        if len(lines) > MAX_LOG_ENTRIES * 2:
            with open(EVENT_LOG_FILE, "w") as f:
                f.writelines(lines[-MAX_LOG_ENTRIES:])
    except OSError:
        pass


def load_log(limit=100):
    try:
        with open(EVENT_LOG_FILE) as f:
            lines = f.readlines()
    except OSError:
        return []
    entries = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            data = ujson.loads(line)
            data["date"], data["time"] = _format_ts(data["ts"])
            entries.append(data)
        except Exception:
            continue
    entries.reverse()
    return entries


def save_last_rx(durations):
    with open(LAST_RX_FILE, "w") as f:
        ujson.dump({"count": len(durations) if durations else 0, "durations": durations or []}, f)


def load_last_rx():
    try:
        with open(LAST_RX_FILE) as f:
            return ujson.load(f)
    except OSError:
        return {"count": 0, "durations": []}


def send_and_capture(name):
    from machine import Pin
    import time as _time
    from ir_codes import load_codes

    codes = load_codes()
    if name not in codes:
        raise ValueError("Unbekannter Code: " + name)

    Pin(15, Pin.OUT).value(1)
    edges = []

    def _irq(p):
        if len(edges) < 500:
            edges.append(_time.ticks_us())

    rx_pin = Pin(14, Pin.IN)
    rx_pin.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=_irq)

    status_led = Pin(13, Pin.OUT)
    status_led.value(1)
    _time.sleep_ms(30)
    send_by_name(name)
    status_led.value(0)
    _time.sleep_ms(150)

    rx_pin.irq(handler=None)

    durations = None
    if len(edges) >= 2:
        durations = [_time.ticks_diff(edges[i + 1], edges[i]) for i in range(len(edges) - 1)]
    save_last_rx(durations)
    return durations


def save_last(name):
    with open(LAST_FILE, "w") as f:
        ujson.dump({"name": name, "ts": time.time()}, f)


def load_last():
    try:
        with open(LAST_FILE) as f:
            return ujson.load(f)
    except OSError:
        return {"name": None, "ts": 0}


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return ujson.load(f)
    except OSError:
        return {"projektnummer": "", "standort": "", "notizen": ""}


def save_config(data):
    cfg = load_config()
    cfg.update(data)
    with open(CONFIG_FILE, "w") as f:
        ujson.dump(cfg, f)
    return cfg


HTML_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Raytec Fernbedienung</title>
<style>
  *{box-sizing:border-box}
  body{font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:380px;margin:20px auto;padding:0 12px;background:#e9e9e9}
  .remote{background:#f5f5f0;border:3px solid #1a1a1a;border-radius:32px;padding:20px 16px 26px;box-shadow:0 6px 16px rgba(0,0,0,.2)}
  .headers{display:grid;grid-template-columns:repeat(3,1fr);text-align:center;font-weight:700;font-size:12px;letter-spacing:.03em;color:#222;margin-bottom:10px}
  .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:18px}
  .btn{position:relative;aspect-ratio:1;border-radius:50%;border:none;background:#e8e8e3;box-shadow:inset 0 1px 2px rgba(255,255,255,.8), 0 1px 2px rgba(0,0,0,.15);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;cursor:pointer;color:#222;user-select:none}
  .btn:active{filter:brightness(.92)}
  .btn.empty{visibility:hidden;box-shadow:none;background:none}
  .btn svg{width:66%;height:66%}
  .fill .ring{position:absolute;inset:0;border-radius:50%;background:conic-gradient(#c62828 var(--pct,0%), #f5f5f0 0)}
  .fill .stem{position:absolute;top:-4px;left:50%;transform:translateX(-50%);width:8px;height:5px;background:#1a1a1a;border-radius:2px;z-index:2}
  .crossed{position:relative}
  .crossed::after{content:'';position:absolute;width:126%;height:2px;background:#1a1a1a;transform:rotate(-40deg);z-index:3}
  .last-sent{box-shadow:0 0 0 3px #2e7d32, inset 0 1px 2px rgba(255,255,255,.8) !important}
  .last-sent::before{content:'';position:absolute;top:-3px;right:-3px;width:12px;height:12px;border-radius:50%;background:#2e7d32;border:2px solid #f5f5f0;z-index:4}
  .pill.last-sent{box-shadow:0 0 0 3px #2e7d32 !important}
  .sbtn.active-state,.btn.active-state{box-shadow:0 0 0 3px #2e7d32 !important}
  @keyframes pendingBlink{0%,100%{box-shadow:0 0 0 3px #2e7d32}50%{box-shadow:0 0 0 3px transparent}}
  .btn.pending-blink{animation:pendingBlink 0.6s infinite}
  .last-label{text-align:center;font-size:11px;color:#2e7d32;font-weight:700;margin-top:8px;min-height:14px}
  .telemetry{border:2px solid #1a1a1a;border-radius:22px;padding:10px 12px 14px;margin-bottom:18px}
  .telemetry-label{text-align:center;font-size:11px;font-weight:700;letter-spacing:.05em;margin-bottom:8px;color:#222}
  .telemetry-row{display:flex;gap:10px}
  .pill{flex:1;border-radius:20px;background:#e8e8e3;box-shadow:inset 0 1px 2px rgba(255,255,255,.8), 0 1px 2px rgba(0,0,0,.15);padding:12px 0;text-align:center;font-size:12px;font-weight:700;cursor:pointer}
  .pill:active{filter:brightness(.92)}
  .bottom-row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
  .btn.lock{background:#c62828;box-shadow:0 1px 2px rgba(0,0,0,.3)}
  .btn.lock::after{background:#fff}
  .btn.reset{background:#c62828;color:#fff;box-shadow:0 1px 2px rgba(0,0,0,.3)}
  .brand{text-align:center;margin-top:16px}
  .brand .ray{color:#c62828;font-weight:800;font-size:22px;font-style:italic}
  .brand .tec{color:#555;font-weight:800;font-size:22px}
  .section{margin-top:22px;padding-top:14px;border-top:1px solid #ccc}
  .section h3{margin:0 0 10px;font-size:15px;color:#222}
  .row{display:flex;align-items:center;gap:8px;margin-bottom:10px;font-size:13px;flex-wrap:wrap}
  input,textarea{padding:7px;font-size:14px;border:1px solid #999;border-radius:6px;font-family:inherit}
  input[type=number]{width:70px}
  input[type=text]{flex:1;min-width:120px}
  textarea{width:100%;min-height:60px;resize:vertical}
  .sbtn{padding:10px;font-size:14px;border-radius:8px;border:1px solid #333;background:#fff;flex:1;cursor:pointer}
  .sbtn.stop{background:#333;color:#fff}
  .sbtn.save{background:#2e7d32;color:#fff;border-color:#1b5e20}
  #status,#cfgstatus{font-size:13px;color:#555;margin-top:6px}
  .state-badge{font-weight:700;padding:2px 8px;border-radius:10px;background:#ccc;color:#333}
  .state-badge.on{background:#2e7d32;color:#fff}
  .state-badge.off{background:#999;color:#fff}
  .info-icon{display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:50%;background:#777;color:#fff;font-size:11px;font-style:italic;font-weight:700;cursor:help;position:relative;margin-left:6px;vertical-align:middle}
  .info-icon .tooltip{visibility:hidden;opacity:0;position:absolute;top:130%;left:0;width:230px;background:#222;color:#fff;font-size:11px;font-style:normal;font-weight:400;line-height:1.5;padding:10px 12px;border-radius:8px;transition:opacity .15s;z-index:10;text-align:left;box-shadow:0 4px 12px rgba(0,0,0,.3)}
  .info-icon:hover .tooltip,.info-icon:active .tooltip{visibility:visible;opacity:1}
  .btn-tooltip{position:fixed;visibility:hidden;opacity:0;background:#222;color:#fff;font-size:12px;line-height:1.5;padding:10px 12px;border-radius:8px;max-width:220px;z-index:100;box-shadow:0 4px 12px rgba(0,0,0,.35);transition:opacity .15s;pointer-events:none}
  .btn-tooltip.show{visibility:visible;opacity:1}
  .wifi-bar{display:flex;justify-content:flex-end;align-items:center;gap:6px;margin-bottom:10px;font-size:11px;color:#555}
  .wifi-bar svg{width:20px;height:16px}
  .wifi-bar rect{fill:#ccc}
  .wifi-bar rect.on{fill:#2e7d32}
  .wifi-bar.weak rect.on{fill:#c62828}
  details.section summary{cursor:pointer;font-size:15px;font-weight:700;color:#222;list-style:none}
  details.section summary::-webkit-details-marker{display:none}
  details.section summary::before{content:'\25B8 ';display:inline-block;transition:transform .15s}
  details.section[open] summary::before{transform:rotate(90deg)}
  .log-list{max-height:220px;overflow-y:auto;font-size:12px;border:1px solid #ccc;border-radius:6px;background:#fafafa}
  .log-date{padding:5px 8px;background:#e8e8e3;font-weight:700;font-size:11px;color:#444}
  .log-entry{padding:6px 8px;border-bottom:1px solid #e0e0e0}
  .log-entry:last-child{border-bottom:none}
  .log-time{color:#777;margin-right:6px}
</style></head><body>
<div class="wifi-bar" id="wifiBar" title="WLAN-Signal">
  <svg viewBox="0 0 20 16"><rect class="b1" x="0" y="11" width="3" height="5"/><rect class="b2" x="5" y="8" width="3" height="8"/><rect class="b3" x="10" y="4" width="3" height="12"/><rect class="b4" x="15" y="0" width="3" height="16"/></svg>
  <span id="wifiDbm">--</span>
</div>
<div class="section" style="margin-top:0;padding-top:0;border-top:none">
  <h3>Projektnummer</h3>
  <div class="row">
    <input id="projektnummer" type="text" placeholder="z.B. P-2026-0142">
  </div>
  <h3>Standort</h3>
  <div class="row">
    <input id="standort" type="text" placeholder="z.B. Lagerhalle Nord, Mast 3">
  </div>
  <h3>Notizen</h3>
  <div class="row">
    <textarea id="notizen" placeholder="Freitext..."></textarea>
  </div>
  <div class="row">
    <button class="sbtn save" onclick="saveConfig()">Speichern</button>
  </div>
  <p id="cfgstatus"></p>
</div>

<div class="remote">
  <div class="headers"><div>POWER</div><div>PHOTOCELL</div><div>TIMER</div></div>
  <div class="grid">
    <div class="btn" data-code="power_5"><svg viewBox="0 0 40 40" stroke="#222" stroke-width="1.8" fill="none">
  <circle cx="10" cy="20" r="8.5"/>
  <text x="7" y="24" font-size="11" font-weight="700" stroke="none" fill="#222">5</text>
  <path d="M18.5 6 A16 16 0 0 1 18.5 34" stroke-linecap="round"/>
  <line x1="21" y1="11" x2="29" y2="11" stroke-linecap="round"/>
  <line x1="23" y1="17" x2="32" y2="17" stroke-linecap="round"/>
  <line x1="23" y1="23" x2="32" y2="23" stroke-linecap="round"/>
  <line x1="21" y1="29" x2="29" y2="29" stroke-linecap="round"/>
</svg></div>
    <div class="btn" data-code="photocell_1"><svg viewBox="0 0 24 24" fill="none" stroke="#222" stroke-width="1.6">
      <circle cx="12" cy="12" r="8.5"/>
      <circle cx="9" cy="10" r="1.2" fill="#222" stroke="none"/>
      <circle cx="15" cy="10" r="1.2" fill="#222" stroke="none"/>
    </svg></div>
    <div class="btn fill" data-code="timer_full" style="--pct:100%;color:#fff"><div class="ring"></div><div class="stem"></div></div>

    <div class="btn" data-code="power_4"><svg viewBox="0 0 40 40" stroke="#222" stroke-width="1.8" fill="none">
  <circle cx="10" cy="20" r="8.5"/>
  <text x="7" y="24" font-size="11" font-weight="700" stroke="none" fill="#222">4</text>
  <path d="M18.5 6 A16 16 0 0 1 18.5 34" stroke-linecap="round"/>
  <line x1="21" y1="11" x2="29" y2="11" stroke-linecap="round"/>
  <line x1="23" y1="17" x2="32" y2="17" stroke-linecap="round"/>
  <line x1="23" y1="23" x2="32" y2="23" stroke-linecap="round"/>
  <line x1="21" y1="29" x2="29" y2="29" stroke-linecap="round"/>
</svg></div>
    <div class="btn" data-code="photocell_2"><svg viewBox="0 0 24 24">
      <mask id="m2"><rect width="24" height="24" fill="#fff"/><circle cx="15" cy="8.5" r="8.3" fill="#000"/></mask>
      <circle cx="12" cy="12" r="8.5" fill="#222" mask="url(#m2)"/>
    </svg></div>
    <div class="btn fill" data-code="timer_75" style="--pct:75%"><div class="ring"></div><div class="stem"></div></div>

    <div class="btn" data-code="power_3"><svg viewBox="0 0 40 40" stroke="#222" stroke-width="1.8" fill="none">
  <circle cx="10" cy="20" r="8.5"/>
  <text x="7" y="24" font-size="11" font-weight="700" stroke="none" fill="#222">3</text>
  <path d="M18.5 6 A16 16 0 0 1 18.5 34" stroke-linecap="round"/>
  <line x1="21" y1="11" x2="29" y2="11" stroke-linecap="round"/>
  <line x1="23" y1="17" x2="32" y2="17" stroke-linecap="round"/>
  <line x1="23" y1="23" x2="32" y2="23" stroke-linecap="round"/>
  <line x1="21" y1="29" x2="29" y2="29" stroke-linecap="round"/>
</svg></div>
    <div class="btn" data-code="photocell_3"><svg viewBox="0 0 24 24">
      <mask id="m3"><rect width="24" height="24" fill="#fff"/><circle cx="17.5" cy="7" r="8.3" fill="#000"/></mask>
      <circle cx="12" cy="12" r="8.5" fill="#222" mask="url(#m3)"/>
    </svg></div>
    <div class="btn fill" data-code="timer_50" style="--pct:50%"><div class="ring"></div><div class="stem"></div></div>

    <div class="btn" data-code="power_2"><svg viewBox="0 0 40 40" stroke="#222" stroke-width="1.8" fill="none">
  <circle cx="10" cy="20" r="8.5"/>
  <text x="7" y="24" font-size="11" font-weight="700" stroke="none" fill="#222">2</text>
  <path d="M18.5 6 A16 16 0 0 1 18.5 34" stroke-linecap="round"/>
  <line x1="21" y1="11" x2="29" y2="11" stroke-linecap="round"/>
  <line x1="23" y1="17" x2="32" y2="17" stroke-linecap="round"/>
  <line x1="23" y1="23" x2="32" y2="23" stroke-linecap="round"/>
  <line x1="21" y1="29" x2="29" y2="29" stroke-linecap="round"/>
</svg></div>
    <div class="btn crossed" data-code="photocell_off"><svg viewBox="0 0 24 24">
      <mask id="m4"><rect width="24" height="24" fill="#fff"/><circle cx="17.5" cy="7" r="8.3" fill="#000"/></mask>
      <circle cx="12" cy="12" r="8.5" fill="#222" mask="url(#m4)"/>
    </svg></div>
    <div class="btn fill" data-code="timer_25" style="--pct:25%"><div class="ring"></div><div class="stem"></div></div>

    <div class="btn" data-code="power_1"><svg viewBox="0 0 40 40" stroke="#222" stroke-width="1.8" fill="none">
  <circle cx="10" cy="20" r="8.5"/>
  <text x="7" y="24" font-size="11" font-weight="700" stroke="none" fill="#222">1</text>
  <path d="M18.5 6 A16 16 0 0 1 18.5 34" stroke-linecap="round"/>
  <line x1="21" y1="11" x2="29" y2="11" stroke-linecap="round"/>
  <line x1="23" y1="17" x2="32" y2="17" stroke-linecap="round"/>
  <line x1="23" y1="23" x2="32" y2="23" stroke-linecap="round"/>
  <line x1="21" y1="29" x2="29" y2="29" stroke-linecap="round"/>
</svg></div>
    <div class="btn empty"></div>
    <div class="btn fill crossed" data-code="timer_off" style="--pct:0%"><div class="ring"></div><div class="stem"></div></div>

  </div>

  <div class="telemetry">
    <div class="telemetry-label">TELEMETRY</div>
    <div class="telemetry-row">
      <div class="pill" data-code="tel">TEL</div>
      <div class="pill" data-code="dim">DIM</div>
    </div>
  </div>

  <div class="bottom-row">
    <div class="btn lock crossed" data-code="lock"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.6">
  <rect x="9" y="4" width="7" height="16" rx="3"/>
  <circle cx="12.5" cy="8" r="0.9" fill="#fff" stroke="none"/>
  <path d="M17 8A6 6 0 0 1 17 16" stroke-linecap="round"/>
  <path d="M19.3 5.3A10 10 0 0 1 19.3 18.7" stroke-linecap="round"/>
</svg></div>
    <div class="btn" data-code="status" style="font-size:9px">STATUS</div>
    <div class="btn reset" data-code="reset" style="font-size:10px">RESET</div>
  </div>

  <div class="brand"><span class="ray">ray</span><span class="tec">TEC</span></div>
  <div class="last-label" id="lastLabel"></div>
</div>

<div class="section">
  <div class="remote">
    <div class="telemetry">
      <div class="telemetry-label">Strahler pulsen
        <span class="info-icon">i<span class="tooltip">
          <b>Verkabelung</b> (Raytec External Input, Volt Free):<br>
          <b>Purple</b> &rarr; Pico <b>GND</b><br>
          <b>Orange</b> &rarr; Pico <b id="strahlerPin2">-</b><br><br>
          Open-Drain-Prinzip: "An" zieht die Leitung auf LOW (Kurzschluss-Simulation),
          "Aus" laesst sie als hochohmigen Eingang los. Es wird nie aktiv Spannung angelegt.
        </span></span>
      </div>
      <div class="row" style="font-size:11px;color:#666;justify-content:center">
        GPIO: <b id="strahlerPin">-</b> &nbsp;|&nbsp; Status: <span id="strahlerState" class="state-badge">-</span>
      </div>
      <div class="row" style="justify-content:center;margin-bottom:0">
        <label>An (ms)</label><input id="on_ms" value="100" type="number" oninput="scheduleTimingApply()">
        <label>Aus (ms)</label><input id="off_ms" value="50" type="number" oninput="scheduleTimingApply()">
      </div>
    </div>
    <div class="headers" style="grid-template-columns:repeat(2,1fr)"><div>PULS</div><div>DAUER</div></div>
    <div class="grid" style="grid-template-columns:repeat(2,1fr)">
      <div class="btn" id="btnStart" onclick="startStrahler()" style="font-size:11px" data-tooltip="Sendet einmalig photocell_off + tel + timer_off, dann startet der Puls-Timer (An/Aus im eingestellten ms-Rhythmus) am Relais-GPIO.">Start</div>
      <div class="btn" id="btnOn" onclick="strahlerOn()" style="font-size:11px" data-tooltip="Sendet einmalig photocell_off + tel + timer_off, dann schaltet das Relais dauerhaft auf An (kein Pulsen, durchgehendes Leuchten).">An</div>
      <div class="btn" id="btnStop" onclick="stopStrahler()" style="font-size:11px" data-tooltip="Stoppt den Puls-Timer und oeffnet den Relais-Kontakt (Aus).">Stop</div>
      <div class="btn" id="btnOff" onclick="strahlerOff()" style="font-size:11px" data-tooltip="Oeffnet den Relais-Kontakt dauerhaft (Aus), ohne den Telemetrie-Modus zu aendern.">Aus</div>
    </div>
    <div class="brand"><span class="ray">BERNARD</span><span class="tec">TEC</span></div>
  </div>
</div>

<details class="section">
  <summary>Log</summary>
  <div style="margin:10px 0 6px">
    <button class="sbtn" style="padding:4px 10px;font-size:12px;width:auto;display:inline-block" onclick="loadLog()">Aktualisieren</button>
    <button class="sbtn" style="padding:4px 10px;font-size:12px;width:auto;display:inline-block;background:#c62828;color:#fff;border-color:#8e1c1c" onclick="clearLog()">Log loeschen</button>
  </div>
  <div id="logList" class="log-list"></div>
</details>

<div class="btn-tooltip" id="btnTooltip"></div>

<script>
const HOLD_TO_SEND = {reset: 4, lock: 4};

function sendCode(b){
  b.style.filter='brightness(.7)';
  fetch('/api/send/'+b.dataset.code, {method:'POST'})
    .then(()=>markLast(b.dataset.code))
    .finally(()=>setTimeout(()=>b.style.filter='',150));
}

document.querySelectorAll('[data-code]').forEach(b=>{
  const holdSeconds = HOLD_TO_SEND[b.dataset.code];
  if(!holdSeconds){
    b.onclick = ()=>sendCode(b);
    return;
  }
  const originalHtml = b.innerHTML;
  let countdownTimer = null;
  let remaining = holdSeconds;
  const start = ()=>{
    remaining = holdSeconds;
    b.innerText = String(remaining);
    b.style.background = '#c62828';
    b.style.color = '#fff';
    b.style.fontSize = '28px';
    b.style.fontWeight = '800';
    countdownTimer = setInterval(()=>{
      remaining--;
      if(remaining <= 0){
        clearInterval(countdownTimer);
        countdownTimer = null;
        b.innerHTML = originalHtml;
        b.style.background = '';
        b.style.color = '';
        b.style.fontSize = '';
        b.style.fontWeight = '';
        sendCode(b);
      } else {
        b.innerText = String(remaining);
      }
    }, 1000);
  };
  const cancel = ()=>{
    if(countdownTimer){
      clearInterval(countdownTimer);
      countdownTimer = null;
      b.innerHTML = originalHtml;
      b.style.background = '';
      b.style.color = '';
      b.style.fontSize = '';
      b.style.fontWeight = '';
    }
  };
  b.addEventListener('mousedown', start);
  b.addEventListener('touchstart', (e)=>{e.preventDefault(); start();});
  b.addEventListener('mouseup', cancel);
  b.addEventListener('mouseleave', cancel);
  b.addEventListener('touchend', cancel);
  b.addEventListener('touchcancel', cancel);
  b.oncontextmenu = (e)=>e.preventDefault();
});
function markLast(name){
  document.querySelectorAll('.last-sent').forEach(el=>el.classList.remove('last-sent'));
  const el = document.querySelector('[data-code="'+name+'"]');
  if(el) el.classList.add('last-sent');
  document.getElementById('lastLabel').innerText = 'zuletzt gesendet: ' + name;
}
function loadLast(){
  fetch('/api/last').then(r=>r.json()).then(d=>{
    if(d.name) markLast(d.name);
  });
}
function startStrahler(){
  const on_ms = document.getElementById('on_ms').value;
  const off_ms = document.getElementById('off_ms').value;
  fetch('/api/strahler/start?on_ms='+on_ms+'&off_ms='+off_ms, {method:'POST'})
    .then(r=>r.json())
    .then(r=>{
      if(!r.ok) alert('Fehler: '+r.error);
      loadStrahlerStatus();
      loadLast();
    });
}
function stopStrahler(){
  fetch('/api/strahler/stop', {method:'POST'}).then(()=>loadStrahlerStatus());
}
function strahlerOn(){
  fetch('/api/strahler/on', {method:'POST'})
    .then(r=>r.json())
    .then(r=>{
      if(!r.ok) alert('Fehler: '+r.error);
      loadStrahlerStatus();
      loadLast();
    });
}
function strahlerOff(){
  fetch('/api/strahler/off', {method:'POST'}).then(()=>loadStrahlerStatus());
}
function loadStrahlerStatus(){
  fetch('/api/strahler/status').then(r=>r.json()).then(s=>{
    document.getElementById('strahlerPin').innerText = 'GP' + s.pin;
    document.getElementById('strahlerPin2').innerText = 'GP' + s.pin;
    const badge = document.getElementById('strahlerState');
    badge.innerText = s.running === true ? 'PULST' : (s.running ? 'AN' : 'AUS');
    badge.className = 'state-badge ' + (s.running ? 'on' : 'off');
    document.getElementById('btnStart').classList.toggle('active-state', s.running === true);
    document.getElementById('btnStop').classList.toggle('active-state', !s.running);
    document.getElementById('btnOn').classList.toggle('active-state', s.running === 'on');
    document.getElementById('btnOff').classList.toggle('active-state', !s.running);
    strahlerPulsing = (s.running === true);
    if(lastPushedOn === null){
      lastPushedOn = s.on_ms;
      lastPushedOff = s.off_ms;
    }
  });
}
setInterval(loadStrahlerStatus, 5000);

let strahlerPulsing = false;
let lastPushedOn = null;
let lastPushedOff = null;
let applyCountdown = null;
const btnStartOriginalHtml = 'Start';
function scheduleTimingApply(){
  if(!strahlerPulsing) return;
  const on_ms = document.getElementById('on_ms').value;
  const off_ms = document.getElementById('off_ms').value;
  const btnStart = document.getElementById('btnStart');
  if(on_ms == lastPushedOn && off_ms == lastPushedOff){
    if(applyCountdown){
      clearInterval(applyCountdown);
      applyCountdown = null;
      btnStart.classList.remove('pending-blink');
      btnStart.innerText = btnStartOriginalHtml;
      btnStart.style.fontSize = '';
      btnStart.style.fontWeight = '';
    }
    return;
  }
  if(applyCountdown) clearInterval(applyCountdown);
  let remaining = 10;
  btnStart.innerText = String(remaining);
  btnStart.style.fontSize = '24px';
  btnStart.style.fontWeight = '800';
  btnStart.classList.add('pending-blink');
  applyCountdown = setInterval(()=>{
    remaining--;
    if(remaining <= 0){
      clearInterval(applyCountdown);
      applyCountdown = null;
      btnStart.classList.remove('pending-blink');
      btnStart.innerText = btnStartOriginalHtml;
      btnStart.style.fontSize = '';
      btnStart.style.fontWeight = '';
      lastPushedOn = document.getElementById('on_ms').value;
      lastPushedOff = document.getElementById('off_ms').value;
      startStrahler();
    } else {
      btnStart.innerText = String(remaining);
    }
  }, 1000);
}
function loadConfig(){
  fetch('/api/config').then(r=>r.json()).then(cfg=>{
    document.getElementById('projektnummer').value = cfg.projektnummer || '';
    document.getElementById('standort').value = cfg.standort || '';
    document.getElementById('notizen').value = cfg.notizen || '';
  });
}
function saveConfig(){
  const data = {
    projektnummer: document.getElementById('projektnummer').value,
    standort: document.getElementById('standort').value,
    notizen: document.getElementById('notizen').value
  };
  fetch('/api/config', {method:'POST', body: JSON.stringify(data)})
    .then(()=>document.getElementById('cfgstatus').innerText='gespeichert');
}
function loadWifiStatus(){
  fetch('/api/wifi').then(r=>r.json()).then(w=>{
    const bar = document.getElementById('wifiBar');
    const bars = [1,2,3,4].map(n=>bar.querySelector('.b'+n));
    let count = 0;
    if (w.rssi >= -50) count = 4;
    else if (w.rssi >= -60) count = 3;
    else if (w.rssi >= -70) count = 2;
    else if (w.rssi >= -80) count = 1;
    else count = 0;
    bars.forEach((b,i)=>b.classList.toggle('on', i < count));
    bar.classList.toggle('weak', count <= 1);
    document.getElementById('wifiDbm').innerText = w.rssi + ' dBm';
  }).catch(()=>{});
}
setInterval(loadWifiStatus, 8000);
loadWifiStatus();
const LOG_LABELS = {
  boot: "Neustart (Stromausfall?)",
  start: "Puls gestartet",
  stop: "Puls gestoppt",
  on: "Dauerhaft an",
  off: "Ausgeschaltet",
  restore: "Automatisch wiederhergestellt"
};
function loadLog(){
  fetch('/api/log').then(r=>r.json()).then(entries=>{
    const el = document.getElementById('logList');
    if (!entries.length){
      el.innerHTML = '<div class="log-entry">Noch keine Eintraege</div>';
      return;
    }
    let html = '';
    let lastDate = null;
    entries.forEach(e=>{
      if (e.date !== lastDate){
        html += '<div class="log-date">' + e.date + '</div>';
        lastDate = e.date;
      }
      let label = LOG_LABELS[e.event] || e.event;
      if (e.on_ms !== undefined) label += ' (An ' + e.on_ms + 'ms / Aus ' + e.off_ms + 'ms)';
      else if (e.mode === 'on') label += ' (Dauerlicht)';
      html += '<div class="log-entry"><span class="log-time">' + e.time + '</span>' + label + '</div>';
    });
    el.innerHTML = html;
  }).catch(()=>{});
}
function clearLog(){
  if (!confirm('Log wirklich komplett loeschen?')) return;
  fetch('/api/log', {method:'DELETE'}).then(loadLog);
}
loadLog();
loadConfig();
loadLast();
loadStrahlerStatus();

const BUTTON_INFO = {
  power_5: "Power Select Stufe 5/5: 100% Helligkeit. Quick and easy selection of 5 accurately defined power settings.",
  power_4: "Power Select Stufe 4/5: 80% Helligkeit.",
  power_3: "Power Select Stufe 3/5: 60% Helligkeit.",
  power_2: "Power Select Stufe 2/5: 40% Helligkeit.",
  power_1: "Power Select Stufe 1/5: 20% Helligkeit.",
  photocell_1: "Photocell Adjust Stufe 1/3: waehlt eine von 3 Lichtempfindlichkeits-Stufen fuer die automatische Tag/Nacht-Steuerung.",
  photocell_2: "Photocell Adjust Stufe 2/3.",
  photocell_3: "Photocell Adjust Stufe 3/3.",
  photocell_off: "Photocell Disable: Lamp operates from telemetry input only. Der Strahler wird dann nur noch ueber den Telemetrie-Eingang (Orange/Purple) gesteuert, das eingebaute Photocell wird ignoriert.",
  timer_full: "Timer Setting: 30 Minuten. Der Strahler bleibt nach einem Telemetrie-Trigger 30 Minuten an.",
  timer_75: "Timer Setting: 10 Minuten.",
  timer_50: "Timer Setting: 3 Minuten.",
  timer_25: "Timer Setting: 1 Minute.",
  timer_off: "Timer Disable: keine automatische Abschaltzeit nach Telemetrie-Trigger.",
  tel: "Selects Telemetry Input (Konfigurationsfunktion fuer die Telemetrie-Leitungen).",
  dim: "Selects dimming function on telemetry wires (aktiviert Dimm-Funktion ueber die Telemetrie-Leitungen).",
  lock: "Disable Remote Control: sperrt die Fernbedienung, um versehentliche Aenderungen zu verhindern.",
  status: "LED Status Indicator: schaltet die Status-LEDs am Geraet ein oder aus.",
  reset: "Reset: stellt die Werkseinstellungen wieder her (am Original-Geraet 4 Sekunden gedrueckt halten)."
};

let tooltipTimer = null;
const tooltipEl = document.getElementById('btnTooltip');
document.querySelectorAll('[data-code], [data-tooltip]').forEach(b=>{
  const info = BUTTON_INFO[b.dataset.code] || b.dataset.tooltip;
  if(!info) return;
  b.addEventListener('mouseenter', (e)=>{
    tooltipTimer = setTimeout(()=>{
      tooltipEl.innerText = info;
      const rect = b.getBoundingClientRect();
      tooltipEl.style.left = Math.min(rect.left, window.innerWidth - 240) + 'px';
      tooltipEl.style.top = (rect.bottom + 6) + 'px';
      tooltipEl.classList.add('show');
    }, 3000);
  });
  b.addEventListener('mouseleave', ()=>{
    clearTimeout(tooltipTimer);
    tooltipEl.classList.remove('show');
  });
});
</script>
</body></html>
"""


def connect_wifi(ssid=None, password=None, timeout_s=15, retries=6):
    # Manche Access Points (z.B. mobile Hotspots) brauchen gelegentlich
    # mehrere Anlaeufe, bevor die Verbindung wirklich zustande kommt -
    # daher mehrere komplette Verbindungsversuche statt nur einem.
    #
    # Eingebaute LED als Status-Anzeige ohne USB-Zugriff:
    #   langsames Blinken = verbindet gerade
    #   durchgehend an     = verbunden
    #   kurzes schnelles Blinken = alle Versuche fehlgeschlagen
    from machine import Pin
    status_led = Pin("LED", Pin.OUT)

    if ssid is None or password is None:
        ssid, password = load_wifi_config()
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    try:
        wlan.config(pm=0xa11140)  # WLAN-Stromsparmodus aus - verursacht bei
        # manchen Access Points staendige Mini-Aussetzer, waehrend andere
        # Geraete (z.B. Laptops ohne diesen Sparmodus) am selben AP stabil
        # bleiben
    except Exception:
        pass
    for attempt in range(1, retries + 1):
        wlan.disconnect()
        time.sleep_ms(500)
        wlan.connect(ssid, password)
        start = time.ticks_ms()
        blink = False
        while time.ticks_diff(time.ticks_ms(), start) < timeout_s * 1000:
            if wlan.isconnected():
                status_led.value(1)
                print("WLAN verbunden:", wlan.ifconfig())
                return wlan
            blink = not blink
            status_led.value(blink)
            time.sleep_ms(200)
        print("WLAN-Versuch", attempt, "fehlgeschlagen (Status", wlan.status(), ")")
    for _ in range(10):
        status_led.value(not status_led.value())
        time.sleep_ms(80)
    status_led.value(0)
    raise RuntimeError("WLAN-Verbindung fehlgeschlagen nach " + str(retries) + " Versuchen")


def parse_query(query):
    params = {}
    for pair in query.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            params[k] = v
    return params


def handle_request(method, path, params, body):
    if path == "/" and method == "GET":
        return 200, "text/html", HTML_PAGE
    if path == "/api/buttons" and method == "GET":
        return 200, "application/json", ujson.dumps(list_codes())
    if path.startswith("/api/send/") and method == "POST":
        name = path[len("/api/send/"):]
        try:
            durations = send_and_capture(name)
            save_last(name)
            if name.startswith("power_"):
                save_strahler_state({"level": name})
            if name in ("reset", "lock"):
                # Original-Fernbedienung sendet bei diesen Tasten wiederholt
                # Signal, solange sie 4 Sek. gehalten wird (LEDs bleiben so
                # lange orange). Unsere Aufzeichnung enthaelt nur einen
                # einzelnen kurzen Burst - den also fuer ~4,5s wiederholen,
                # um das Halten nachzubilden.
                hold_start = time.ticks_ms()
                while time.ticks_diff(time.ticks_ms(), hold_start) < 4500:
                    time.sleep_ms(40)
                    send_by_name(name)
            if name not in ("photocell_off", "tel", "timer_off") and strahler.running:
                # Fast jede andere Taste (Power Select, Dim, Timer Setting,
                # Reset, ...) wechselt den Strahler intern von "Telemetrie
                # steuert An/Aus" auf einen manuellen/anderen Modus - er
                # leuchtet dann nur noch durchgehend in der gewaehlten Stufe
                # statt dem Relais zu folgen. Also nach jeder Fremd-Taste die
                # Telemetrie-Vorbereitung automatisch neu senden.
                time.sleep_ms(500)
                send_by_name("photocell_off")
                time.sleep_ms(500)
                send_by_name("tel")
                time.sleep_ms(500)
                send_by_name("timer_off")
                save_last("timer_off")
            return 200, "application/json", ujson.dumps({
                "ok": True,
                "rx_count": len(durations) if durations else 0,
            })
        except Exception as e:
            return 500, "application/json", ujson.dumps({"ok": False, "error": str(e)})
    if path == "/api/last" and method == "GET":
        return 200, "application/json", ujson.dumps(load_last())
    if path == "/api/last_rx" and method == "GET":
        return 200, "application/json", ujson.dumps(load_last_rx())
    if path == "/api/strahler/start" and method == "POST":
        on_ms = int(params.get("on_ms", 100))
        off_ms = int(params.get("off_ms", 50))
        if not strahler.running:
            try:
                send_by_name("photocell_off")
                time.sleep_ms(500)
                send_by_name("tel")
                time.sleep_ms(500)
                send_by_name("timer_off")
                time.sleep_ms(500)
                save_last("timer_off")
            except Exception as e:
                return 500, "application/json", ujson.dumps({"ok": False, "error": "Vorbereitung (photocell_off/tel/timer_off) fehlgeschlagen: " + str(e)})
        strahler.start(on_ms=on_ms, off_ms=off_ms)
        save_strahler_state({"mode": "pulse", "on_ms": on_ms, "off_ms": off_ms})
        log_event("start", on_ms=on_ms, off_ms=off_ms)
        return 200, "application/json", '{"ok":true}'
    if path == "/api/strahler/stop" and method == "POST":
        strahler.stop()
        save_strahler_state({"mode": "off"})
        log_event("stop")
        return 200, "application/json", '{"ok":true}'
    if path == "/api/strahler/on" and method == "POST":
        try:
            send_by_name("photocell_off")
            time.sleep_ms(500)
            send_by_name("tel")
            time.sleep_ms(500)
            send_by_name("timer_off")
            save_last("timer_off")
        except Exception as e:
            return 500, "application/json", ujson.dumps({"ok": False, "error": "Vorbereitung (photocell_off/tel/timer_off) fehlgeschlagen: " + str(e)})
        strahler.on()
        save_strahler_state({"mode": "on"})
        log_event("on")
        return 200, "application/json", '{"ok":true}'
    if path == "/api/strahler/off" and method == "POST":
        strahler.off()
        save_strahler_state({"mode": "off"})
        log_event("off")
        return 200, "application/json", '{"ok":true}'
    if path == "/api/strahler/status" and method == "GET":
        return 200, "application/json", ujson.dumps({
            "running": strahler.running,
            "pin": STRAHLER_PIN,
            "on_ms": strahler.on_ms,
            "off_ms": strahler.off_ms,
        })
    if path == "/api/wifi" and method == "GET":
        wlan = network.WLAN(network.STA_IF)
        try:
            rssi = wlan.status("rssi")
        except Exception:
            rssi = None
        return 200, "application/json", ujson.dumps({"rssi": rssi})
    if path == "/api/log" and method == "GET":
        return 200, "application/json", ujson.dumps(load_log())
    if path == "/api/log" and method == "DELETE":
        try:
            import os
            os.remove(EVENT_LOG_FILE)
        except OSError:
            pass
        return 200, "application/json", '{"ok":true}'
    if path == "/api/config" and method == "GET":
        return 200, "application/json", ujson.dumps(load_config())
    if path == "/api/config" and method == "POST":
        try:
            data = ujson.loads(body) if body else {}
            cfg = save_config(data)
            return 200, "application/json", ujson.dumps(cfg)
        except Exception as e:
            return 500, "application/json", ujson.dumps({"ok": False, "error": str(e)})
    return 404, "text/plain", "not found"


def check_wifi_reachable(gateway, timeout_s=3):
    """Echter Erreichbarkeits-Check (nicht nur wlan.isconnected(), das bei
    diesem Hotspot manchmal faelschlich 'verbunden' bleibt, obwohl die
    Verbindung tot ist): Verbindungsversuch zum Gateway. Ein abgelehnter
    Verbindungsaufbau (ECONNREFUSED) zaehlt auch als erreichbar - der Host
    hat ja geantwortet."""
    try:
        cs = socket.socket()
        cs.settimeout(timeout_s)
        cs.connect((gateway, 80))
        cs.close()
        return True
    except OSError as e:
        cs.close()
        return len(e.args) > 0 and e.args[0] == 111  # ECONNREFUSED
    except Exception:
        return False


def run_server(port=80):
    addr = socket.getaddrinfo("0.0.0.0", port)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(4)
    s.settimeout(20)  # Leerlauf-Gelegenheit fuer den WLAN-Watchdog unten
    wlan = network.WLAN(network.STA_IF)
    print("Server laeuft auf Port", port)
    while True:
        try:
            cl, remote_addr = s.accept()
        except OSError:
            # Kein Request in den letzten 20s - WLAN wirklich noch erreichbar?
            gateway = wlan.ifconfig()[2]
            if not wlan.isconnected() or not check_wifi_reachable(gateway):
                print("WLAN tot trotz isconnected()==", wlan.isconnected(), "- Reconnect...")
                try:
                    connect_wifi()
                except Exception as e:
                    print("Reconnect-Versuch fehlgeschlagen:", e)
            continue
        cl.settimeout(10)
        try:
            req = cl.recv(2048)
            if not req:
                continue
            header_end = req.find(b"\r\n\r\n")
            header_part = req[:header_end if header_end != -1 else len(req)].decode()
            lines = header_part.split("\r\n")
            request_line = lines[0]
            content_length = 0
            for h in lines[1:]:
                if h.lower().startswith("content-length:"):
                    content_length = int(h.split(":", 1)[1].strip())
            body_bytes = req[header_end + 4:] if header_end != -1 else b""
            while len(body_bytes) < content_length:
                body_bytes += cl.recv(1024)
            body = body_bytes.decode()

            parts = request_line.split(" ")
            method, path = parts[0], parts[1]
            query = ""
            if "?" in path:
                path, query = path.split("?", 1)
            params = parse_query(query)

            status, ctype, resp_body = handle_request(method, path, params, body)
            header = "HTTP/1.1 {} OK\r\nContent-Type: {}\r\nConnection: close\r\n\r\n".format(status, ctype)
            data = (header + resp_body).encode()
            mv = memoryview(data)
            total = 0
            while total < len(data):
                sent = cl.send(mv[total:])
                total += sent
        except Exception as e:
            print("Fehler bei Request:", e)
        finally:
            cl.close()


STRAHLER_BOOT_WAIT_MS = 10000  # Sicherheitswartezeit: falls der Strahler
# selbst gerade erst wieder Strom bekommen hat (gemeinsamer Stromausfall),
# muss er erst hochfahren, bevor sein IR-Empfaenger Befehle sicher
# entgegennimmt. Keine Angabe im Handbuch gefunden - Erfahrungswert.


def restore_state():
    """Stellt nach einem Neustart (Stromausfall Pico und/oder Strahler) den
    zuletzt aktiven Zustand wieder her: gewaehlte Power-Stufe und ob
    Pulsieren/Dauerlicht aktiv war."""
    state = load_strahler_state()
    if not state.get("level") and state.get("mode", "off") == "off":
        return
    time.sleep_ms(STRAHLER_BOOT_WAIT_MS)
    try:
        if state.get("level"):
            send_by_name(state["level"])
            time.sleep_ms(500)
        mode = state.get("mode", "off")
        if mode in ("pulse", "on"):
            send_by_name("photocell_off")
            time.sleep_ms(500)
            send_by_name("tel")
            time.sleep_ms(500)
            send_by_name("timer_off")
            save_last("timer_off")
            if mode == "pulse":
                strahler.start(on_ms=state.get("on_ms", 100), off_ms=state.get("off_ms", 50))
                log_event("restore", mode="pulse", on_ms=state.get("on_ms", 100), off_ms=state.get("off_ms", 50))
            else:
                strahler.on()
                log_event("restore", mode="on")
    except Exception as e:
        print("Zustand konnte nicht wiederhergestellt werden:", e)


def main():
    while True:
        try:
            connect_wifi()
            break
        except Exception as e:
            print("Boot-WLAN-Verbindung fehlgeschlagen, versuche es weiter:", e)
            time.sleep_ms(3000)
    try:
        import ntptime
        ntptime.settime()
    except Exception as e:
        print("NTP-Zeitsync fehlgeschlagen:", e)
    log_event("boot")
    try:
        import _thread
        import mdns_responder
        _thread.start_new_thread(mdns_responder.run, ("raytec",))
    except Exception as e:
        print("mDNS-Responder konnte nicht gestartet werden:", e)
    restore_state()
    run_server()


if __name__ == "__main__":
    main()
