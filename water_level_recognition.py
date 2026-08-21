"""
水位识别算法模块：
1. 参数设置
2. 推理引擎初始化
3. 水位识别计算
"""

from ultralytics import YOLO

MODEL_PATH = "/home/jetson/models/new_demo/best.engine"
CONF_LEVEL = 0.4
PHYSICAL_OFFSET_CM = 2.75
ALPHA = 1.002846
BETA = 0.264446
MIN_LEVEL_CM = -20.0
MAX_LEVEL_CM = 120.0
USE_ELEVATION = False
BASE_ELEVATION = 1950.0
CLASS_WATER_LINE = 0
CLASS_GAUGE = 1
MODEL_NAMES = {
    0: "water_line",
    1: "gauge",
    2: "10",
    3: "9",
    4: "8",
    5: "7",
    6: "6",
    7: "5",
    8: "4",
    9: "3",
    10: "2",
    11: "1",
}


"""
作用：加载水位识别推理引擎，成功返回模型对象，失败抛出异常。
"""
def initialize_water_level_model():
    # 第一步：加载 TensorRT 推理引擎。
    model = YOLO(MODEL_PATH, task="pose")

    # 第二步：补齐类别名称映射，供后续识别使用。
    if not hasattr(model, "names") or not isinstance(model.names, dict):
        model.names = {}
    model.names.update({index: str(index) for index in range(1000)})
    model.names.update(MODEL_NAMES)

    # 第三步：返回已经初始化完成的模型对象。
    return model


"""
作用：对输入图像执行一次水位识别，成功返回浮点型水位，失败返回状态字符串。
"""
def run_water_level_detection(model, frame):
    try:
        # 第一步：对当前图像执行一次模型推理。
        results = model.predict(
            frame,
            conf=CONF_LEVEL,
            save=False,
            verbose=False,
            task="pose",
        )
    except Exception as exc:
        return f"模型推理异常: {exc}"

    for result in results:
        if result.boxes is None or len(result.boxes) == 0:
            return "未识别到目标"

        gauge_idx = (result.boxes.cls == CLASS_GAUGE).nonzero(as_tuple=False).flatten()
        water_line_idx = (result.boxes.cls == CLASS_WATER_LINE).nonzero(as_tuple=False).flatten()
        if len(gauge_idx) == 0:
            return "未识别到水尺"
        if len(water_line_idx) == 0:
            return "未识别到水线"

        # 第二步：提取水线位置，并收集所有刻度数字的位置和数值。
        water_box = result.boxes.xyxy[int(water_line_idx[0])].cpu().numpy()
        water_y = float(water_box[3])
        digit_points = []

        for box in result.boxes:
            class_id = int(box.cls[0])
            if class_id < 2:
                continue
            digit_value = float(model.names.get(class_id, str(class_id)))
            digit_points.append(
                {
                    "y": float(box.xywh[0][1]),
                    "val": digit_value,
                }
            )

        if len(digit_points) < 2:
            return f"有效刻度数字不足: {len(digit_points)}"

        digit_points.sort(key=lambda item: item["y"])

        first_high_digit_index = -1
        for index, item in enumerate(digit_points):
            if item["val"] in (8.0, 9.0):
                first_high_digit_index = index
                break

        # 第三步：把识别到的刻度数字换算成物理刻度值。
        calibrated_points = []
        for index, item in enumerate(digit_points):
            value = item["val"]
            if first_high_digit_index != -1 and index < first_high_digit_index:
                if value == 0.0:
                    value = 10.0
                elif value == 1.0:
                    value = 11.0

            physical_cm = value * 10.0
            if index == len(digit_points) - 1 and item["val"] == 10.0 and first_high_digit_index == -1:
                physical_cm = 0.0

            calibrated_points.append(
                {
                    "y": item["y"],
                    "phys": physical_cm + PHYSICAL_OFFSET_CM,
                }
            )

        # 第四步：筛选水线以上的有效参考刻度。
        above_line = [item for item in calibrated_points if item["y"] < water_y]
        valid_reference = []

        if len(above_line) >= 2:
            valid_reference.append(above_line[0])
            for item in above_line[1:]:
                prev_item = valid_reference[-1]
                dy = item["y"] - prev_item["y"]
                dv = prev_item["phys"] - item["phys"]
                if dy <= 0:
                    continue

                scale = dv / dy
                if len(valid_reference) == 1:
                    if 0 < dv <= 25:
                        valid_reference.append(item)
                else:
                    ref_dy = valid_reference[-1]["y"] - valid_reference[-2]["y"]
                    ref_dv = valid_reference[-2]["phys"] - valid_reference[-1]["phys"]
                    ref_scale = ref_dv / ref_dy
                    if ref_scale != 0 and 0.5 < (scale / ref_scale) < 1.5:
                        valid_reference.append(item)
        else:
            valid_reference = above_line

        # 第五步：根据参考刻度和水线位置计算最终水位。
        if len(valid_reference) >= 2:
            near_point = valid_reference[-1]
            far_point = valid_reference[-2]
            pixel_to_cm = (far_point["phys"] - near_point["phys"]) / (near_point["y"] - far_point["y"])
            estimated_level_cm = near_point["phys"] - (water_y - near_point["y"]) * pixel_to_cm
        elif len(valid_reference) == 1:
            estimated_level_cm = valid_reference[0]["phys"] - (water_y - valid_reference[0]["y"]) * 0.12
        else:
            return "没有有效参考刻度"

        final_cm = (estimated_level_cm * ALPHA) + BETA
        final_cm = max(MIN_LEVEL_CM, min(MAX_LEVEL_CM, final_cm))
        if USE_ELEVATION:
            return round(BASE_ELEVATION + final_cm / 100.0, 3)
        return round(final_cm, 2)

    return "未处理的识别结果"
