"""PyInstaller entry point.

``undatum/__main__.py`` uses package-relative imports, so it cannot be the
frozen script itself; this wrapper imports it as part of the package.
"""

from undatum.__main__ import main

if __name__ == "__main__":
    main()
