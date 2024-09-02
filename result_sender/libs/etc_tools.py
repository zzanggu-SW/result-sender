import binascii


def string2bytes(st):
    return bytes.fromhex((binascii.hexlify(st.encode("euc-kr"))).decode("utf-8"))


def bytes2string(b):
    return binascii.unhexlify(b.hex().encode("utf-8")).decode("euc-kr")
