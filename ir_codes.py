import ujson

CODES_FILE = "/codes.json"


def load_codes():
    try:
        with open(CODES_FILE) as f:
            return ujson.load(f)
    except OSError:
        return {}


def save_code(name, durations):
    codes = load_codes()
    codes[name] = durations
    with open(CODES_FILE, "w") as f:
        ujson.dump(codes, f)


def list_codes():
    return list(load_codes().keys())
