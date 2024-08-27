from threading import Thread

import requests

from app.config import CACHE_URL, BOARD_URL, USE_DASHBOARD


def send_signal_to_cache():
    url = CACHE_URL + '/signal'
    requests.get(url)


def send_signal_to_dash_board():
    url = BOARD_URL + '/'  # TODO
    requests.get(url)


def send_signal():
    print("send signal")
    Thread(target=send_signal_to_cache, args=(), daemon=True).start()
    if USE_DASHBOARD:
        Thread(target=send_signal_to_dash_board, args=(), daemon=True).start()
