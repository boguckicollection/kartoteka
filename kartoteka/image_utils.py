import logging
from typing import IO, Optional, Union
from pathlib import Path
from contextlib import ExitStack
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

Source = Union[str, Path, IO[bytes]]

def load_rgba_image(source: Source) -> Optional[Image.Image]:
    """Open ``source`` as an image and convert it to RGBA.

    Parameters
    ----------
    source:
        A filesystem path or file-like object accepted by :func:`PIL.Image.open`.

    Returns
    -------
    Optional[Image.Image]
        The loaded image in RGBA mode or ``None`` if the image cannot be
        opened or decoded.
    """
    try:
        with ExitStack() as stack:
            img = Image.open(source)
            if hasattr(img, "__enter__"):
                img = stack.enter_context(img)
            else:
                close = getattr(img, "close", None)
                if callable(close):
                    stack.callback(close)
            rgba = img.convert("RGBA")
            load = getattr(rgba, "load", None)
            if callable(load):
                load()
            return rgba
    except (FileNotFoundError, UnidentifiedImageError, OSError) as exc:  # pragma: no cover - logged
        logger.warning("Failed to open image %s: %s", source, exc)
        return None
