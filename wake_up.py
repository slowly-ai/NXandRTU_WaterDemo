"""
NVIDIA Jetson Orin NX 休眠唤醒模块：
1. 按整 5 分钟计算下一次绝对唤醒时间
2. 调用硬件 RTC 进入 SC7 深度休眠
"""

import os
import subprocess
import time
from datetime import datetime
from log import error_log, write_log, write_round_separator

RTC_DEVICE_PATH = "/dev/rtc0"
CYCLE_SECONDS = 300
INIT_STAGE_END_SECONDS = 15
MODBUS_LISTEN_START_SECONDS = 30
MODBUS_LISTEN_END_SECONDS = 60


"""
作用：等待到本轮周期内的指定偏移时间点，再进入下一阶段。
"""
def wait_until_cycle_offset(cycle_start_epoch, offset_seconds, stage_name):
    # 第一步：计算当前阶段目标时间点。
    target_epoch = float(cycle_start_epoch) + float(offset_seconds)
    remaining_seconds = target_epoch - time.time()
    target_time_text = datetime.fromtimestamp(float(target_epoch)).strftime("%Y-%m-%d %H:%M:%S")

    # 第二步：如果还没到目标时间，则等待到该时间点；如果已超过，则立即记录超时情况。
    if remaining_seconds > 0:
        write_log(stage_name, f"等待到 {target_time_text} | 剩余 {remaining_seconds:.1f} 秒")
        time.sleep(remaining_seconds)
    else:
        write_log(stage_name, f"已到目标时间点 | 目标时间={target_time_text}")


"""
作用：计算下一次整 5 分钟唤醒时间，设置 RTC 并进入 SC7 深度休眠，醒来后返回下一轮周期起点。
"""
def sleep_to_next_cycle(cycle_start_epoch):
    # 第一步：计算下一轮整 5 分钟绝对唤醒时间。
    next_wake_epoch = int(float(cycle_start_epoch) // CYCLE_SECONDS) * CYCLE_SECONDS + CYCLE_SECONDS
    now_epoch = time.time()
    if next_wake_epoch <= now_epoch:
        next_wake_epoch = (int(now_epoch) // CYCLE_SECONDS + 1) * CYCLE_SECONDS

    # 第二步：只检查 RTC 设备是否存在；真正访问设备由 rtcwake/sudo 完成。
    if not os.path.exists(RTC_DEVICE_PATH):
        error_log("休眠", f"RTC 设备不存在: {RTC_DEVICE_PATH}")
        raise RuntimeError(f"RTC 设备不存在: {RTC_DEVICE_PATH}")

    write_log("休眠", f"下一次唤醒时间 | {datetime.fromtimestamp(float(next_wake_epoch)).strftime('%Y-%m-%d %H:%M:%S')}")
    write_log("休眠", f"准备进入 SC7 深度休眠 | RTC={RTC_DEVICE_PATH}")
    write_round_separator()

    # 第三步：调用 rtcwake 设置硬件 RTC，并进入 mem 休眠。
    rtcwake_command = ["rtcwake", "-m", "mem", "-d", RTC_DEVICE_PATH, "-t", str(int(next_wake_epoch))]
    if not (hasattr(os, "geteuid") and os.geteuid() == 0):
        rtcwake_command = ["sudo", "-n", *rtcwake_command]

    try:
        result = subprocess.run(
            rtcwake_command,
            capture_output=True,
            check=False,
            text=True,
        )
    except Exception as exc:
        detail_text = (
            f"错误种类: rtcwake 命令启动失败\n"
            f"异常类型: {type(exc).__name__}\n"
            f"异常信息: {exc}\n"
        )
        error_log("休眠", f"rtcwake 命令启动失败 | {exc}", detail_text)
        raise

    if result.returncode != 0:
        error_text = (result.stderr or result.stdout or "").strip()
        detail_text = (
            f"错误种类: rtcwake 执行失败\n"
            f"错误码: returncode={result.returncode}\n"
            f"stdout:\n{(result.stdout or '').strip()}\n"
            f"stderr:\n{(result.stderr or '').strip()}\n"
        )
        if error_text:
            error_log("休眠", f"rtcwake 执行失败，返回码={result.returncode} | {error_text}", detail_text)
            raise RuntimeError(f"rtcwake 执行失败，返回码={result.returncode} | {error_text}")
        error_log("休眠", f"rtcwake 执行失败，返回码={result.returncode}", detail_text)
        raise RuntimeError(f"rtcwake 执行失败，返回码={result.returncode}")

    # 第四步：系统被 RTC 唤醒后，立即输出唤醒日志并返回下一轮周期起点。
    write_log(
        "唤醒",
        (
            f"系统唤醒 | 计划时间={datetime.fromtimestamp(float(next_wake_epoch)).strftime('%Y-%m-%d %H:%M:%S')}"
            f" | 实际时间={datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')}"
        ),
    )
    return float(next_wake_epoch)
