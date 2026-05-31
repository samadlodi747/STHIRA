import math
from collections.abc import Mapping, Sequence


def finite_or_none(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def clean_for_json(value):
    if isinstance(value, Mapping):
        return {key: clean_for_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [clean_for_json(item) for item in value]
    return finite_or_none(value)
