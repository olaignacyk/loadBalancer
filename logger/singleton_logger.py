import logging
from colorama import Fore, Style
from threading import Lock


class ColorFormatter(logging.Formatter):
    """Custom formatter to add colors based on log level."""
    COLOR_MAP = {
        logging.DEBUG: Fore.BLUE,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.MAGENTA,
    }

    def format(self, record):
        color = self.COLOR_MAP.get(record.levelno, Fore.WHITE)
        message = super().format(record)
        return f"{color}{message}{Style.RESET_ALL}"


class SingletonLogger:
    _instance = None
    _lock = Lock()

    def __new__(cls):
        """Ensure only one instance of the logger is created."""
        if not cls._instance:
            with cls._lock:  # Thread-safe instantiation
                if not cls._instance:
                    cls._instance = super(SingletonLogger, cls).__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Set up the logger configuration."""
        self.logger = logging.getLogger("LoadBalancerLogger")
        self.logger.setLevel(logging.DEBUG)

        # Create console handler with a custom formatter
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        formatter = ColorFormatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(formatter)

        # Prevent duplicate handlers
        if not self.logger.handlers:
            self.logger.addHandler(console_handler)

    def get_logger(self):
        """Return the configured logger."""
        return self.logger
