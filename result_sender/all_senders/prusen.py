from asyncio import Queue
from datetime import datetime
import logging
import os
from pathlib import Path
import re
from threading import Thread
import time
import serial
from typing import Optional

from server_config_model import (
    RootConfig,
    ServerConfig,
    load_server_root_config,
    save_config,
    InputSerialConfigItem,
    OutputSerialConfigItem,
)
from result_sender.utils.decoders import decode_message
from io_schemas.sort_result import RootSortResult

from result_sender.interface import ResultInterface
from result_sender.libs.etc_tools import string2bytes
from result_sender.libs.log_controller import Log, logger_formatted
from result_sender.libs.sync.sync_sender import shm_count_loader


class ResultSender(ResultInterface):
    
    INPUT_COUNT = 1
    OUTPUT_COUNT = 1

    def __init__(self, *args, **kwargs):
        root_config: RootConfig = load_server_root_config()
        self.config: ServerConfig = root_config.config

        self.logger = None
        self.name = "ResultSenderWH"
        sync_num = self.config.serial_config.signal_count_per_pulse

        self.log_queue = self.result_sender_logger()
        self.result_data_queue = kwargs.get("result_data_queue")

        self.client_len = self.config.program_config.line_count
        self.gear_len = len(self.config.serial_config.inputs)
        self.send_offset = [self.config.serial_config.outputs[idx].offset for idx in self.gear_len]
        self.result_offset = [
            offset - 2 for offset in self.send_offset
        ]
        self.SYNC_COUNT: Optional[int] = None

        # self.sync_counts: list[Optional[int]] = [None for _ in range(self.client_len)]
        self.result_data_queue = kwargs.get("result_data_queue")
        self.last_sync_num = sync_num - 2

        self.count_flag_to_message_list: dict[Optional[bytes]] = {
            count_flag: None for count_flag in range(100)
        }
        self.count_flag_to_fruit: dict[int : list[Optional[RootSortResult]]] = {
            client_idx: [None for _ in range(100)]
            for client_idx in range(self.client_len)
        }
        
        if self.config.serial_config.is_read_configured:
            sync_port = kwargs.get("sync_port", "COM7")
            sync_baud_rate = kwargs.get("sync_baud_rate", "")
            self.ser_read = serial.Serial(sync_port, sync_baud_rate)
            print("connect sync serial")
        if self.config.serial_config.is_send_configured:
            self.ser_results = [None for _ in range(self.gear_len)]
            for client_idx, config in enumerate(self.config.serial_config.outputs):
                self.ser_results[client_idx] = serial.Serial(
                    config.port,
                    config.baudrate,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0,
                )
            print("connect result serial", len(self.ser_results))
        print("init done")

    @classmethod
    def check_valid_config(cls):
        """설정한 값이 해당 ResultSender와 유효한지 확인합니다"""
        root_config: RootConfig = load_server_root_config()
        config: ServerConfig = root_config.config
        # 유효성 검사
        if len(config.serial_config.inputs) != cls.INPUT_COUNT:
            raise ValueError("해당 모듈과 설정의 값이 일치하지 않습니다.")
        
        if len(config.serial_config.outputs) != cls.OUTPUT_COUNT:
            raise ValueError("해당 모듈과 설정의 값이 일치하지 않습니다.")
        
        for input_config in config.serial_config.inputs:
            with serial.Serial(input_config.port, baudrate=input_config.baudrate, timeout=1) as ser:
                if ser.is_open:
                    print(f"Connected to {input_config.port}")
        config.serial_config.is_read_configured = True
        save_config(root_config=root_config)

        for output_item in config.serial_config.outputs:
            with serial.Serial(output_item.port, baudrate=output_item.baudrate, timeout=1) as ser:
                if ser.is_open:
                    print(f"Connected to {output_item.port}")
        config.serial_config.is_send_configured = True
        save_config(root_config=root_config)

        return True

    @classmethod
    def create_default_config(cls):
        """현장에서 사용하는 틀을 생성합니다"""
        root_config: RootConfig = load_server_root_config()
        config: ServerConfig = root_config.config
        config.serial_config.inputs = [
            InputSerialConfigItem(port=f"COM{i}", baudrate=38400, pin=i + 2)
            for i in range(int(cls.INPUT_COUNT))
        ]
        config.serial_config.outputs = [
            OutputSerialConfigItem(port=f"COM{i + 1}", baudrate=38400, pin=i + 30, offset=20)
            for i in range(int(cls.OUTPUT_COUNT))
        ]
        save_config(root_config=root_config)

    @classmethod
    def get_arduino_sketch(cls):
        """현장에서 사용하는 아두이노 코드를 반환합니다"""
        root_config: RootConfig = load_server_root_config()
        config: ServerConfig = root_config.config
        pass
    
    def run(self):
        print("run input")
        self.logger = Log().config_queue_log(self.log_queue, self.name)

        for gear_idx in range(self.gear_len):
            Thread(
                target=self.result_serial_loop,
                kwargs={
                    "offset": self.result_offset[gear_idx],
                    "client_idx": gear_idx,
                },
                daemon=True,
            ).start()
            Thread(
                target=self.send_serial_loop,
                kwargs={
                    "offset": self.send_offset[gear_idx],
                    "client_idx": gear_idx,
                },
                daemon=True,
            ).start()
        print("result loop, send loop  start")

        Thread(
            target=self.get_fruit_data, args=(self.result_data_queue,), daemon=True
        ).start()
        if not self.test:
            while True:
                time.sleep(0.001)
                ser_read_bytes = self.ser_read.readline()

                re_bytes_string = re.sub(
                    rb"shutdown|[\r\n]", b"", ser_read_bytes
                )  # \r\n , shutdown 지우기
                # TODO 라인 3개 판별 -> flag or cut 판별
                self.process_serial_data(re_bytes_string)

    def process_serial_data(self, re_bytes_string):
        packed_message = decode_message(re_bytes_string)
        if packed_message:
            _line, count_flag, _cut, _group = packed_message
            self.SYNC_COUNT = count_flag

    def get_fruit_data(self, queue):
        while True:
            time.sleep(0.001)
            data: RootSortResult = queue.get()
            Thread(target=self.fruit_object_make, args=(data,), daemon=True).start()

    def fruit_object_make(self, data: RootSortResult):
        _count_flag = int(data.root.count_flag)
        line_idx = int(data.root.client)
        count_diff = (int(self.SYNC_COUNT) - int(_count_flag)) % 100
        self.count_flag_to_fruit[line_idx][_count_flag] = data

        self.log_message(
            f"Receive Fruit Instance"
            f"self.SYNC_COUNT : {self.SYNC_COUNT}, "
            f"_count_flag: {_count_flag} "
            f"diff count = {count_diff}"
            f"line_idx : {line_idx} "
            f"fruit_grade_idx : {data.root.grade_idx} ",
            log_level=logging.ERROR if count_diff > 18 else logging.INFO,
        )

    def result_serial_loop(self, offset=27):
        while self.SYNC_COUNT is None:
            time.sleep(0.001)
        target_count = 0
        while True:
            target_count %= 100
            time.sleep(0.001)
            if offset > (self.SYNC_COUNT - target_count) % 100:
                continue
            # TODO 경주 프르센대응 필요
            shape_msg_list = []
            print_flag = False
            for line_idx in range(self.client_len):
                fruit_instance: Optional[RootSortResult] = self.count_flag_to_fruit[
                    line_idx
                ][target_count]
                if fruit_instance:
                    print_flag = True
                    grade_idx = fruit_instance.root.grade_idx
                    shape_msg_list.append(f"형상:{grade_idx}")
                else:
                    shape_msg_list.append(f"형상:{0}")
                # 초기화
                self.count_flag_to_fruit[line_idx][target_count] = None
            msg = ','.join(shape_msg_list) + "\r\n"
            self.count_flag_to_message_list[target_count] = string2bytes(msg)
            if print_flag:
                self.log_message(
                    f"In result_serial_loop {self.SYNC_COUNT}, {target_count}, {msg}"
                )
            target_count += 1

    def log_message(self, msg, log_level=logging.INFO):
        logger_formatted(self.logger, log_level, self.name, msg)

    def send_serial_loop(self, offset=27, client_idx=0):
        while self.SYNC_COUNT is None:
            time.sleep(0.001)
        target_count = 0
        while True:
            target_count %= 100
            time.sleep(0.001)
            if offset > (self.SYNC_COUNT - target_count) % 100:
                continue
            serial_msg = self.count_flag_to_message_list[target_count]
            if self.config.serial_config.is_send_configured:
                self.ser_results[0].write(serial_msg)
                self.log_message(
                    f"send_serial_loop_C{client_idx} {self.SYNC_COUNT}, {target_count}, {serial_msg}"
                )
                self.count_flag_to_message_list[target_count] = None
            target_count += 1

    def result_sender_logger(self):
        listener = Log()
        log_queue = Queue(-1)
        date = datetime.today().strftime('%Y-%m-%d')
        home_dir = os.path.expanduser('~')
        log_base_path = os.path.join(home_dir, '.aiofarm', 'log')
        log_path = os.path.join(log_base_path, date)
        
        if not Path(log_path).exists():
            Path(log_path).mkdir(parents=True)
            
        listener.listener_start(f'{log_path}/{self.name.lower()}_result_sender', f'{self.name.lower()}_listener', log_queue)
        return log_queue
