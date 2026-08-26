"""
NVIDIA Jetson Orin NX 水位监测项目的 Modbus 从站基础模块：
1. 打开串口
2. 更新本地寄存器
3. 等待主站读取并回发响应
"""

import time
import serial
from log import write_log

# 串口参数
SERIAL_PORT = "/dev/modbus_485"
BAUDRATE = 9600
PARITY = "N"
DATA_BITS = 8
STOP_BITS = 1

# Modbus 协议参数
SLAVE_ID = 5
FUNCTION_CODE = 0x03
REG_ADDR = 0
READY_FLAG_OFFSET = 2
STATE_CODE_OFFSET = 3
REQUIRED_REG_COUNT = 4

# 状态码
STATE_IDLE = 0
STATE_MEASURING = 1
STATE_READY_OK = 2
STATE_READY_ERROR = 3
NO_DATA_WORD = 0xFFFF

# 本地保持寄存器定义：
# REG_ADDR + 0：水位高 16 位
# REG_ADDR + 1：水位低 16 位
# REG_ADDR + 2：ready 标志
# REG_ADDR + 3：state 状态码
LOCAL_REGISTERS = [NO_DATA_WORD, NO_DATA_WORD, 0, STATE_IDLE]


"""
作用：打开开发板上的 RS485 串口，返回串口对象。
"""
def open_modbus_serial():
    # 第一步：按原程序的基础串口参数打开串口。
    serial_port = serial.Serial(
        port=SERIAL_PORT,
        baudrate=BAUDRATE,
        parity=PARITY,
        bytesize=DATA_BITS,
        stopbits=STOP_BITS,
        timeout=0.1,
    )

    # 第二步：清空输入输出缓存，避免读到旧数据。
    if hasattr(serial_port, "reset_input_buffer"):
        serial_port.reset_input_buffer()
    if hasattr(serial_port, "reset_output_buffer"):
        serial_port.reset_output_buffer()

    write_log("初始化", f"Modbus 串口初始化完成 | 串口={SERIAL_PORT}")
    return serial_port


"""
作用：按当前业务状态更新本地保持寄存器。
state 支持：idle、measuring、success、error
"""
def set_local_registers(state, water_level_cm=None):
    global LOCAL_REGISTERS

    # 第一步：空闲状态，清空水位数据，ready 置 0。
    if state == "idle":
        LOCAL_REGISTERS = [NO_DATA_WORD, NO_DATA_WORD, 0, STATE_IDLE]
        write_log("初始化", f"本地寄存器已设置为空闲状态 | values={LOCAL_REGISTERS}")
        return list(LOCAL_REGISTERS)

    # 第二步：测量中状态，清空水位数据，state 置为测量中。
    if state == "measuring":
        LOCAL_REGISTERS = [NO_DATA_WORD, NO_DATA_WORD, 0, STATE_MEASURING]
        write_log("初始化", f"本地寄存器已设置为测量中状态 | values={LOCAL_REGISTERS}")
        return list(LOCAL_REGISTERS)

    # 第三步：成功状态，把厘米水位换算成毫米后写入寄存器。
    if state == "success":
        if water_level_cm is None:
            raise ValueError("success 状态必须提供 water_level_cm")

        water_level_mm = int(round(float(water_level_cm) * 10.0))
        water_high = (water_level_mm >> 16) & 0xFFFF
        water_low = water_level_mm & 0xFFFF
        LOCAL_REGISTERS = [water_high, water_low, 1, STATE_READY_OK]
        write_log(
            "通信",
            f"本地寄存器已写入成功水位 | 水位={water_level_cm:.2f} cm | values={LOCAL_REGISTERS}",
        )
        return list(LOCAL_REGISTERS)

    # 第四步：错误状态，写入无数据标记，ready 置 1，state 置失败。
    if state == "error":
        LOCAL_REGISTERS = [NO_DATA_WORD, NO_DATA_WORD, 1, STATE_READY_ERROR]
        write_log("初始化", f"本地寄存器已设置为错误状态 | values={LOCAL_REGISTERS}")
        return list(LOCAL_REGISTERS)

    raise ValueError(f"不支持的寄存器状态: {state}")


