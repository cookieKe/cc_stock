import importlib
import pkgutil
from typing import Dict, Type
from backend.strategy_engine.base import BaseStrategy


class StrategyRegistry:
    """策略注册表：自动发现built_in下的策略，支持动态加载。"""

    def __init__(self):
        self._strategies: Dict[str, Type[BaseStrategy]] = {}

    def discover_builtin(self):
        import backend.strategy_engine.built_in as builtin_pkg
        package_path = builtin_pkg.__path__
        for _, mod_name, _ in pkgutil.iter_modules(package_path):
            mod = importlib.import_module(f"backend.strategy_engine.built_in.{mod_name}")
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if isinstance(attr, type) and issubclass(attr, BaseStrategy) and attr is not BaseStrategy:
                    instance = attr()
                    self.register(instance.name, attr)

    def register(self, name: str, strategy_cls: Type[BaseStrategy]):
        self._strategies[name] = strategy_cls

    def get(self, name: str) -> Type[BaseStrategy]:
        if name not in self._strategies:
            raise KeyError(f"策略 '{name}' 未注册。可用: {list(self._strategies.keys())}")
        return self._strategies[name]

    def list_strategies(self) -> Dict[str, dict]:
        return {
            name: {
                "name": cls.name,
                "display_name": cls.display_name,
                "description": cls.description,
                "parameters": cls.parameters,
            }
            for name, cls in self._strategies.items()
        }

    def __contains__(self, name: str) -> bool:
        return name in self._strategies


registry = StrategyRegistry()
registry.discover_builtin()
