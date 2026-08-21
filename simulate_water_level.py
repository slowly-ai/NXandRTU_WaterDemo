"""
模拟水位模块：
1. 保留正式 RTSP 取流流程
2. 不执行真实 AI 水位识别
3. 直接返回固定模拟水位值
"""

from log import write_log

SIMULATED_LEVEL_CM = 58.8


"""
作用：返回固定模拟水位值，供主函数在调试阶段直接调用。
"""
def run_simulated_water_level_detection():
    # 第一步：直接使用预设的模拟水位值。
    write_log("识别", f"当前使用模拟水位 | {SIMULATED_LEVEL_CM:.2f} cm")

    # 第二步：把模拟值返回给主流程继续走 Modbus 通信。
    return SIMULATED_LEVEL_CM
