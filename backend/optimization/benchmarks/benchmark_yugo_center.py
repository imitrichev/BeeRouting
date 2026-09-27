"""Сравнительный benchmark района «Югоцентр»."""

from pathlib import Path

from backend.optimization.benchmarks.benchmark_region import main


DEFAULT_JSON_PATH = Path("Югоцентр.json")
if __name__ == "__main__":
    main(DEFAULT_JSON_PATH)
