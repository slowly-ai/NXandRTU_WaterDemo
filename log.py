"""
日志模块：
1. 统一输出运行日志并立即落盘
2. 保存每次取流得到的图片
3. 便于后续排查唤醒、识别、通信全过程
"""

import os
from datetime import datetime
import cv2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_LOG_DIR = os.path.join(BASE_DIR, "runtime_logs")
CAPTURE_IMAGE_DIR = os.path.join(BASE_DIR, "capture_images")


"""
作用：输出一条带时间和阶段的日志，同时立即写入本地日志文件。
"""
def write_log(stage, message):
    # 第一步：生成当前日志时间和日志文本。
    now = datetime.now()
    timestamp_text = now.strftime("%Y-%m-%d %H:%M:%S")
    log_text = f"[{timestamp_text}] [{stage}] {message}"

    # 第二步：先打印到终端，保证程序运行时能实时看到日志。
    print(log_text, flush=True)

    # 第三步：按天创建日志文件，并强制刷新到磁盘。
    os.makedirs(RUNTIME_LOG_DIR, exist_ok=True)
    log_file_path = os.path.join(RUNTIME_LOG_DIR, f"water_level_{now.year}-{now.month}-{now.day}.log")
    with open(log_file_path, "a", encoding="utf-8") as log_file:
        log_file.write(log_text + "\n")
        log_file.flush()
        os.fsync(log_file.fileno())


"""
作用：把当前取流图片按时间戳保存到本地目录，成功返回图片路径，失败返回空字符串。
"""
def save_capture_image(frame):
    # 第一步：确保图片保存目录存在。
    os.makedirs(CAPTURE_IMAGE_DIR, exist_ok=True)

    # 第二步：按“年-月-日_时:分:秒”生成图片文件名。
    now = datetime.now()
    image_name = f"{now.year}-{now.month}-{now.day}_{now:%H:%M:%S}.jpg"
    image_path = os.path.join(CAPTURE_IMAGE_DIR, image_name)

    # 第三步：保存图片并记录结果日志。
    save_ok = cv2.imwrite(image_path, frame)
    if save_ok:
        write_log("图像", f"图片保存成功 | 文件名={image_name}")
        return image_path

    write_log("图像", "图片保存失败")
    return ""
