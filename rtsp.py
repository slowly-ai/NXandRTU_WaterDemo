"""
RTSP 视频流模块：
1. 参数设置
2. RTSP 视频流初始化
3. RTSP 取帧
"""

import cv2
from log import save_capture_image, write_log

RTSP_URL = "rtsp://admin:zlr151548@192.168.1.64:554/Streaming/Channels/102"


"""
作用：打开 RTSP 视频流，成功返回视频流对象，失败抛出异常。
"""
def initialize_rtsp_video_stream():
    # 第一步：按配置地址打开 RTSP 视频流。
    video_capture = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
    if not video_capture.isOpened():
        raise RuntimeError("RTSP 视频流打开失败")

    # 第二步：打开成功后返回视频流对象。
    write_log("初始化", "RTSP 视频流初始化完成")
    return video_capture


"""
作用：从已经打开的 RTSP 视频流中抓取一帧图像，成功返回 frame，失败返回 None。
"""
def capture_frame_from_rtsp(video_capture):
    # 第一步：从已经初始化好的 RTSP 视频流中读取当前帧。
    ret, frame = video_capture.read()
    if not ret or frame is None:
        write_log("识别", "RTSP 取帧失败")
        return None

    # 第二步：取帧成功后立即保存当前图片。
    save_capture_image(frame)

    # 第三步：返回当前帧给后续识别流程。
    write_log("识别", "RTSP 取帧成功")
    return frame
