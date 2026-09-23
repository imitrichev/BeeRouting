"""JSON-снимок domain-моделей: без pickle и без импорта классов из входных данных."""
from dataclasses import fields, is_dataclass
from enum import Enum
from backend.optimization import models
from backend.optimization.json_import import JsonScenario

# Разрешены только собственные модели ядра. JSON не может выполнять код.
TYPES = {name: value for name, value in vars(models).items()
         if isinstance(value, type) and (is_dataclass(value) or issubclass(value, Enum))}
TYPES['JsonScenario'] = JsonScenario


def encode(value):
    """Сохраняет типы кортежей, enum и ключей транспортных матриц."""
    if isinstance(value, Enum):
        return {'enum': type(value).__name__, 'value': value.value}
    if is_dataclass(value):
        return {'model': type(value).__name__, 'fields': {f.name: encode(getattr(value, f.name)) for f in fields(value)}}
    if isinstance(value, dict):
        return {'mapping': [[encode(k), encode(v)] for k, v in value.items()]}
    if isinstance(value, (tuple, list, set, frozenset)):
        return {'sequence': [encode(v) for v in value], 'kind': type(value).__name__}
    return value


def decode(value):
    """Восстанавливает снимок с повторной валидацией dataclass-моделей."""
    if not isinstance(value, dict):
        return value
    if 'enum' in value:
        return TYPES[value['enum']](value['value'])
    if 'model' in value:
        return TYPES[value['model']](**{k: decode(v) for k, v in value['fields'].items()})
    if 'mapping' in value:
        return {decode(k): decode(v) for k, v in value['mapping']}
    if 'sequence' in value:
        return {'tuple': tuple, 'list': list, 'set': set, 'frozenset': frozenset}[value['kind']](decode(v) for v in value['sequence'])
    raise ValueError('Неизвестный формат сохранённого состояния')
