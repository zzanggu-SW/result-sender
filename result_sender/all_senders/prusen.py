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
    BAUDRATE = 38400

    def __init__(self, *args, **kwargs):
        super().__init__()
        root_config: RootConfig = load_server_root_config()
        self.config: ServerConfig = root_config.config

        self.logger = None
        self.name = "ResultSenderWH"
        sync_num = self.config.serial_config.signal_count_per_pulse

        self.log_queue = self.result_sender_logger()
        self.result_data_queue = kwargs.get("result_data_queue")

        self.client_len = self.config.program_config.line_count
        self.gear_len = len(self.config.serial_config.inputs)
        self.send_offset = [
            self.config.serial_config.outputs[idx].offset
            for idx in range(self.gear_len)
        ]
        self.result_offset = [offset - 2 for offset in self.send_offset]
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

        serial_list = []
        try:
            for input_config in config.serial_config.inputs:
                ser = serial.Serial(
                    input_config.port, baudrate=input_config.baudrate, timeout=1
                )
                serial_list.append(ser)
                if ser.is_open:
                    print(f"Connected to {input_config.port}")
            config.serial_config.is_read_configured = True
            save_config(root_config=root_config)

            for output_item in config.serial_config.outputs:
                ser = serial.Serial(
                    output_item.port, baudrate=output_item.baudrate, timeout=1
                )
                serial_list.append(ser)
                if ser.is_open:
                    print(f"Connected to {output_item.port}")
            config.serial_config.is_send_configured = True
            save_config(root_config=root_config)

            return True
        finally:
            # 모든 시리얼 포트 연결을 닫습니다
            for ser in serial_list:
                if ser.is_open:
                    ser.close()
                    print(f"Disconnected from {ser.port}")

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
            OutputSerialConfigItem(
                port=f"COM{i + 1}", baudrate=38400, pin=i + 30, offset=20
            )
            for i in range(int(cls.OUTPUT_COUNT))
        ]
        config.serial_config.is_read_configured = False
        config.serial_config.is_send_configured = False
        config.serial_config.is_production_sketch_uploaded = False
        save_config(root_config=root_config)

    @classmethod
    def get_arduino_sketch(cls):
        """현장에서 사용하는 아두이노 코드를 반환합니다"""
        root_config: RootConfig = load_server_root_config()
        config: ServerConfig = root_config.config
        
        baudrate = cls.BAUDRATE
        num_of_line = config.program_config.line_count
        num_of_beat = config.serial_config.signal_count_per_pulse
        
        pin_in_map = [input_item.pin for input_item in config.serial_config.inputs]
        pin_out_map = [output.pin for output in config.serial_config.outputs]
        trigger_intervals = [input_item.camera_delay for input_item in config.serial_config.inputs]
        soft_intervals = [10 for _ in range(num_of_line)]  # 예시 소프트 인터벌
        
        # 배열을 아두이노 코드 형식으로 변환
        pin_in_map_str = ", ".join(map(str, pin_in_map))
        pin_out_map_str = ", ".join(map(str, pin_out_map))
        trigger_intervals_str = ", ".join(map(str, trigger_intervals))
        soft_intervals_str = ", ".join(map(str, soft_intervals))

        arduino_sketch = f"""
        // 개별 구분되는 라인의 개수
        #define NUM_OF_LINE {num_of_line}
        // 한 싱크의 총 이미지 촬영 tn
        #define NUM_OF_BEAT {num_of_beat}

        // interval2의 최소 수치
        #define ITD 0
        // interval2의 최대 수치 ; 4000으로 설정되어있다면, 4초이상 간격이 벌어질경우 라인이 정지했다고 판단한다는 뜻
        #define ITU 4000

        const int PIN_IN_MAP[NUM_OF_LINE] = {{{pin_in_map_str}}};     // 2~9번 라인이 각각 PLC의 몇번 포트에 연결되어있는가를 Array로 전달
        const int PIN_OUT_MAP[NUM_OF_LINE] = {{{pin_out_map_str}}}; // 0~n번 라인이 각각 PLC의 몇번 포트에 연결되어있는가를 Array로 전달
        int TRIGGER_INTERVAL[NUM_OF_LINE] = {{{trigger_intervals_str}}};  // 트리거 인터벌 = 신호받고 -> 카메라에게 신호 주는데까지의 시간
        int SOFT_INTERVAL[NUM_OF_LINE] = {{{soft_intervals_str}}};  // 소프트 인터벌 = 카메라에게 신호 주고 -> 컴퓨터에게 신호 주는데까지의 시간

        unsigned long cM;
        bool onOff[NUM_OF_LINE];
        uint32_t photoelectric_sensor_signal_count[NUM_OF_LINE];
        uint32_t downbeat_count[NUM_OF_LINE];
        uint32_t downbeat_count_now[NUM_OF_LINE];
        uint32_t downbeat_sync_count[NUM_OF_LINE];
        uint32_t downbeat_trig_count[NUM_OF_LINE];
        int interval_check_count[NUM_OF_LINE];
        unsigned long interval2[NUM_OF_LINE];
        unsigned long pMH[NUM_OF_LINE];
        unsigned long pM[NUM_OF_LINE];
        unsigned long pM2[NUM_OF_LINE];
        uint32_t upbeat_count[NUM_OF_LINE][NUM_OF_BEAT - 1];
        uint32_t upbeat_sync_count[NUM_OF_LINE][NUM_OF_BEAT - 1];
        int upbeat_interval[NUM_OF_LINE][NUM_OF_BEAT - 1];
        uint32_t count[NUM_OF_LINE];

        void setup()
        {{
            for (int i = 0; i < NUM_OF_LINE; i++)
            {{
                onOff[i] = false;
                photoelectric_sensor_signal_count[i] = 0;
                downbeat_count[i] = 0;
                downbeat_count_now[i] = 0;
                downbeat_sync_count[i] = 0;
                downbeat_trig_count[i] = 0;
                interval_check_count[i] = 0;
                count[i] = 0;
                pM[i] = millis();
                pM2[i] = millis();
                pMH[i] = millis();

                pinMode(PIN_IN_MAP[i], INPUT);
                pinMode(PIN_OUT_MAP[i], OUTPUT);

                interval2[i] = 440;
                for (int j = 0; j < NUM_OF_BEAT - 1; j++)
                {{
                    upbeat_count[i][j] = 0;
                    upbeat_sync_count[i][j] = 0;
                    upbeat_interval[i][j] = 0;
                }}
            }}

            pinMode(7, OUTPUT);
            Serial.begin({baudrate});
            Serial1.begin({baudrate});
            Serial2.begin({baudrate});
            Serial3.begin({baudrate});
        }}

        uint32_t check_digital_read(int numOfPin, int array_num, bool ooc[])
        {{
            if (digitalRead(numOfPin) == 1)
            {{
                if (ooc[array_num] == false)
                {{
                    ooc[array_num] = true;
                    return 1;
                }}
            }}
            else if (digitalRead(numOfPin) == 0)
            {{
                if (ooc[array_num] == true)
                {{
                    ooc[array_num] = false;
                }}
            }}
            return 0;
        }}

        void signal(int k)
        {{
            photoelectric_sensor_signal_count[k] += check_digital_read(PIN_IN_MAP[k], k, onOff);
            if (downbeat_count[k] < photoelectric_sensor_signal_count[k])
            {{
                if (cM - pM[k] < 5)
                {{
                    downbeat_count[k] = photoelectric_sensor_signal_count[k];
                    return;
                }}
                downbeat_count[k] = photoelectric_sensor_signal_count[k];
                interval_check_count[k]++;
                pM[k] = cM;
                if (interval_check_count[k] % 2 == 0)
                {{
                    interval_check_count[k] = 0;
                    interval2[k] = cM - pM2[k];
                    pM2[k] = cM;
                    if ((ITD < interval2[k]) && (interval2[k] < ITU))
                    {{
                        for (int i = 0; i < NUM_OF_BEAT - 1; i++)
                        {{
                            upbeat_interval[k][i] = (interval2[k] / 2) / (NUM_OF_BEAT) * (i + 1);
                        }}
                    }}
                }}
            }}
            if (downbeat_trig_count[k] < downbeat_count[k] and cM - pM[k] >= TRIGGER_INTERVAL[k])
            {{
                downbeat_trig_count[k] = downbeat_count[k];
                downbeat_count_now[k] = downbeat_count[k];
                pMH[k] = cM;
                digitalWrite(PIN_OUT_MAP[k], HIGH);
            }}
            if (downbeat_sync_count[k] < downbeat_count_now[k] and cM - pMH[k] >= SOFT_INTERVAL[k])
            {{
                downbeat_sync_count[k] = downbeat_count_now[k];
                count[k]++; // 이거를 시리얼로 보내세요.
                digitalWrite(PIN_OUT_MAP[k], LOW);
                Serial.println("L" + String(k) + "S" + String(count[k] % 100) + "C0" + "G0");
                Serial1.println("L" + String(k) + "S" + String(count[k] % 100) + "C0" + "G0");
            }}
            for (int i = 0; i < NUM_OF_BEAT - 1; i++)
            {{
                if (upbeat_count[k][i] != downbeat_sync_count[k] and upbeat_interval[k][i] != 0 and cM - pMH[k] >= upbeat_interval[k][i])
                {{
                    upbeat_count[k][i] = downbeat_sync_count[k];
                    digitalWrite(PIN_OUT_MAP[k], HIGH);
                }}
            }}
            for (int i = 0; i < NUM_OF_BEAT - 1; i++)
            {{
                if (upbeat_sync_count[k][i] != downbeat_sync_count[k] and upbeat_interval[k][i] != 0 and cM - pMH[k] >= upbeat_interval[k][i] + SOFT_INTERVAL[k])
                {{
                    upbeat_sync_count[k][i] = downbeat_sync_count[k];
                    digitalWrite(PIN_OUT_MAP[k], LOW);
                    Serial1.println("L" + String(k) + "S" + String(count[k] % 100) + "C" + String(i + 1) + "G0");
                    Serial.println("L" + String(k) + "S" + String(count[k] % 100) + "C" + String(i + 1) + "G0");
                }}
            }}
        }}

        void loop()
        {{
            cM = millis();
            for (int i = 0; i < NUM_OF_LINE; i++)
            {{
                signal(i);
            }}
        }}
        """

        return arduino_sketch

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
            log_level=logging.ERROR if count_diff > self.config.serial_config.outputs[line_idx].offset else logging.INFO,
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
            msg = ",".join(shape_msg_list) + "\r\n"
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
        date = datetime.today().strftime("%Y-%m-%d")
        home_dir = os.path.expanduser("~")
        log_base_path = os.path.join(home_dir, ".aiofarm", "log")
        log_path = os.path.join(log_base_path, date)

        if not Path(log_path).exists():
            Path(log_path).mkdir(parents=True)

        listener.listener_start(
            f"{log_path}/{self.name.lower()}_result_sender",
            f"{self.name.lower()}_listener",
            log_queue,
        )
        return log_queue
