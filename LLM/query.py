import os
import uuid
import json
import requests
from dotenv import load_dotenv

SYSTEM_PROMPT = """
Ты формируешь краткое объяснение результата назначения заявки для диспетчера.

Используй только факты из переданного JSON.
Не придумывай причины, время, расстояния, ограничения или преимущества.
Выбери до 5 наиболее важных причин.
Если другой инженер тоже подходит, не называй его неподходящим.
Если есть существенно лучшая допустимая альтернатива или must_mention=true,
обязательно укажи её.
Одинаковые причины для нескольких инженеров можно объединять.
Незначительные отличия по пробегу или времени можно не упоминать.
Если "distance_difference_km" или "travel_time_difference_min" отрицательные,
то это значит, что предлагаемая альтернатива лучше, и можно ее предложить как улучшение.
Если же они положительны, то альтернативный вариант хуже.

Пиши кратко, естественно и понятно на русском языке.
"""


def get_access_token() -> str:
    """Получает временный access token по постоянному Authorization key."""

    response = requests.post(
        "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        headers={
            "Authorization": f"Basic {os.environ['GIGACHAT_AUTH_KEY']}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        data={
            "scope": "GIGACHAT_API_PERS",
        },
        timeout=30,
    )

    response.raise_for_status()
    return response.json()["access_token"]


def explain_assignment(decision_trace: dict) -> str:
    """Отправляет DecisionTrace в GigaChat и получает объяснение."""

    access_token = get_access_token()

    user_prompt = (
        "Сформируй краткое объяснение назначения заявки для диспетчера.\n\n"
        "Данные:\n"
        + json.dumps(
            decision_trace,
            ensure_ascii=False,
            indent=2,
        )
    )

    response = requests.post(
        "https://api.giga.chat/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json={
            "model": "GigaChat-3-Ultra",
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            "temperature": 0.2,
        },
        timeout=30,
    )

    response.raise_for_status()

    return response.json()["choices"][0]["message"]["content"]

decision_trace = {
    "task": {
        "id": "J70802",
        "required_skill": "Аварийные работы",
        "required_equipment": ["OTDR"],
        "window_start": "14:00",
        "window_end": "16:00"
    },

    "assigned_engineer": {
        "id": "E04",
        "name": "Сергей Иванов"
    },

    "alternative_engineers": [
        {
            "name": "Алексей Петров",
            "feasible": False,
            "reasons": [
                {
                    "type": "MISSING_SKILL",
                    "required_skill": "Аварийные работы"
                }
            ]
        },
        {
            "name": "Николай Козлов",
            "feasible": False,
            "reasons": [
                {
                    "type": "MISSING_EQUIPMENT",
                    "missing_equipment": ["OTDR"]
                }
            ]
        },
        {
            "name": "Дмитрий Волков",
            "feasible": True,
            "impact": {
                "distance_difference_km": 7.2,
                "travel_time_difference_min": 15
            }
        },
        {
            "name": "Павел Сидоров",
            "feasible": True,
            "impact": {
                "distance_difference_km": -0.4,
                "travel_time_difference_min": -1
            }
        }
    ]
}

load_dotenv()

text = explain_assignment(decision_trace)

print(text)
