class SerialResultInterface:
    def __init__(self):
        self.logger = None

    def run(self):
        raise NotImplementedError("This method should be implemented by subclasses.")

    def check_valid_config(self):
        """설정한 값이 해당 SerialResultSender와 유효한지 확인합니다"""
        raise NotImplementedError("This method should be implemented by subclasses.")

    def create_default_config(self):
        """현장에서 사용하는 틀을 생성합니다"""
        raise NotImplementedError("This method should be implemented by subclasses.")

    def return_arduino_sketch(self):
        """현장에서 사용하는 아두이노 코드를 반환합니다"""
        raise NotImplementedError("This method should be implemented by subclasses.")
