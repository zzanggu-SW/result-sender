from threading import Thread

import requests


def send_signal_to_cache():
    url = CACHE_URL + "/signal"
    requests.get(url)


def send_signal_to_dash_board():
    url = BOARD_URL + "/"
    requests.get(url)


def send_signal():
    print("send signal")
    Thread(target=send_signal_to_cache, args=(), daemon=True).start()
    if USE_DASHBOARD:
        Thread(target=send_signal_to_dash_board, args=(), daemon=True).start()
