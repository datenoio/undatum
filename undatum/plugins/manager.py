"""Plugin manager for discovering and loading plugins."""

import logging
from typing import Any

try:
    from importlib.metadata import entry_points
except ImportError:
    # Python < 3.8
    try:
        from importlib_metadata import entry_points
    except ImportError:
        # Fallback for very old Python
        def entry_points(**kwargs):
            return []


from .base import Plugin
from .registry import PluginRegistry

logger = logging.getLogger(__name__)


class PluginManager:
    """Manages plugin discovery, loading, and registration."""

    def __init__(self):
        self.registry = PluginRegistry()
        self._loaded_plugins: dict[str, Plugin] = {}

    def discover_plugins(self) -> list[str]:
        """Discover plugins from installed packages.

        Returns:
            List of plugin entry point names
        """
        plugin_names = []
        try:
            # Discover plugins via entry points
            eps = entry_points(group="undatum.plugins")
            for ep in eps:
                plugin_names.append(ep.name)
                logger.debug(f"Discovered plugin entry point: {ep.name} from {ep.module}")
        except Exception as e:
            logger.warning(f"Error discovering plugins: {e}")

        return plugin_names

    def load_plugin(self, entry_point_name: str, app: Any | None = None) -> Plugin | None:
        """Load a plugin from entry point.

        Args:
            entry_point_name: Entry point name
            app: Undatum app instance (optional)

        Returns:
            Plugin instance or None if loading failed
        """
        if entry_point_name in self._loaded_plugins:
            return self._loaded_plugins[entry_point_name]

        try:
            eps = entry_points(group="undatum.plugins", name=entry_point_name)
            if not eps:
                logger.warning(f"Plugin entry point '{entry_point_name}' not found")
                return None

            ep = list(eps)[0]

            # Load plugin function
            plugin_func = ep.load()

            # Call plugin registration function
            # Plugin function should return Plugin instance or register directly
            plugin = plugin_func(app) if app else plugin_func()

            if plugin:
                if isinstance(plugin, Plugin):
                    self._loaded_plugins[entry_point_name] = plugin
                    self.registry.register(plugin)
                    if app:
                        plugin.initialize(app)
                    return plugin
                else:
                    logger.warning(f"Plugin '{entry_point_name}' did not return Plugin instance")

        except Exception as e:
            logger.error(f"Failed to load plugin '{entry_point_name}': {e}", exc_info=True)

        return None

    def load_all_plugins(self, app: Any | None = None) -> None:
        """Load all discovered plugins.

        Args:
            app: Undatum app instance (optional)
        """
        plugin_names = self.discover_plugins()
        for name in plugin_names:
            try:
                self.load_plugin(name, app)
            except Exception as e:
                logger.warning(f"Failed to load plugin '{name}': {e}")

    def get_registry(self) -> PluginRegistry:
        """Get plugin registry.

        Returns:
            Plugin registry instance
        """
        return self.registry
