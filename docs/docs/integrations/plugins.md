---
title: "Plugins"
description: "Extend undatum with commands, connectors, and transforms"
---
# Plugins

Add domain-specific commands, connectors, or transforms without maintaining a fork. Plugins are Python packages that export an `undatum.plugins` entry point. The callable must return a `Plugin` instance (typically `register(undatum_app=None)`).

```toml
[project.entry-points."undatum.plugins"]
my-plugin = "mypackage.plugin:register"
```

```bash norun
undatum plugins list
undatum plugins info my-plugin
undatum plugins validate
```

Base classes live in `undatum.plugins.base`: `CommandPlugin`, `ConnectorPlugin`, `TransformPlugin`. Worked examples: [examples/plugins](https://github.com/datenoio/undatum/tree/master/examples/plugins). CLI surface: [`plugins`](/commands/plugins).

## Command plugin

Register extra Typer commands on the main app:

```python
from undatum.plugins.base import CommandPlugin, Plugin
import typer

def register(undatum_app=None) -> Plugin:
    return HelloPlugin()

class HelloPlugin(CommandPlugin):
    def __init__(self):
        super().__init__("hello", "1.0.0", "Print a greeting")

    def register_commands(self, app):
        @app.command()
        def hello(name: str = "world"):
            """Greet someone."""
            typer.echo(f"hello {name}")
```

## Transform plugin

Implement `transform(record) -> dict` and apply it with `undatum apply --plugin <name>`:

```python
from typing import Any
from undatum.plugins.base import Plugin, TransformPlugin

def register(undatum_app=None) -> Plugin:
    return UpperPlugin()

class UpperPlugin(TransformPlugin):
    def __init__(self):
        super().__init__("example-transform", "1.0.0", "Uppercase strings")

    def register_transforms(self, registry: Any) -> None:
        registry.register(self)

    def transform(self, record: dict[str, Any], **kwargs) -> dict[str, Any]:
        return {k: v.upper() if isinstance(v, str) else v for k, v in record.items()}
```

```bash norun
undatum apply data.jsonl --plugin example-transform --output out.jsonl
```

## Connector plugin

Handle custom URI schemes on the iterable I/O path (`can_handle` + `open`). Cloud `s3://` / `gs://` / `az://` URIs are built-in; connectors are consulted for other schemes.

```python
from undatum.plugins.base import ConnectorPlugin, Plugin

class DemoConnector(ConnectorPlugin):
    def can_handle(self, uri: str) -> bool:
        return isinstance(uri, str) and uri.startswith("demo://")

    def open(self, uri: str, mode: str = "r", **kwargs):
        path = uri[len("demo://") :]
        return open(path, "rb" if "b" in mode or mode.startswith("r") else mode)

    def register_connectors(self, registry) -> None:
        registry.register(self)
```

See `examples/plugins/example_connector_plugin.py`.