"""
作用：等待 RTU 主站读取请求，检查请求帧，读取本地寄存器，组装响应帧并回发。
收到一次有效读请求后立即返回 True；超时未收到则返回 False。
"""
def wait_and_reply_once(serial_port, timeout_seconds=15.0):
    # 第一步：监听前先清空缓存，避免上一轮残留数据影响本轮通信。
    if hasattr(serial_port, "reset_input_buffer"):
        serial_port.reset_input_buffer()
    if hasattr(serial_port, "reset_output_buffer"):
        serial_port.reset_output_buffer()
    write_log("通信", f"Modbus 开始监听主站请求 | 超时={timeout_seconds:.1f}s")

    # 第二步：循环读取串口数据，从缓存中提取 8 字节 Modbus RTU 读请求帧。
    receive_buffer = bytearray()
    deadline = time.monotonic() + float(timeout_seconds)
    while time.monotonic() < deadline:
        chunk = serial_port.read(256)
        if chunk:
            receive_buffer.extend(chunk)

        while len(receive_buffer) >= 8:
            if receive_buffer[0] != (SLAVE_ID & 0xFF):
                del receive_buffer[0]
                continue

            request_frame = bytes(receive_buffer[:8])

            # 第三步：检查从站地址、功能码、寄存器数量和 CRC 是否正确。
            slave_id = request_frame[0]
            function_code = request_frame[1]
            start_address = (request_frame[2] << 8) | request_frame[3]
            register_count = (request_frame[4] << 8) | request_frame[5]
            received_crc = request_frame[6] | (request_frame[7] << 8)

            crc = 0xFFFF
            for byte in request_frame[:6]:
                crc ^= byte
                for _ in range(8):
                    if crc & 0x0001:
                        crc = (crc >> 1) ^ 0xA001
                    else:
                        crc >>= 1
            expected_crc = crc & 0xFFFF

            if slave_id != SLAVE_ID:
                write_log("通信", "从站地址不匹配，忽略该请求")
                del receive_buffer[0]
                continue

            if received_crc != expected_crc:
                write_log("通信", "请求帧 CRC 校验失败，忽略该请求")
                del receive_buffer[0]
                continue

            del receive_buffer[:8]
            write_log("通信", f"开发板已收到请求帧 | {request_frame.hex().upper()}")

            request_ok = False
            if function_code != FUNCTION_CODE:
                payload = bytes((SLAVE_ID, function_code | 0x80, 0x01))
                write_log("通信", "功能码不支持，准备返回异常响应")
            elif register_count <= 0 or register_count > 125:
                payload = bytes((SLAVE_ID, function_code | 0x80, 0x03))
                write_log("通信", "寄存器数量非法，准备返回异常响应")
            else:
                write_log("通信", "开发板检查通过")

                # 第四步：按照主站请求地址读取本地寄存器数据。
                start_index = start_address - REG_ADDR
                end_index = start_index + register_count
                if start_index < 0 or end_index > REQUIRED_REG_COUNT:
                    payload = bytes((SLAVE_ID, function_code | 0x80, 0x02))
                    write_log("通信", "寄存器地址越界，准备返回异常响应")
                else:
                    register_values = LOCAL_REGISTERS[start_index:end_index]
                    write_log("通信", f"开发板已读取本地寄存器 | values={register_values}")

                    # 第五步：组装正常响应帧并回发给 RTU 主站。
                    payload = bytearray((SLAVE_ID, function_code, len(register_values) * 2))
                    for value in register_values:
                        payload.extend(((int(value) >> 8) & 0xFF, int(value) & 0xFF))
                    request_ok = True

            crc = 0xFFFF
            for byte in payload:
                crc ^= byte
                for _ in range(8):
                    if crc & 0x0001:
                        crc = (crc >> 1) ^ 0xA001
                    else:
                        crc >>= 1

            response_frame = bytes(payload) + bytes((crc & 0xFF, (crc >> 8) & 0xFF))
            serial_port.write(response_frame)
            serial_port.flush()
            write_log("通信", f"开发板已回发响应帧 | {response_frame.hex().upper()}")
            if request_ok:
                return True

    write_log("通信", f"Modbus 监听超时 | {timeout_seconds:.1f}s 内未收到有效主站读请求")
    return False
