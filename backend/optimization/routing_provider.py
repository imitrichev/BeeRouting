"""Интерфейс внешнего источника матрицы времени движения."""

from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol, runtime_checkable


@runtime_checkable
class RoutingProvider(Protocol):
    """Контракт получения готовых матриц времени и расстояния."""

    def get_travel_time_matrix(
        self,
        location_ids: Iterable[str],
    ) -> Mapping[str, Mapping[str, int]]:
        """Возвращает travel-time matrix для переданных локаций."""

    def get_distance_matrix(
        self,
        location_ids: Iterable[str],
    ) -> Mapping[str, Mapping[str, float]]:
        """Возвращает distance matrix в километрах для переданных локаций."""


@dataclass(frozen=True, slots=True)
class InMemoryRoutingProvider:
    """Детерминированный provider с двумя заранее заданными матрицами."""

    travel_time_matrix: Mapping[str, Mapping[str, int]]
    distance_matrix: Mapping[str, Mapping[str, float]]

    def get_travel_time_matrix(
        self,
        location_ids: Iterable[str],
    ) -> Mapping[str, Mapping[str, int]]:
        """Возвращает копию подматрицы и проверяет наличие всех локаций."""
        requested_locations = tuple(dict.fromkeys(location_ids))
        matrix = {
            from_location: dict(to_locations)
            for from_location, to_locations in self.travel_time_matrix.items()
        }
        missing_origins = set(requested_locations) - matrix.keys()
        if missing_origins:
            raise ValueError(
                f"В routing provider отсутствуют исходные локации: "
                f"{sorted(missing_origins)}"
            )
        for from_location in requested_locations:
            missing_destinations = set(requested_locations) - matrix[
                from_location
            ].keys()
            if missing_destinations:
                raise ValueError(
                    f"В routing provider отсутствуют назначения из "
                    f"{from_location}: {sorted(missing_destinations)}"
                )
        return {
            from_location: {
                to_location: matrix[from_location][to_location]
                for to_location in requested_locations
            }
            for from_location in requested_locations
        }

    def get_distance_matrix(
        self,
        location_ids: Iterable[str],
    ) -> Mapping[str, Mapping[str, float]]:
        """Возвращает копию подматрицы расстояний в километрах."""
        requested_locations = tuple(dict.fromkeys(location_ids))
        matrix = {
            from_location: dict(to_locations)
            for from_location, to_locations in self.distance_matrix.items()
        }
        missing_origins = set(requested_locations) - matrix.keys()
        if missing_origins:
            raise ValueError(
                f"В routing provider отсутствуют исходные локации: "
                f"{sorted(missing_origins)}"
            )
        for from_location in requested_locations:
            missing_destinations = set(requested_locations) - matrix[
                from_location
            ].keys()
            if missing_destinations:
                raise ValueError(
                    f"В routing provider отсутствуют назначения из "
                    f"{from_location}: {sorted(missing_destinations)}"
                )
        return {
            from_location: {
                to_location: matrix[from_location][to_location]
                for to_location in requested_locations
            }
            for from_location in requested_locations
        }
