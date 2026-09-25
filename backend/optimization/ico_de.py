"""Python-порт Countries Algorithm / ICO с адаптивной Differential Evolution.

Модуль перенесён из ``countries_algorithm_v2.hpp`` ветки ``island_DE``.
Имена ``Individual``, ``Country`` и ``CountriesAlgorithm`` сохранены по старой
Python-реализации ``country_optimization_v4.py``, чтобы алгоритм было проще
сопоставлять с работой авторов. Это независимый непрерывный оптимизатор: он не
зависит от Django, OR-Tools и доменных моделей маршрутизации.

Актуальный C++ по умолчанию фактически выполняет островную адаптивную DE:
вероятность страновых действий умножена там на ноль. Здесь страновые операции
сохранены, но также выключены параметром ``ico_actions_start_probability=0``.

Numba намеренно не применяется: основная стоимость находится в переданной
пользователем objective-функции, а её произвольный Python callback нельзя
безопасно компилировать в nopython-режиме.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import ceil, exp, inf
from typing import Callable, Sequence

import numpy as np

Objective = Callable[[np.ndarray], float]


class IndividualType(str, Enum):
    """Способ кодирования точки пространства поиска."""

    GRAY = "gray"
    REAL = "real"


@dataclass(slots=True)
class AdaptiveOperatorPair:
    """Адаптивно выбирает один из двух операторов размножения."""

    reward: np.ndarray = field(default_factory=lambda: np.full(2, 1e-6))
    probabilities: np.ndarray = field(default_factory=lambda: np.full(2, 0.5))

    def update(self, index: int, credit: float, alpha: float) -> None:
        """Обновляет EMA-награду оператора после рождения потомка."""
        if 0 <= index < 2:
            alpha = float(np.clip(alpha, 0.0, 1.0))
            self.reward[index] = (1.0 - alpha) * self.reward[index] + alpha * max(0.0, credit)

    def renormalize(self, floor_0: float, floor_1: float) -> None:
        """Преобразует награды в вероятности с заданными нижними границами."""
        floors = np.maximum([floor_0, floor_1], 0.0)
        if floors.sum() >= 1.0:
            self.probabilities = floors / floors.sum()
            return
        residual = 1.0 - floors.sum()
        reward_sum = self.reward.sum()
        shares = self.reward / reward_sum if reward_sum > 1e-30 else np.full(2, 0.5)
        self.probabilities = floors + residual * shares


def normalized_elite_credit(elite_threshold: float, child_f: float) -> float:
    """Даёт награду только потомку, который вошёл в текущую элитную область."""
    if not np.isfinite(elite_threshold) or not np.isfinite(child_f) or child_f >= elite_threshold:
        return 0.0
    return (elite_threshold - child_f) / (abs(elite_threshold) + abs(child_f) + 1.0)


def to_gray_code(number: int) -> int:
    """Кодирует неотрицательное целое кодом Грея."""
    return number ^ (number >> 1)


def from_gray_code(gray: int) -> int:
    """Декодирует код Грея в обычное неотрицательное целое."""
    number = 0
    while gray:
        number ^= gray
        gray >>= 1
    return number


@dataclass(slots=True)
class Individual:
    """Базовая особь с уже вычисленным значением минимизируемой функции."""

    x_min: np.ndarray
    x_max: np.ndarray
    f_value: float
    individual_type: IndividualType
    epidemic_count: int = 0

    def real_x(self) -> np.ndarray:
        """Возвращает точку в вещественных координатах."""
        raise NotImplementedError

    def clone(self) -> "Individual":
        """Создаёт независимую копию особи без повторного вызова objective."""
        raise NotImplementedError


@dataclass(slots=True)
class RealIndividual(Individual):
    """Особь с непосредственным вещественным представлением координат."""

    x: np.ndarray = field(default_factory=lambda: np.empty(0))

    @classmethod
    def create(
        cls, x: Sequence[float], x_min: np.ndarray, x_max: np.ndarray, function: Objective
    ) -> "RealIndividual":
        """Создаёт и один раз оценивает вещественную особь."""
        point = np.asarray(x, dtype=float).copy()
        return cls(x_min, x_max, float(function(point)), IndividualType.REAL, 0, point)

    def real_x(self) -> np.ndarray:
        """Возвращает копию координат, не позволяя изменить особь снаружи."""
        return self.x.copy()

    def clone(self) -> "RealIndividual":
        """Копирует координаты и кэшированную оценку."""
        return RealIndividual(
            self.x_min, self.x_max, self.f_value, self.individual_type,
            self.epidemic_count, self.x.copy(),
        )

    def mutate(self, function: Objective, p_max: float, rng: np.random.Generator) -> None:
        """Выполняет затухающую эпидемическую мутацию всех координат."""
        self.epidemic_count += 1
        amplitude = p_max * (self.x_max - self.x_min) / self.epidemic_count
        self.x = np.clip(self.x + rng.uniform(-0.5, 0.5, self.x.size) * amplitude, self.x_min, self.x_max)
        self.f_value = float(function(self.x))

    @classmethod
    def blx_crossover(
        cls,
        first: "RealIndividual",
        second: "RealIndividual",
        alpha: float,
        function: Objective,
        rng: np.random.Generator,
    ) -> "RealIndividual":
        """Создаёт потомка BLX-alpha внутри расширенного интервала родителей."""
        lower_parent = np.minimum(first.x, second.x)
        upper_parent = np.maximum(first.x, second.x)
        interval = upper_parent - lower_parent
        lower = np.maximum(first.x_min, lower_parent - alpha * interval)
        upper = np.minimum(first.x_max, upper_parent + alpha * interval)
        return cls.create(rng.uniform(lower, upper), first.x_min, first.x_max, function)

    @classmethod
    def differential_crossover(
        cls,
        target: "RealIndividual",
        pbest: "RealIndividual",
        r1: "RealIndividual",
        r2: "RealIndividual",
        scale_factor: float,
        crossover_rate: float,
        function: Objective,
        rng: np.random.Generator,
    ) -> tuple["RealIndividual", float]:
        """Выполняет current-to-pbest/1 mutation и binomial crossover.

        Формула пробной координаты:
        ``target + F*(pbest-target) + F*(r1-r2)``. Хотя функция названа
        crossover как в C++, она объединяет мутацию DE и кроссовер.
        """
        dimension = target.x.size
        forced_dimension = int(rng.integers(dimension))
        mask = rng.random(dimension) < crossover_rate
        mask[forced_dimension] = True  # хотя бы одна координата обязана измениться
        mutant = target.x + scale_factor * (pbest.x - target.x) + scale_factor * (r1.x - r2.x)

        # C++ сначала отражает выход за границу, затем случайно чинит слишком
        # большой перелёт, который после одного отражения всё ещё недопустим.
        mutant = np.where(mutant < target.x_min, 2 * target.x_min - mutant, mutant)
        mutant = np.where(mutant > target.x_max, 2 * target.x_max - mutant, mutant)
        invalid = (mutant < target.x_min) | (mutant > target.x_max)
        if invalid.any():
            mutant[invalid] = rng.uniform(target.x_min[invalid], target.x_max[invalid])
        child_x = np.where(mask, mutant, target.x)
        return cls.create(child_x, target.x_min, target.x_max, function), float(mask.mean())


@dataclass(slots=True)
class GrayIndividual(Individual):
    """Особь с дискретными координатами, закодированными кодом Грея."""

    genes: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.int64))
    code: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=object))

    @classmethod
    def from_decimal(
        cls,
        decimal: Sequence[int],
        x_min: np.ndarray,
        x_max: np.ndarray,
        genes: np.ndarray,
        function: Objective,
    ) -> "GrayIndividual":
        """Создаёт Gray-особь из целых позиций координатной сетки."""
        maximum = np.array([(1 << int(bits)) - 1 for bits in genes], dtype=object)
        bounded = [min(max(int(value), 0), int(limit)) for value, limit in zip(decimal, maximum)]
        code = np.array([to_gray_code(value) for value in bounded], dtype=object)
        temporary = cls(x_min, x_max, inf, IndividualType.GRAY, 0, genes.copy(), code)
        temporary.f_value = float(function(temporary.real_x()))
        return temporary

    @classmethod
    def from_real(
        cls,
        x: Sequence[float],
        x_min: np.ndarray,
        x_max: np.ndarray,
        genes: np.ndarray,
        function: Objective,
    ) -> "GrayIndividual":
        """Квантует вещественную точку на Gray-сетку."""
        point = np.asarray(x, dtype=float)
        span = x_max - x_min
        normalized = np.divide(point - x_min, span, out=np.zeros_like(point), where=span > 0)
        maximum = np.array([(1 << int(bits)) - 1 for bits in genes], dtype=object)
        decimal = [round(float(np.clip(value, 0.0, 1.0)) * int(limit)) for value, limit in zip(normalized, maximum)]
        return cls.from_decimal(decimal, x_min, x_max, genes, function)

    def decimal_x(self) -> np.ndarray:
        """Декодирует Gray-гены в целые координаты сетки."""
        return np.array([from_gray_code(int(value)) for value in self.code], dtype=object)

    def real_x(self) -> np.ndarray:
        """Линейно отображает целую Gray-сетку в заданные границы."""
        maximum = np.array([(1 << int(bits)) - 1 for bits in self.genes], dtype=float)
        return self.x_min + (self.x_max - self.x_min) * np.asarray(self.decimal_x(), dtype=float) / maximum

    def clone(self) -> "GrayIndividual":
        """Копирует код и кэшированную оценку без нового вычисления."""
        return GrayIndividual(
            self.x_min, self.x_max, self.f_value, self.individual_type,
            self.epidemic_count, self.genes.copy(), self.code.copy(),
        )

    def mutate(self, maximum_flips: float, function: Objective, rng: np.random.Generator) -> "GrayIndividual":
        """Переворачивает случайные биты; сила мутации убывает с возрастом."""
        flips = max(0, int(np.floor(maximum_flips - self.epidemic_count)))
        child = self.clone()
        child.epidemic_count += 1
        if flips == 0:
            return child
        bit_string = "".join(f"{int(code):0{int(bits)}b}" for code, bits in zip(self.code, self.genes))
        bits = np.fromiter((int(bit) for bit in bit_string), dtype=np.int8)
        for position in rng.choice(bits.size, size=min(flips, bits.size), replace=False):
            bits[position] ^= 1
        offset = 0
        new_code: list[int] = []
        for width in self.genes:
            part = bits[offset : offset + int(width)]
            new_code.append(int("".join(map(str, part.tolist())), 2))
            offset += int(width)
        child.code = np.array(new_code, dtype=object)
        child.f_value = float(function(child.real_x()))
        return child

    @classmethod
    def crossover(
        cls,
        first: "GrayIndividual",
        second: "GrayIndividual",
        uniform: bool,
        function: Objective,
        rng: np.random.Generator,
    ) -> tuple["GrayIndividual", "GrayIndividual"]:
        """Выполняет равномерный или двухточечный кроссовер Gray-битов."""
        widths = first.genes
        first_bits = np.concatenate([
            np.array(list(map(int, f"{int(code):0{int(width)}b}")))
            for code, width in zip(first.code, widths)
        ])
        second_bits = np.concatenate([
            np.array(list(map(int, f"{int(code):0{int(width)}b}")))
            for code, width in zip(second.code, widths)
        ])
        if uniform:
            mask = rng.random(first_bits.size) < 0.5
        elif first_bits.size <= 2:
            mask = np.zeros(first_bits.size, dtype=bool)
        else:
            left, right = sorted(rng.choice(np.arange(1, first_bits.size - 1), 2, replace=False))
            mask = np.zeros(first_bits.size, dtype=bool)
            mask[left:right] = True
        child_bits = (np.where(mask, second_bits, first_bits), np.where(mask, first_bits, second_bits))

        def build(bits: np.ndarray) -> GrayIndividual:
            offset = 0
            codes = []
            for width in widths:
                part = bits[offset : offset + int(width)]
                codes.append(int("".join(map(str, part.tolist())), 2))
                offset += int(width)
            child = cls(first.x_min, first.x_max, inf, IndividualType.GRAY, 0, widths.copy(), np.array(codes, dtype=object))
            child.f_value = float(function(child.real_x()))
            return child

        return build(child_bits[0]), build(child_bits[1])


@dataclass(slots=True)
class ICOConfig:
    """Все численные параметры ICO/DE; значения повторяют C++ ``Params``."""

    x_min: Sequence[float]
    x_max: Sequence[float]
    genes: Sequence[int] | None = None
    p_min: float = 0.1
    p_max: float = 0.5
    countries_count: int = 10
    country_population: int = 20
    reproduction_min: int = 1
    reproduction_max: int = 5
    extinction_min: int = 1
    extinction_max: int = 3
    trade_count: int = 3
    war_count: int = 3
    epidemic_elite_fraction: float = 0.2
    epidemic_dead_fraction: float = 0.3
    maximum_gray_mutation: int = 3
    maximum_iterations: int = 1000
    gray_country_fraction: float = 0.5
    parent_rank_pressure: float = 3.0
    de_f: float = 0.55
    de_cr: float = 0.90
    de_pbest_fraction: float = 0.20
    de_pool_fraction: float = 0.60
    de_pool_fraction_end: float = 0.40
    de_exploitation_start_fraction: float = 0.18
    de_exploitation_share_start: float = 0.45
    de_exploitation_share_end: float = 0.85
    de_adaptive: bool = True
    de_memory_size: int = 5
    de_f_sigma: float = 0.10
    de_cr_sigma: float = 0.05
    population_reduction: bool = True
    minimum_country_size: int = 4
    minimum_countries: int = 2
    adaptive_reproduction_operators: bool = True
    operator_learning_rate: float = 0.10
    operator_minimum_probability: float = 0.05
    stagnation_limit: int = 25
    restart_country_fraction: float = 0.15
    migration_fraction: float = 0.30
    ico_actions_start_probability: float = 0.0
    motion_probability: float = 0.25
    trade_probability: float = 0.20
    war_probability: float = 0.20
    epidemic_probability: float = 0.20
    migration_probability: float = 0.15
    initial_x: Sequence[float] | None = None
    target_f: float | None = None
    printing: bool = False
    random_seed: int | None = None

    def __post_init__(self) -> None:
        """Проверяет размерности, границы и параметры популяции."""
        if len(self.x_min) == 0 or len(self.x_min) != len(self.x_max):
            raise ValueError("x_min и x_max должны иметь одинаковую ненулевую размерность")
        if any(low >= high for low, high in zip(self.x_min, self.x_max)):
            raise ValueError("Каждая нижняя граница должна быть меньше верхней")
        if self.genes is not None and len(self.genes) != len(self.x_min):
            raise ValueError("genes должен содержать число бит для каждой координаты")
        if self.countries_count <= 0 or self.country_population < 2:
            raise ValueError("Нужна хотя бы одна страна и две особи в стране")
        if self.maximum_iterations <= 0 or self.de_memory_size <= 0:
            raise ValueError("Лимиты итераций и памяти DE должны быть положительными")
        if self.initial_x is not None and len(self.initial_x) != len(self.x_min):
            raise ValueError("initial_x имеет неверную размерность")
        action_probability_sum = sum((
            self.motion_probability,
            self.trade_probability,
            self.war_probability,
            self.epidemic_probability,
            self.migration_probability,
        ))
        if action_probability_sum <= 0:
            raise ValueError("Сумма вероятностей действий стран должна быть положительной")


@dataclass(frozen=True, slots=True)
class ICOResult:
    """Лучшее найденное решение и фактическая стоимость поиска."""

    x: np.ndarray
    objective: float
    iterations: int
    function_evaluations: int


class _ObjectiveCounter:
    """Считает обращения к пользовательской objective-функции."""

    def __init__(self, function: Objective) -> None:
        self.function = function
        self.calls = 0

    def __call__(self, x: np.ndarray) -> float:
        self.calls += 1
        return float(self.function(x))


class Country:
    """Остров популяции с общей кодировкой и собственной памятью DE."""

    def __init__(
        self,
        size: int,
        x_min: np.ndarray,
        x_max: np.ndarray,
        function: Objective,
        individual_type: IndividualType,
        genes: np.ndarray,
        config: ICOConfig,
        rng: np.random.Generator,
    ) -> None:
        """Создаёт локальную популяцию в случайном поддиапазоне пространства."""
        self.x_min, self.x_max = x_min, x_max
        self.function, self.individual_type = function, individual_type
        self.genes, self.config, self.rng = genes, config, rng
        self.action = -1
        self.ally: Country | None = None
        self.enemy: Country | None = None
        self.de_memory_f = np.full(config.de_memory_size, config.de_f)
        self.de_memory_cr = np.full(config.de_memory_size, config.de_cr)
        self.de_memory_index = 0
        self.population: list[Individual] = []
        if individual_type is IndividualType.REAL:
            local_min = rng.uniform(x_min, x_max)
            local_max = rng.uniform(local_min, x_max)
            self.population = [RealIndividual.create(rng.uniform(local_min, local_max), x_min, x_max, function) for _ in range(size)]
        else:
            maximum = np.array([(1 << int(bits)) - 1 for bits in genes], dtype=np.int64)
            local_min = np.array([rng.integers(0, maximum[i]) for i in range(len(genes))])
            local_max = np.array([rng.integers(local_min[i] + 1, maximum[i] + 1) for i in range(len(genes))])
            self.population = [GrayIndividual.from_decimal(
                [rng.integers(local_min[i], local_max[i] + 1) for i in range(len(genes))],
                x_min, x_max, genes, function,
            ) for _ in range(size)]
        self.sort_population()

    def sort_population(self) -> None:
        """Размещает лучшую особь первой."""
        self.population.sort(key=lambda individual: individual.f_value)

    @property
    def best_f(self) -> float:
        """Возвращает лучшую оценку страны."""
        return self.population[0].f_value if self.population else inf

    @property
    def average_f(self) -> float:
        """Возвращает среднюю оценку жителей страны."""
        return float(np.mean([individual.f_value for individual in self.population])) if self.population else inf

    def random_individual(self) -> Individual:
        """Создаёт случайного жителя во всём допустимом пространстве."""
        if self.individual_type is IndividualType.REAL:
            return RealIndividual.create(self.rng.uniform(self.x_min, self.x_max), self.x_min, self.x_max, self.function)
        maximum = [(1 << int(bits)) - 1 for bits in self.genes]
        return GrayIndividual.from_decimal(
            [self.rng.integers(limit + 1) for limit in maximum], self.x_min, self.x_max,
            self.genes, self.function,
        )

    def select_rank_biased_parent(self, count: int, exclude: int | None = None) -> int:
        """Выбирает родителя с экспоненциальным предпочтением лучших рангов."""
        weights = np.exp(-self.config.parent_rank_pressure * np.arange(count) / max(1, count - 1))
        if exclude is not None:
            weights[exclude] = 0.0
        weights /= weights.sum()
        return int(self.rng.choice(count, p=weights))

    def reproduce(
        self,
        f_min: float,
        f_max: float,
        iteration: int,
        de_share: float,
        de_pool_fraction: float,
        operator_adaptation: AdaptiveOperatorPair,
    ) -> None:
        """Добавляет потомков BLX/DE или двух Gray-кроссоверов."""
        parent_count = len(self.population)
        if parent_count < 2:
            return
        fraction = (f_max - self.average_f) / (f_max - f_min + 1e-15)
        children_pairs = int(np.clip(ceil(
            (self.config.reproduction_max - self.config.reproduction_min) * fraction
            + self.config.reproduction_min
        ), self.config.reproduction_min, self.config.reproduction_max))

        elite_count = max(1, min(parent_count, ceil(0.2 * parent_count)))
        elite_threshold = self.population[elite_count - 1].f_value
        if self.individual_type is IndividualType.GRAY:
            for _ in range(children_pairs):
                first_index = self.select_rank_biased_parent(parent_count)
                second_index = self.select_rank_biased_parent(parent_count, first_index)
                operator = int(self.rng.choice(2, p=operator_adaptation.probabilities))
                children = GrayIndividual.crossover(
                    self.population[first_index], self.population[second_index], operator == 0,
                    self.function, self.rng,
                )
                for child in children:
                    operator_adaptation.update(operator, normalized_elite_credit(elite_threshold, child.f_value), self.config.operator_learning_rate)
                    self.population.append(child)
            self.sort_population()
            return

        # Вещественная ветка повторяет активную C++ смесь BLX и DE.
        alpha = float(np.clip(
            self.config.p_max - (self.config.p_max - self.config.p_min)
            * (1.0 - iteration / self.config.maximum_iterations)
            * ((self.average_f - f_min) / (f_max - f_min + 1e-15)),
            self.config.p_min, self.config.p_max,
        ))
        pool_count = int(np.clip(ceil(de_pool_fraction * parent_count), min(4, parent_count), parent_count))
        pbest_count = int(np.clip(ceil(self.config.de_pbest_fraction * pool_count), min(2, pool_count), pool_count))
        de_elite_threshold = self.population[pbest_count - 1].f_value
        successful: list[tuple[float, float, float]] = []

        for _ in range(2 * children_pairs):
            use_de = self.rng.random() >= 1.0 - de_share and parent_count >= 4
            if use_de:
                target_index = int(self.rng.integers(pool_count))
                candidates = [i for i in range(pbest_count) if i != target_index]
                pbest_index = int(self.rng.choice(candidates)) if candidates else (target_index + 1) % pool_count
                r1_index = self.select_rank_biased_parent(pool_count, target_index)
                while r1_index == pbest_index:
                    r1_index = self.select_rank_biased_parent(pool_count, target_index)
                candidates = [i for i in range(parent_count) if i not in {target_index, pbest_index, r1_index}]
                r2_index = int(self.rng.choice(candidates))
                memory_slot = int(self.rng.integers(self.config.de_memory_size))
                scale_factor = self.config.de_f
                crossover_rate = self.config.de_cr
                if self.config.de_adaptive:
                    scale_factor = -1.0
                    while scale_factor <= 0.0:
                        scale_factor = self.de_memory_f[memory_slot] + self.config.de_f_sigma * self.rng.standard_cauchy()
                    scale_factor = min(scale_factor, 1.0)
                    crossover_rate = float(np.clip(
                        self.rng.normal(self.de_memory_cr[memory_slot], self.config.de_cr_sigma), 0.0, 1.0
                    ))
                target = self.population[target_index]
                child, actual_cr = RealIndividual.differential_crossover(
                    target, self.population[pbest_index], self.population[r1_index], self.population[r2_index],
                    scale_factor, crossover_rate, self.function, self.rng,
                )
                improvement = target.f_value - child.f_value
                if improvement > 0.0 and child.f_value <= de_elite_threshold:
                    scale = abs(target.f_value) + abs(child.f_value) + 1.0
                    successful.append((scale_factor, actual_cr, improvement / scale))
                operator_adaptation.update(1, normalized_elite_credit(de_elite_threshold, child.f_value), self.config.operator_learning_rate)
            else:
                first_index = self.select_rank_biased_parent(parent_count)
                second_index = self.select_rank_biased_parent(parent_count, first_index)
                child = RealIndividual.blx_crossover(
                    self.population[first_index], self.population[second_index], alpha, self.function, self.rng,
                )
                operator_adaptation.update(0, normalized_elite_credit(de_elite_threshold, child.f_value), self.config.operator_learning_rate)
            self.population.append(child)

        # SHADE-подобная память учит F и CR только на успешных элитных потомках.
        if self.config.de_adaptive and successful:
            values = np.asarray(successful)
            weights = values[:, 2] / values[:, 2].sum() if values[:, 2].sum() > 1e-30 else np.full(len(values), 1 / len(values))
            f_denominator = np.sum(weights * values[:, 0])
            if f_denominator > 1e-30:
                self.de_memory_f[self.de_memory_index] = np.clip(np.sum(weights * values[:, 0] ** 2) / f_denominator, 0.0, 1.0)
            cr_denominator = np.sum(weights * values[:, 1])
            if cr_denominator > 1e-30:
                lehmer_cr = np.clip(np.sum(weights * values[:, 1] ** 2) / cr_denominator, 0.0, 1.0)
                self.de_memory_cr[self.de_memory_index] = 0.5 * (self.de_memory_cr[self.de_memory_index] + lehmer_cr)
            self.de_memory_index = (self.de_memory_index + 1) % self.config.de_memory_size
        self.sort_population()

    def extinct(self, f_min: float, f_max: float, minimum_survivors: int) -> None:
        """Удаляет худших жителей; слабые страны теряют больше особей."""
        remove_count = int(np.clip(
            (self.config.extinction_max - self.config.extinction_min)
            * ((self.average_f - f_min) / (f_max - f_min + 1e-15))
            + self.config.extinction_min,
            self.config.extinction_min, self.config.extinction_max,
        ))
        remove_count = min(remove_count, max(0, len(self.population) - minimum_survivors))
        if remove_count:
            del self.population[-remove_count:]

    def migrate(self) -> None:
        """Заменяет худшую долю случайными особями, сохраняя лидера."""
        count = min(max(1, ceil(self.config.migration_fraction * len(self.population))), len(self.population) - 1)
        del self.population[-count:]
        self.population.extend(self.random_individual() for _ in range(count))
        self.sort_population()

    def move_to_leader(self, radius: float) -> None:
        """Сдвигает всех жителей, кроме лидера, в сторону лучшей особи."""
        if len(self.population) < 2:
            return
        leader = self.population[0].real_x()
        moved: list[Individual] = [self.population[0]]
        for individual in self.population[1:]:
            point = individual.real_x()
            point = np.clip(
                point + self.rng.uniform(0.0, radius) * (leader - point),
                self.x_min,
                self.x_max,
            )
            if self.individual_type is IndividualType.REAL:
                moved.append(RealIndividual.create(point, self.x_min, self.x_max, self.function))
            else:
                moved.append(GrayIndividual.from_real(point, self.x_min, self.x_max, self.genes, self.function))
        self.population = moved
        self.sort_population()

    def epidemic(self, gray_mutation_strength: float) -> None:
        """Защищает элиту, удаляет худших и мутирует оставшихся жителей."""
        size = len(self.population)
        elite_count = ceil(self.config.epidemic_elite_fraction * size)
        dead_count = ceil(self.config.epidemic_dead_fraction * size)
        if dead_count >= size:
            self.population.clear()
            return
        if dead_count:
            del self.population[-dead_count:]
        for index in range(elite_count, len(self.population)):
            individual = self.population[index]
            if self.individual_type is IndividualType.REAL:
                individual.mutate(self.function, self.config.p_max, self.rng)
            else:
                self.population[index] = individual.mutate(
                    gray_mutation_strength, self.function, self.rng
                )
        self.sort_population()


class CountriesAlgorithm:
    """Островной ICO с адаптивной DE и ограничением числа вычислений."""

    def __init__(self, function: Objective, config: ICOConfig) -> None:
        """Нормализует настройки, создаёт RNG и начальные страны."""
        self.config = config
        self.rng = np.random.default_rng(config.random_seed)
        self.function = _ObjectiveCounter(function)
        self.x_min = np.asarray(config.x_min, dtype=float)
        self.x_max = np.asarray(config.x_max, dtype=float)
        self.genes = np.asarray(config.genes or [32] * len(self.x_min), dtype=np.int64)
        self.real_operators = AdaptiveOperatorPair()
        self.gray_operators = AdaptiveOperatorPair()
        self.countries: list[Country] = []
        gray_count = round(config.gray_country_fraction * config.countries_count)
        for index in range(config.countries_count):
            kind = IndividualType.GRAY if index < gray_count else IndividualType.REAL
            self.countries.append(Country(
                config.country_population, self.x_min, self.x_max, self.function,
                kind, self.genes, config, self.rng,
            ))
        if config.initial_x is not None:
            self._insert_initial_solution(config.initial_x)

    def _insert_initial_solution(self, initial_x: Sequence[float]) -> None:
        """Заменяет худшую случайную особь переданным начальным решением."""
        point = np.clip(np.asarray(initial_x, dtype=float), self.x_min, self.x_max)
        target = next((country for country in self.countries if country.individual_type is IndividualType.REAL), self.countries[0])
        individual: Individual
        if target.individual_type is IndividualType.REAL:
            individual = RealIndividual.create(point, self.x_min, self.x_max, self.function)
        else:
            individual = GrayIndividual.from_real(point, self.x_min, self.x_max, self.genes, self.function)
        target.population[-1] = individual
        target.sort_population()

    def _restart_weak_countries(self) -> None:
        """Пересоздаёт худшие страны после длительного застоя."""
        if len(self.countries) <= 1:
            return
        self.countries.sort(key=lambda country: country.best_f)
        count = int(np.clip(ceil(self.config.restart_country_fraction * len(self.countries)), 1, len(self.countries) - 1))
        for country in self.countries[-count:]:
            target_size = max(len(country.population), self.config.country_population)
            country.population = [country.random_individual() for _ in range(target_size)]
            country.sort_population()

    def _trade(self, first: Country, second: Country) -> None:
        """Обменивает случайных жителей и переводит их в кодировку получателя."""
        count = self.config.trade_count
        if len(first.population) <= count or len(second.population) <= count:
            count = min(len(first.population), len(second.population)) // 2
        if count <= 0:
            return
        first_indices = sorted(self.rng.choice(len(first.population), count, replace=False), reverse=True)
        second_indices = sorted(self.rng.choice(len(second.population), count, replace=False), reverse=True)
        first_group = [first.population.pop(int(index)) for index in first_indices]
        second_group = [second.population.pop(int(index)) for index in second_indices]
        first.population.extend(self._convert(individual, first) for individual in second_group)
        second.population.extend(self._convert(individual, second) for individual in first_group)
        first.sort_population()
        second.sort_population()

    def _war(self, first: Country, second: Country) -> None:
        """Проводит попарные дуэли; победившая страна ассимилирует выживших."""
        count = min(self.config.war_count, len(first.population), len(second.population))
        if count <= 0:
            return
        first_indices = sorted(self.rng.choice(len(first.population), count, replace=False), reverse=True)
        second_indices = sorted(self.rng.choice(len(second.population), count, replace=False), reverse=True)
        first_group = [first.population.pop(int(index)) for index in first_indices]
        second_group = [second.population.pop(int(index)) for index in second_indices]
        first_wins = sum(a.f_value < b.f_value for a, b in zip(first_group, second_group))
        second_wins = sum(b.f_value < a.f_value for a, b in zip(first_group, second_group))
        if first_wins > second_wins:
            first.population.extend(self._convert(item, first) for item in first_group + second_group)
        elif second_wins > first_wins:
            second.population.extend(self._convert(item, second) for item in first_group + second_group)
        else:
            first.population.extend(self._convert(item, first) for item in first_group)
            second.population.extend(self._convert(item, second) for item in second_group)
        # Если одна сторона потеряла всех участников, добавляем нового жителя,
        # чтобы остров не исчез только из-за одной военной операции.
        if not first.population:
            first.population.append(first.random_individual())
        if not second.population:
            second.population.append(second.random_individual())
        first.sort_population()
        second.sort_population()

    def _apply_country_actions(self, progress: float) -> None:
        """Выполняет Motion/Trade/War/Epidemic/Migration ранней фазы ICO.

        В исходном C++ вероятность входа в эту ветку равна нулю. Метод нужен,
        чтобы исследователь мог вернуть ICO-действия одним параметром, не
        вмешиваясь в рабочую DE-ветку.
        """
        threshold = self.config.ico_actions_start_probability * (1.0 - progress)
        if progress >= 0.18 or self.rng.random() >= threshold:
            return
        probabilities = np.asarray([
            self.config.motion_probability,
            self.config.trade_probability,
            self.config.war_probability,
            self.config.epidemic_probability,
            self.config.migration_probability,
        ], dtype=float)
        probabilities /= probabilities.sum()
        available = set(range(len(self.countries)))
        radius = 2.0 - 0.8 * progress**0.6
        gray_strength = (1.0 - progress) * self.config.maximum_gray_mutation
        while available:
            index = min(available)
            available.remove(index)
            country = self.countries[index]
            action = int(self.rng.choice(5, p=probabilities))
            if action == 0:
                country.move_to_leader(radius)
            elif action in (1, 2) and available:
                partner_index = int(self.rng.choice(tuple(available)))
                available.remove(partner_index)
                partner = self.countries[partner_index]
                if action == 1:
                    self._trade(country, partner)
                else:
                    self._war(country, partner)
            elif action == 3:
                country.epidemic(gray_strength)
            elif action == 4:
                country.migrate()

    def _reduce_population(self, progress: float) -> None:
        """Линейно сокращает число стран и максимальный размер острова."""
        if not self.config.population_reduction:
            return
        target_countries = round(
            self.config.countries_count
            + (self.config.minimum_countries - self.config.countries_count) * progress
        )
        target_countries = int(np.clip(target_countries, self.config.minimum_countries, self.config.countries_count))
        self.countries.sort(key=lambda country: country.best_f)
        self.countries = self.countries[:target_countries]
        size_limit = max(self.config.minimum_country_size, round(
            self.config.country_population
            + (self.config.minimum_country_size - self.config.country_population) * progress
        ))
        for country in self.countries:
            country.population = country.population[:size_limit]

    def start(
        self,
        canonical_x: Sequence[float] | None = None,
        epsilon: float = 0.0,
        y_epsilon: float | None = None,
        max_calls: int | None = None,
    ) -> ICOResult:
        """Ищет минимум до лимита итераций, FE или известного target_f.

        ``canonical_x`` и ``epsilon`` сохранены для совместимости с C++/старым
        Python API. Как и C++ для CEC2017, координаты известного оптимума не
        используются; ранняя остановка проверяет objective через ``target_f``.
        """
        del canonical_x, epsilon
        best_country = min(self.countries, key=lambda country: country.best_f)
        best = best_country.population[0].clone()
        stagnant_iterations = 0
        iteration = 0

        for iteration in range(1, self.config.maximum_iterations + 1):
            if max_calls is not None and self.function.calls >= max_calls:
                break
            progress = (
                min(1.0, self.function.calls / max_calls)
                if max_calls else (iteration - 1) / max(1, self.config.maximum_iterations - 1)
            )
            self._apply_country_actions(progress)
            self.countries = [country for country in self.countries if country.population]
            if not self.countries:
                break
            self.countries.sort(key=lambda country: country.average_f)
            f_min, f_max = self.countries[0].average_f, self.countries[-1].average_f
            if f_min == f_max and len(self.countries) > 1:
                self._restart_weak_countries()
                self.countries.sort(key=lambda country: country.average_f)
                f_min, f_max = self.countries[0].average_f, self.countries[-1].average_f

            if progress >= self.config.de_exploitation_start_fraction:
                phase = (progress - self.config.de_exploitation_start_fraction) / max(1e-15, 1 - self.config.de_exploitation_start_fraction)
                de_floor = self.config.de_exploitation_share_start + phase * (
                    self.config.de_exploitation_share_end - self.config.de_exploitation_share_start
                )
                de_pool = self.config.de_pool_fraction + phase * (
                    self.config.de_pool_fraction_end - self.config.de_pool_fraction
                )
            else:
                de_floor, de_pool = self.config.operator_minimum_probability, self.config.de_pool_fraction

            if self.config.adaptive_reproduction_operators:
                self.real_operators.renormalize(self.config.operator_minimum_probability, de_floor)
                self.gray_operators.renormalize(
                    self.config.operator_minimum_probability, self.config.operator_minimum_probability
                )
            de_share = float(self.real_operators.probabilities[1])
            schedule_iteration = min(
                self.config.maximum_iterations,
                1 + round(progress * max(0, self.config.maximum_iterations - 1)),
            )
            isolated: list[Individual] = []
            for country in self.countries:
                if len(country.population) <= 1:
                    isolated.extend(country.population)
                    continue
                adaptation = self.gray_operators if country.individual_type is IndividualType.GRAY else self.real_operators
                country.reproduce(f_min, f_max, schedule_iteration, de_share, de_pool, adaptation)
                country.extinct(
                    f_min, f_max,
                    self.config.minimum_country_size if self.config.population_reduction else 0,
                )
            self.countries = [country for country in self.countries if country.population]
            for individual in isolated:
                country = self.countries[int(self.rng.integers(len(self.countries)))]
                country.population.append(self._convert(individual, country))
                country.sort_population()
            self._reduce_population(progress)

            current_country = min(self.countries, key=lambda country: country.best_f)
            current = current_country.population[0]
            if current.f_value < best.f_value:
                best = current.clone()
                stagnant_iterations = 0
            else:
                stagnant_iterations += 1
            if stagnant_iterations >= self.config.stagnation_limit:
                self._restart_weak_countries()
                stagnant_iterations = 0
            if self.config.printing and iteration % 50 == 0:
                print(f"Итерация: {iteration}, objective: {best.f_value}, вычислений: {self.function.calls}")
            if (
                self.config.target_f is not None
                and y_epsilon is not None
                and abs(best.f_value - self.config.target_f) <= y_epsilon
            ):
                break
        return ICOResult(best.real_x(), best.f_value, iteration, self.function.calls)

    def _convert(self, individual: Individual, country: Country) -> Individual:
        """Переводит мигранта в кодировку принимающей страны без новой оценки."""
        if individual.individual_type is country.individual_type:
            return individual.clone()
        if country.individual_type is IndividualType.REAL:
            return RealIndividual(
                country.x_min, country.x_max, individual.f_value, IndividualType.REAL,
                individual.epidemic_count, individual.real_x(),
            )
        converted = GrayIndividual.from_real(
            individual.real_x(), country.x_min, country.x_max, country.genes,
            lambda _: individual.f_value,
        )
        converted.epidemic_count = individual.epidemic_count
        return converted


__all__ = [
    "CountriesAlgorithm",
    "Country",
    "GrayIndividual",
    "ICOConfig",
    "ICOResult",
    "Individual",
    "IndividualType",
    "RealIndividual",
    "from_gray_code",
    "to_gray_code",
]
