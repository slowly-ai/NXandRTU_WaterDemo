"""
周期初始化模块：
1. 在单轮业务的前 15 秒内初始化外设和算法资源
2. 作为单轮初始化总入口，统一串联各模块
"""

import time
from log import error_log, write_log
from modbus import open_modbus_serial, read_rtu_time_and_calibrate, set_local_registers
from rtsp import initialize_rtsp_video_stream
from water_level_recognition import initialize_water_level_model


"""
作用：在单轮周期的初始化窗口内完成 Modbus 串口、RTSP 视频流和推理引擎初始化。
成功返回串口对象、视频流对象和模型对象；失败则抛出异常交给主流程处理。
"""
def initialize_cycle_resources(cycle_start_epoch, init_stage_end_seconds, should_calibrate_time=False):
    # 第一步：计算初始化阶段截止时间，并准备资源变量。
    init_deadline_monotonic = time.monotonic() + float(init_stage_end_seconds)
    serial_port = None
    video_capture = None
    model = None
    serial_attempt_count = 0
    rtsp_attempt_count = 0
    model_attempt_count = 0
    serial_start_logged = False
    rtsp_start_logged = False
    model_start_logged = False

    # 第二步：在初始化窗口内持续尝试打开串口、视频流和推理模型。
    while time.monotonic() < init_deadline_monotonic:
        if serial_port is None:
            if not serial_start_logged:
                write_log("初始化", "开始初始化 Modbus 串口")
                serial_start_logged = True
            serial_attempt_count += 1
            try:
                serial_port = open_modbus_serial()
                if should_calibrate_time:
                    read_rtu_time_and_calibrate(serial_port)
                set_local_registers("measuring")
            except Exception as exc:
                if serial_port is not None and serial_port.is_open:
                    serial_port.close()
                serial_port = None
                write_log("初始化", f"Modbus 串口初始化失败 | 第{serial_attempt_count}次 | {exc}")
                error_log("初始化", f"Modbus 串口初始化失败 | 第{serial_attempt_count}次 | {exc}")

        if video_capture is None:
            if not rtsp_start_logged:
                write_log("初始化", "开始初始化 RTSP 视频流")
                rtsp_start_logged = True
            rtsp_attempt_count += 1
            try:
                video_capture = initialize_rtsp_video_stream()
            except Exception as exc:
                video_capture = None
                write_log("初始化", f"RTSP 视频流初始化失败 | 第{rtsp_attempt_count}次 | {exc}")
                error_log("初始化", f"RTSP 视频流初始化失败 | 第{rtsp_attempt_count}次 | {exc}")

        if model is None:
            if not model_start_logged:
                write_log("初始化", "开始初始化水位识别推理引擎")
                model_start_logged = True
            model_attempt_count += 1
            try:
                model = initialize_water_level_model()
                write_log("初始化", "水位识别推理引擎初始化完成")
            except Exception as exc:
                model = None
                write_log("初始化", f"水位识别推理引擎初始化失败 | 第{model_attempt_count}次 | {exc}")
                error_log("初始化", f"水位识别推理引擎初始化失败 | 第{model_attempt_count}次 | {exc}")

        if serial_port is not None and video_capture is not None and model is not None:
            break

        remaining_seconds = init_deadline_monotonic - time.monotonic()
        if remaining_seconds > 0:
            time.sleep(min(0.5, remaining_seconds))

    # 第三步：串口必须成功，视频流和模型尽量在窗口内成功。
    if serial_port is None:
        if video_capture is not None:
            video_capture.release()
        model = None
        write_log("初始化", "初始化失败，已释放本轮已创建的资源")
        error_log("初始化", "初始化失败，已释放本轮已创建的资源")
        raise RuntimeError("Modbus 串口未在 15 秒初始化窗口内准备完成")

    detector_ready = video_capture is not None and model is not None
    if not detector_ready:
        write_log("初始化", "水位检测资源未在 15 秒内初始化完成，本轮识别按失败处理")
        error_log("初始化", "水位检测资源未在 15 秒内初始化完成，本轮识别按失败处理")

    return serial_port, video_capture, model, detector_ready
