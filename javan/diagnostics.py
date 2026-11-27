"""Local rotating diagnostics, without customer URLs, messages or financial fields."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import traceback

LOGGER = logging.getLogger('javan')
LOGGER.addHandler(logging.NullHandler())


def record_error(exc_type, tb):
    frames = ' > '.join(f'{Path(f.filename).name}:{f.lineno}:{f.name}' for f in traceback.extract_tb(tb))
    LOGGER.error('Unhandled %s at %s', exc_type.__name__, frames)


def configure_logging(folder):
    directory = Path(folder) / 'logs'
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(directory / 'javan.log', maxBytes=512*1024, backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False
    def hook(exc_type, exc, tb):
        record_error(exc_type, tb)
    sys.excepthook = hook
    LOGGER.info('Application started')
    return LOGGER
