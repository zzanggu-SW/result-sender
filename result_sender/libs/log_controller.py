import datetime
import logging
import logging.handlers
import os
import pathlib
import platform
from threading import Thread

from colorama import Fore, Style


# def logger_formatted(logger, level, name, message):
#     log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
#     logger.log(level, f"{name:25s} - {message}")
def logger_formatted(logger, level, name, message):
    # 변경하고 싶은 새로운 포맷
    # new_format = f"{name} - {message}"
    logger.log(level, message)


class Log:
    def __init__(self):
        self.th = None

    @staticmethod
    def get_logger(name):
        return logging.getLogger(name)

    def listener_start(self, file_path, name, queue):
        self.th = Thread(target=self._proc_log_queue, args=(file_path, name, queue), daemon=True)
        self.th.start()

    def listener_end(self, queue):
        queue.put(None)
        self.th.join()
        print("log listener end...")

    def _proc_log_queue(self, file_path, name, queue):
        self.config_log(file_path, name)
        logger = self.get_logger(name)
        while True:
            try:
                record = queue.get()
                if record is None:
                    break
                logger.handle(record)
            except Exception:
                import sys
                import traceback

                print("listener problem", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                break

    @staticmethod
    def config_queue_log(queue, name):
        """
        if you use multiprocess logging,
        call this in multiprocess as logging producer.
        logging consumer function is [self.listener_start] and [self.listener_end]
        it returns logger, and you can use this logger to log
        """
        qh = logging.handlers.QueueHandler(queue)
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        logger.addHandler(qh)
        return logger

    @staticmethod
    def config_log(file_path, name):
        """
        it returns FileHandler and StreamHandler logger
        if you do not need to use multiprocess logging,
        just call this function and use returned logger.
        """
        file_path = os.path.join(pathlib.Path(__file__).parent.parent, file_path)
        # err file handler
        fh_err = logging.handlers.RotatingFileHandler(file_path + "_error.log", "a")
        fh_err.setLevel(logging.WARNING)
        # file handler
        fh_dbg = logging.handlers.RotatingFileHandler(file_path + "_debug.log", "a")
        fh_dbg.setLevel(logging.DEBUG)
        # console handler
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        # logging format setting
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        sf = ColoredFormatter(log_format)
        ff = ColoredFormatter(log_format)
        fh_err.setFormatter(ff)
        fh_dbg.setFormatter(ff)
        sh.setFormatter(sf)
        if platform.system() == "Windows":
            import msvcrt

            import win32api
            import win32con

            win32api.SetHandleInformation(msvcrt.get_osfhandle(fh_dbg.stream.fileno()), win32con.HANDLE_FLAG_INHERIT, 0)
            win32api.SetHandleInformation(msvcrt.get_osfhandle(fh_err.stream.fileno()), win32con.HANDLE_FLAG_INHERIT, 0)
        # create logger, assign handler
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        logger.addHandler(fh_err)
        logger.addHandler(fh_dbg)
        logger.addHandler(sh)
        return logger


class ColoredFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": Fore.BLUE + Style.BRIGHT,
        "INFO": Fore.GREEN + Style.BRIGHT,
        "WARNING": Fore.YELLOW + Style.BRIGHT,
        "ERROR": Fore.RED + Style.BRIGHT,
        "CRITICAL": Fore.RED + Style.BRIGHT + Style.BRIGHT,
    }

    def format(self, record):
        log_message = super().format(record)
        return self.COLORS.get(record.levelname, "") + log_message + Style.RESET_ALL


def flask_logger_set(f_name="app.log", port=5000, logger_name="werkzeug", logger=None):
    if logger is None:
        logger = logging.getLogger(logger_name)

    logger.setLevel(logging.DEBUG)

    log_format = f"%(asctime)s - %(name)s - %(levelname)s - [Port: {port}] - %(message)s"
    formatter = logging.Formatter(log_format)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(formatter)

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(f"./log/{today}"):
        os.makedirs(f"./log/{today}")

    file_handler = logging.FileHandler(f"./log/{today}/{f_name}")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    # 색상 formatter를 추가하여 사용자 지정 로그 포매터 적용
    colored_formatter = ColoredFormatter(log_format)
    stream_handler.setFormatter(colored_formatter)
    return logger
