"""Single-nozzle Bambu models with the existing cloud print parameter contract."""
PRINTER_MODELS = {
    'N2S': 'Bambu Lab A1', 'C12': 'Bambu Lab P1S',
}


def canonical_model(value):
    if not isinstance(value, str):
        return ''
    aliases = {k: k for k in PRINTER_MODELS}
    aliases.update({name: key for key, name in PRINTER_MODELS.items()})
    aliases.update({name.removeprefix('Bambu Lab '): key for key, name in PRINTER_MODELS.items()})
    return aliases.get(value.strip(), '')


def supports_auto_swap(value):
    return canonical_model(value) == 'N2S'
