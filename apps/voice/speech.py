
import re
import unicodedata


MAX_SPEECH_CHARS = 1200

_DIGITS = ('zéro', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept', 'huit', 'neuf')
_SMALL = {
    0: 'zéro', 1: 'un', 2: 'deux', 3: 'trois', 4: 'quatre', 5: 'cinq', 6: 'six',
    7: 'sept', 8: 'huit', 9: 'neuf', 10: 'dix', 11: 'onze', 12: 'douze',
    13: 'treize', 14: 'quatorze', 15: 'quinze', 16: 'seize',
}
_TENS = {20: 'vingt', 30: 'trente', 40: 'quarante', 50: 'cinquante', 60: 'soixante'}


def _under_hundred(value):
    if value <= 16:
        return _SMALL[value]
    if value < 20:
        return 'dix-' + _SMALL[value - 10]
    if value < 70:
        tens = value // 10 * 10
        unit = value % 10
        return _TENS[tens] + ((' et un' if tens == 20 else '-un') if unit == 1 else ('-' + _SMALL[unit] if unit else ''))
    if value < 80:
        rest = value - 60
        return 'soixante et onze' if value == 71 else 'soixante-' + _under_hundred(rest)
    if value == 80:
        return 'quatre-vingts'
    return 'quatre-vingt-' + _under_hundred(value - 80)


def _under_thousand(value):
    if value < 100:
        return _under_hundred(value)
    hundreds, rest = divmod(value, 100)
    prefix = 'cent' if hundreds == 1 else _SMALL[hundreds] + ' cent'
    if rest == 0:
        return prefix + ('s' if hundreds > 1 else '')
    return prefix + ' ' + _under_hundred(rest)


def _number_to_french(value):
    if value < 0:
        return 'moins ' + _number_to_french(-value)
    if value < 1000:
        return _under_thousand(value)
    if value < 1_000_000:
        thousands, rest = divmod(value, 1000)
        prefix = 'mille' if thousands == 1 else _under_thousand(thousands) + ' mille'
        return prefix + ((' ' + _under_thousand(rest)) if rest else '')
    if value < 1_000_000_000:
        millions, rest = divmod(value, 1_000_000)
        prefix = _number_to_french(millions) + (' million' if millions == 1 else ' millions')
        return prefix + ((' ' + _number_to_french(rest)) if rest else '')
    return ' '.join(_DIGITS[int(char)] for char in str(value))


def _speak_decimal(match):
    whole = _number_to_french(int(match.group(1)))
    fraction = ' '.join(_DIGITS[int(digit)] for digit in match.group(2))
    return f'{whole} virgule {fraction}'


def _speak_number(value):
    value = value.replace(',', '.')
    if '.' not in value:
        return _number_to_french(int(value))
    whole, fraction = value.split('.', 1)
    negative = whole.startswith('-')
    whole = whole.lstrip('-')
    prefix = 'moins ' if negative else ''
    return prefix + _number_to_french(int(whole)) + ' virgule ' + ' '.join(
        _DIGITS[int(digit)] for digit in fraction
    )


def _speak_identifier(match):
    identifier = match.group(0)
    parts = identifier.split('-')
    lead = 'alerte' if parts[0].upper() == 'AL' else parts[0].upper()
    spoken = [lead]
    for part in parts[1:]:
        if part.isdigit():
            spoken.extend(_DIGITS[int(digit)] for digit in part)
        else:
            spoken.append(part.upper())
    return ' '.join(spoken)


def _strip_markdown(text):
    text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'[`*_~]+', '', text)
    lines = []
    for line in text.splitlines() or [text]:
        if re.fullmatch(r'[ \t]*\|?[ \t]*:?-{3,}(?:[ \t]*\|[ \t]*:?-{3,})*[ \t]*\|?[ \t]*', line):
            continue
        line = re.sub(r'^\s{0,3}#{1,6}\s*', '', line.strip())
        line = re.sub(r'^(?:[-*+]\s+|\d+[.)]\s+)', '', line)
        line = line.strip().strip('|').strip().replace('|', ', ')
        line = re.sub(r'\s+,', ',', line)
        if line:
            lines.append(line)
    return '. '.join(lines)


def normalize_speech(value, max_chars=MAX_SPEECH_CHARS):
    
    text = _strip_markdown(str(value or ''))
    text = re.sub(r'\bAL-\d{3,}\b|\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b', _speak_identifier, text)
    text = re.sub(r'°\s+([cCfF])', r'°\1', text)
    units = {
        '%': ' pour cent', 'mm/s': ' millimètres par seconde', 'cm/s': ' centimètres par seconde',
        'm/s': ' mètres par seconde', 'rpm': ' tours par minute', 'tr/min': ' tours par minute',
        'l/min': ' litres par minute', 'l/s': ' litres par seconde', 'kw': ' kilowatts',
        'kwh': ' kilowattheures', 'bar': ' bars', '°c': ' degrés Celsius', '°f': ' degrés Fahrenheit',
        'a': ' ampères', 'v': ' volts', 'hz': ' hertz', 'db': ' décibels', 'kg': ' kilogrammes',
        's': ' secondes', 'min': ' minutes', 'h': ' heures',
    }
    unit_pattern = re.compile(r'(?i)(?<![\w-])(-?\d+(?:[.,]\d+)?)\s*(mm/s|cm/s|m/s|tr/min|l/min|l/s|kwh|kw|rpm|bar|°c|°f|hz|db|kg|%|a|v|s|min|h)(?![a-z])')
    def speak_unit(match):
        return _speak_number(match.group(1)) + units[match.group(2).lower()]
    text = unit_pattern.sub(speak_unit, text)
    text = re.sub(r'(?<![\w-])(-?\d+)[.,](\d+)(?!\w)', _speak_decimal, text)
    text = re.sub(r'(?<![\w-])-?\d+(?![\w-])', lambda m: _number_to_french(int(m.group(0))), text)
    text = text.replace('∞', ' infini ').replace('−', ' moins ').replace('–', ' à ').replace('—', ' à ')
    text = re.sub(r'[^\w\s.,;:!?\'-]', ' ', text, flags=re.UNICODE)
    text = re.sub(r'[_/\\]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip(' ,;:')
    if not text:
        return ''
    text = unicodedata.normalize('NFC', text)
    return text[:max(0, int(max_chars))].rstrip()


def split_speech_sentences(value):
    """Split normalized speech into bounded sentence strings."""
    text = str(value or '').strip()
    if not text:
        return []
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [part.strip() for part in parts if part.strip()]


def make_spoken_summary(value, max_chars=250):
    suffix = 'Dites confirme ou annule.'
    room = max(0, max_chars - len(suffix) - 2)
    summary = normalize_speech(value, max_chars=room).rstrip(' .,:;')
    return f'{summary}. {suffix}' if summary else suffix
