from result_sender.interface import ResultInterface


class ResultSender(ResultInterface):
    def __init__(self):
        super().__init__()

    @classmethod
    def run():
        pass

    @classmethod
    def check_valid_config():
        """설정한 값이 해당 SerialResultSender와 유효한지 확인합니다"""
        pass

    @classmethod
    def create_default_config():
        """현장에서 사용하는 틀을 생성합니다"""
        pass

    @classmethod
    def get_arduino_sketch():
        """현장에서 사용하는 아두이노 코드를 반환합니다"""
        pass
