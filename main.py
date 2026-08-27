"""
作用：主入口
"""

import sys
import traceback
import time
from datetime import datetime
from log import error_log, write_log
from modbus import set_local_registers, wait_and_reply_once
from cycle_init import initialize_cycle_resources
from rtsp import capture_frame_from_rtsp
from simulate_water_level import run_simulated_water_level_detection
from water_level_recognition import run_water_level_detection
from wake_up import (
    CYCLE_SECONDS,
    INIT_STAGE_END_SECONDS,
    MODBUS_LISTEN_END_SECONDS,
    MODBUS_LISTEN_START_SECONDS,
    sleep_to_next_cycle,
    wait_until_cycle_offset,
)


"""
作用：按单轮周期执行初始化、水位识别、等待主站读取和休眠唤醒循环。
"""
def main():
    # 第一步：程序首次启动后，先对齐到下一次整 5 分钟时间点。
    current_epoch = time.time()
    cycle_start_epoch = (int(current_epoch) // CYCLE_SECONDS + 1) * CYCLE_SECONDS
    write_log("系统", f"程序启动 | 当前时间={datetime.fromtimestamp(current_epoch).strftime('%Y-%m-%d %H:%M:%S')}")
    write_log("对齐", f"首轮启动等待整 5 分钟对齐 | 目标时间={datetime.fromtimestamp(cycle_start_epoch).strftime('%Y-%m-%d %H:%M:%S')}")
    wait_until_cycle_offset(cycle_start_epoch, 0, "对齐")
    write_log("唤醒", "首轮对齐完成，开始执行第一轮业务")

    while True:
        serial_port = None
        video_capture = None
        model = None
        should_enter_sleep = True
        should_exit_program = False
        exit_code = 0

        try:
            # 第二步：进入本轮周期，先在前 15 秒内完成外设与算法资源初始化。
            write_log("周期", f"本轮开始 | 周期起点={datetime.fromtimestamp(cycle_start_epoch).strftime('%Y-%m-%d %H:%M:%S')}")
            write_log("初始化", "开始初始化外设与算法资源")

            serial_port, video_capture, model, detector_ready = initialize_cycle_resources(
                cycle_start_epoch,
                INIT_STAGE_END_SECONDS,
            )

            wait_until_cycle_offset(cycle_start_epoch, INIT_STAGE_END_SECONDS, "初始化")

            # 第三步：T+15 到 T+30 之间执行取流和水位识别。
            result = "初始化失败"
            if detector_ready:
                write_log("识别", "开始执行水位检测")
                frame = capture_frame_from_rtsp(video_capture)
                if frame is None:
                    result = "视频取流失败"
                else:
                    # result = run_water_level_detection(model, frame)       #算法识别水位
                    result = run_simulated_water_level_detection()           #模拟水位
                write_log("识别", f"水位识别结果 | {result}")
            else:
                write_log("识别", "跳过水位检测 | 原因=RTSP 视频流或推理引擎未按时初始化完成")

            if isinstance(result, (int, float)):
                set_local_registers("success", result)
            else:
                set_local_registers("error")

            # 第四步：T+30 到 T+60 之间监听 RTU 主站读取请求。
            wait_until_cycle_offset(cycle_start_epoch, MODBUS_LISTEN_START_SECONDS, "通信")
            listen_timeout_seconds = max(0.0, cycle_start_epoch + MODBUS_LISTEN_END_SECONDS - time.time())
            if listen_timeout_seconds > 0:
                read_success = wait_and_reply_once(serial_port, timeout_seconds=listen_timeout_seconds)
                if read_success:
                    write_log("通信", "已收到 RTU 主站读请求，本轮监听提前结束")
                else:
                    write_log("通信", "RTU 主站读取超时")
            else:
                write_log("通信", "RTU 监听阶段已超时，直接结束本轮业务")

        except KeyboardInterrupt:
            write_log("系统", "收到中断信号，程序退出，不再进入休眠")
            should_enter_sleep = False
            should_exit_program = True
        except Exception as exc:
            write_log("异常", f"主流程异常 | {exc}")
            error_log("异常", f"主流程异常 | {exc}")
            if serial_port is not None:
                try:
                    set_local_registers("error")
                except Exception as register_exc:
                    write_log("异常", f"写入错误状态寄存器失败 | {register_exc}")
                    error_log("异常", f"写入错误状态寄存器失败 | {register_exc}")

        finally:
            # 第五步：无论本轮成功还是失败，都释放资源并进入下一轮 RTC 休眠。
            if video_capture is not None:
                video_capture.release()
                write_log("休眠", "RTSP 视频流已关闭")

            if serial_port is not None and serial_port.is_open:
                serial_port.close()
                write_log("休眠", "Modbus 串口已关闭")

            model = None

            if should_enter_sleep:
                try:
                    cycle_start_epoch = sleep_to_next_cycle(cycle_start_epoch)
                except Exception as exc:
                    write_log("异常", f"休眠流程异常 | {exc}")
                    error_log(
                        "异常",
                        f"休眠流程异常 | {exc}",
                        (
                            f"错误类型: {type(exc).__name__}\n"
                            f"异常信息: {exc}\n"
                            f"traceback:\n{traceback.format_exc()}"
                        ),
                    )
                    write_log("系统", "RTC 休眠失败，程序退出")
                    error_log("系统", "RTC 休眠失败，程序退出")
                    should_exit_program = True
                    exit_code = 1

        if should_exit_program:
            sys.exit(exit_code)


if __name__ == "__main__":
    main()
