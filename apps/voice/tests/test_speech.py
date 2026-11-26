import pytest

from apps.voice.speech import make_spoken_summary, normalize_speech, split_speech_sentences


@pytest.mark.parametrize(('source', 'expected'), [
    ('POMPE-001', 'POMPE zéro zéro un'),
    ('AL-000005', 'alerte zéro zéro zéro zéro zéro cinq'),
    ('TEMP-COMP-01', 'TEMP COMP zéro un'),
    ('La température est 85 °C.', 'La température est quatre-vingt-cinq degrés Celsius.'),
    ('Taux : 12.5 %', 'Taux : douze virgule cinq pour cent'),
    ('Vibration : 3,3 mm/s', 'Vibration : trois virgule trois millimètres par seconde'),
    ('Mesure 35 A et 220 V', 'Mesure trente-cinq ampères et deux cent vingt volts'),
    ('- 2 alertes\n- 1 machine', 'deux alertes. un machine'),
    ('| Machine | Valeur |\n|---|---|\n| Presse | 90 °C |', 'Machine, Valeur. Presse, quatre-vingt-dix degrés Celsius'),
    ('**État critique** — seuil > 80 °C', 'État critique à seuil quatre-vingts degrés Celsius'),
    ('Valeur -5.25', 'Valeur moins cinq virgule deux cinq'),
    ('', ''),
    (None, ''),
])
def test_normalize_speech_common_and_markdown_cases(source, expected):
    assert normalize_speech(source) == expected


def test_speech_is_bounded_and_removes_symbols():
    result = normalize_speech('Alerte !!! #machine $danger ⚠️ ' + ('texte ' * 500), max_chars=64)
    assert len(result) <= 64
    assert '$' not in result and '⚠' not in result and '#' not in result


def test_speech_removes_markdown_links_and_keeps_link_label():
    assert normalize_speech('[Documentation](https://example.com)') == 'Documentation'


def test_sentence_split_uses_normalized_text():
    assert split_speech_sentences('La pompe est normale. Le capteur est actif !') == [
        'La pompe est normale.', 'Le capteur est actif !',
    ]
    assert split_speech_sentences('') == []


@pytest.mark.parametrize('summary', [
    'Acquitter AL-000005 avec pièce remplacée.',
    'Créer un ordre pour POMPE-001 à 95 °C.',
    'x' * 1000,
    '',
])
def test_spoken_summary_always_has_confirmation_instruction_and_limit(summary):
    spoken = make_spoken_summary(summary)
    assert spoken.endswith('Dites confirme ou annule.')
    assert len(spoken) <= 250
    assert normalize_speech(spoken) == spoken
