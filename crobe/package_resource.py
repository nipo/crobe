"""Access to data files shipped inside crobe packages.

This replaces the deprecated ``pkg_resources`` API with
``importlib.resources`` (standard library since Python 3.9) so that
resource lookup keeps working when crobe is installed as a wheel, a
zip, or an egg.
"""

import importlib.resources
from contextlib import contextmanager


class PackageResource:
    """A data file bundled inside a Python package.

    The file is addressed by its *anchor* package (usually the
    ``__package__`` of the calling module) and a path relative to it.

    Because the package may be installed as a non-extracted archive
    (zip/egg), the on-disk location is only materialised on demand
    through :meth:`path`, which yields a real filesystem path for the
    duration of a ``with`` block.
    """

    def __init__(self, anchor, relative_path):
        self._traversable = importlib.resources.files(anchor) / relative_path

    def exists(self):
        """Whether the resource is present as a readable file."""
        return self._traversable.is_file()

    @contextmanager
    def path(self):
        """Yield a real filesystem path to the resource.

        For archived packages the resource is extracted to a temporary
        file that is kept alive only for the duration of the context.
        The temporary file keeps the original name as suffix, so
        extension-based format detection still works.
        """
        with importlib.resources.as_file(self._traversable) as path:
            yield path
