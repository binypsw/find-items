import importlib
import inspect
import pkgutil
from pathlib import Path

from shared.scraper.base import AbstractScraper

_registry: dict[str, type[AbstractScraper]] = {}


def _discover() -> None:
    plugins_path = Path(__file__).parent
    for _, module_name, _ in pkgutil.walk_packages([str(plugins_path)], prefix=__name__ + "."):
        module = importlib.import_module(module_name)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, AbstractScraper) and obj is not AbstractScraper and hasattr(obj, "source_id"):
                _registry[obj.source_id] = obj


def get_plugin(source_id: str) -> type[AbstractScraper] | None:
    if not _registry:
        _discover()
    return _registry.get(source_id)


def get_all_plugins() -> dict[str, type[AbstractScraper]]:
    if not _registry:
        _discover()
    return dict(_registry)
