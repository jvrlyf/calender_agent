"""
Module-level structured logging.
"""

import logging
import sys


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(logging.DEBUG)

        fmt = logging.Formatter(
            "[%(asctime)s] %(levelname)-8s %(name)-25s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.DEBUG)
        console.setFormatter(fmt)
        logger.addHandler(console)

        file_handler = logging.FileHandler("app.log", encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger