#!/usr/bin/env python3

from .exithandler import ExitHandler
from .pool import ClusteredCSI
from .backlog import CSIBacklog
from .board import Board
from .pool import Pool
import logging
import sys

__version__ = "0.1.1"
__title__ = "pyespargos"
__description__ = "Python library for working with the ESPARGOS WiFi channel sounder"
__uri__ = "http://github.com/ESPARGOS/pyespargos"

class Logger:
    logger = logging.getLogger("pyespargos")
    stderrHandler = logging.StreamHandler(sys.stderr)
    stderrHandler.setFormatter(logging.Formatter("[%(name)-20s] %(message)s"))
    logger.addHandler(stderrHandler)
    logger.setLevel(level = logging.INFO)

    @classmethod
    def get_level(cls):
        return cls.log.getEffectiveLevel()

    @classmethod
    def set_level(cls, level):
        cls.log.setLevel(level=level)
