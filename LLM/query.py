import os
import uuid
import json
from pathlib import Path
import argparse
import requests
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """
Ты формируешь краткое объяснение результата назначения заявки для диспетчера.

Используй только факты из переданного JSON.
Не придумывай причины, время, расстояния, ограничения или преимущества.
Первое предложение обязательно начинай так: «Заявка [task.id] назначена
инженеру [assignment.engineer.name]». Если заявка не назначена, начинай:
«Заявка [task.id] не назначена».
Выбери до 5 наиболее важных причин.
Если другой инженер тоже подходит, не называй его неподходящим.
Если есть существенно лучшая допустимая альтернатива или must_mention=true,
обязательно укажи её.
Поле must_mention=true означает, что факт явно важен для диспетчера.
Не добавляй в текст все проверки подряд: используй прежде всего причины с
must_mention=true, а остальные факты — только если они нужны для связного
объяснения.
В decision trace используются события task_assignment_explanation,
candidate_assessment, deterministic_insertion_check,
counterfactual_optimization, ASSIGNMENT_REASON, UNASSIGNED_REASON и
OBJECTIVE_IMPACT.
Одинаковые причины для нескольких инженеров можно объединять.
Незначительные отличия по пробегу или времени можно не упоминать.
Поля "distance_difference_km" и "travel_time_difference_min" описывают только
изменение отдельных метрик. Итоговое решение принимай по
"objective_difference" или по "objective.delta.total_objective": отрицательное
значение означает улучшение, положительное — ухудшение. Например, альтернатива
может сократить пробег, но стать хуже из-за штрафа за дополнительного инженера.
В таком случае не предлагай переназначение как улучшение, а объясни, что выигрыш
по пробегу не покрывает стоимость нового маршрута.
Если в counterfactual-расчёте есть поля
current_assigned_engineer_distance_km и alternative_engineer_distance_km,
используй их для конкретного сравнения пробега инженеров.

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

def load_decision_trace(path: str | Path) -> dict:
    """Загружает реальный decision trace, сформированный backend-проверками."""
    trace_path = Path(path)
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Decision trace должен быть JSON-объектом")
    return payload


def main() -> None:
    """Отправляет JSON-проверку из файла в GigaChat и печатает ответ."""
    parser = argparse.ArgumentParser(
        description="Объяснение результата маршрутизации по decision trace"
    )
    parser.add_argument("trace", type=Path, help="JSON с результатами проверок")
    args = parser.parse_args()
    print(explain_assignment(load_decision_trace(args.trace)))


# Старый ручной тестовый decision_trace намеренно удалён из выполняемого кода.
# Его можно восстановить локально при отладке формата, но production-запросы
# должны использовать JSON, созданный ExplanationEngine.

if __name__ == "__main__":
    main()
