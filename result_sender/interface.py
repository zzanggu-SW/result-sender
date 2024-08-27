from threading import Thread


class ResultInterface(Thread):
    def __init__(self, *args, **kwargs):
        self.logger = None

    def run(self):
        raise NotImplementedError("This method should be implemented by subclasses.")

    @classmethod
    def check_valid_config(self):
        """설정한 값이 해당 SerialResultSender와 유효한지 확인합니다"""
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    @classmethod
    def create_default_config(cls):
        """현장에서 사용하는 틀을 생성합니다"""
        raise NotImplementedError("This method should be implemented by subclasses.")

    @classmethod
    def get_arduino_sketch(cls):
        """현장에서 사용하는 아두이노 코드를 반환합니다"""
        raise NotImplementedError("This method should be implemented by subclasses.")
