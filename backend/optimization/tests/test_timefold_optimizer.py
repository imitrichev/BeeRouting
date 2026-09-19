"""Проверки доступности альтернативного Timefold solver."""

import shutil

import pytest

from backend.optimization import (
    RouteOptimizer,
    TimefoldOptimizer,
    TimefoldUnavailableError,
)


def test_timefold_optimizer_is_a_separate_route_optimizer() -> None:
    """Timefold подключается рядом с OR-Tools через общий интерфейс."""

    optimizer = TimefoldOptimizer(time_limit_seconds=1)

    assert isinstance(optimizer, RouteOptimizer)
    assert optimizer.config.time_limit_minutes > 0


def test_timefold_default_limit_is_twenty_seconds() -> None:
    """Лимит Timefold по умолчанию не наследуется ошибочно от минут OR-Tools."""

    assert TimefoldOptimizer().time_limit_seconds == 20


@pytest.mark.skipif(
    shutil.which("java") is None,
    reason="Проверка сообщения об отсутствии JVM нужна только без Java",
)
def test_timefold_runs_when_jvm_is_available() -> None:
    """При наличии Java проверяем, что solver действительно запускается."""

    from backend.optimization.tests.test_ortools_optimizer import build_problem

    try:
        result = TimefoldOptimizer(time_limit_seconds=1).optimize(build_problem())
    except TimefoldUnavailableError as exc:
        pytest.fail(f"JVM найден, но Timefold не запустился: {exc}")
    assert result.assigned_task_count >= 0
