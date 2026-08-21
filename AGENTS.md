# NXandRTU_WaterDemo 项目说明

## 1. 项目定位

本项目运行在 Jetson Orin NX 开发板上，目标是完成一套按绝对时间循环执行的水位监测流程，核心链路包括：

- RTSP 视频取流
- 水尺水位识别
- Modbus RTU 从站通信
- 基于硬件 RTC 的整 5 分钟唤醒与 SC7 深度休眠

当前项目目录为：

- `G:\Obsidian\workspace\raw\项目\水位监测项目\NXandRTU_WaterDemo`

## 2. 当前代码结构

- `main.py`
  - 主入口
  - 串联整轮周期流程：首轮对齐、初始化、识别、监听主站读取、休眠唤醒

- `cycle_init.py`
  - 单轮初始化总入口
  - 负责在初始化时间窗内依次初始化：
    - Modbus 串口
    - RTSP 视频流
    - 水位识别模型

- `wake_up.py`
  - 休眠唤醒模块
  - 负责：
    - 计算下一轮整 5 分钟绝对时间
    - 在周期内等待到指定阶段时间点
    - 调用 `rtcwake` 进入 `SC7`

- `modbus.py`
  - Modbus RTU 从站基础模块
  - 负责：
    - 打开 `/dev/modbus_485`
    - 维护本地寄存器
    - 监听主站请求
    - 校验请求帧并回发响应帧

- `rtsp.py`
  - RTSP 视频流模块
  - 负责：
    - 打开 RTSP 视频流
    - 抓取一帧图像
    - 保存当前抓拍图片

- `water_level_recognition.py`
  - 水位识别算法模块
  - 负责：
    - 加载 TensorRT 推理引擎
    - 对单帧图像执行推理
    - 根据识别结果换算水位值

- `simulate_water_level.py`
  - 模拟水位模块
  - 调试阶段用于保留真实取流流程，但跳过真实算法，直接返回固定模拟值

- `log.py`
  - 日志与图像落盘模块
  - 负责：
    - 实时打印日志
    - 强制刷盘日志
    - 保存抓拍图片

## 3. 当前主流程

当前程序按单轮周期运行，默认周期为 5 分钟。

### 3.1 首轮启动

- 程序启动后，不立即进入业务
- 先对齐到下一个整 5 分钟时间点
- 对齐完成后开始第一轮业务

### 3.2 单轮周期

单轮流程如下：

1. 周期开始
   - 记录周期起点日志

2. 初始化阶段
   - 时间窗：`T+0s ~ T+15s`
   - 初始化内容：
     - Modbus 串口
     - RTSP 视频流
     - 推理引擎

3. 识别阶段
   - 时间窗：`T+15s ~ T+30s`
   - 当前先执行 RTSP 取帧
   - 成功取帧后：
     - 现在默认走模拟水位
     - 真实算法识别代码还保留在 `main.py` 中，但默认被注释

4. 通信阶段
   - 时间窗：`T+30s ~ T+45s`
   - Jetson 作为 Modbus RTU 从站监听主站请求
   - 收到一次有效读请求后立即回复并结束监听
   - 超时则记录日志

5. 休眠阶段
   - 释放视频流和串口
   - 计算下一轮整 5 分钟时间
   - 调用硬件 RTC 进入 `SC7`

### 3.3 异常处理原则

- 主流程异常不会直接跳过资源释放
- 资源释放与休眠逻辑放在 `finally` 中
- 如果 `rtcwake` 失败，当前程序会记录异常并退出，不再用软件等待替代硬件休眠

## 4. 当前默认配置

### 4.1 周期时间配置

定义在 `wake_up.py`：

- `CYCLE_SECONDS = 300`
- `INIT_STAGE_END_SECONDS = 15`
- `MODBUS_LISTEN_START_SECONDS = 30`
- `MODBUS_LISTEN_END_SECONDS = 45`
- `RTC_DEVICE_PATH = "/dev/rtc0"`

含义：

- 周期长度为 300 秒，即整 5 分钟
- 前 15 秒用于初始化
- 30 秒开始监听 RTU
- 45 秒结束监听

### 4.2 Modbus 配置

定义在 `modbus.py`：

- 串口设备：`/dev/modbus_485`
- 波特率：`9600`
- 校验位：`N`
- 数据位：`8`
- 停止位：`1`
- 从站地址：`5`
- 功能码：`0x03`
- 起始寄存器地址：`0`

本地寄存器结构：

- `寄存器 0`：水位高 16 位
- `寄存器 1`：水位低 16 位
- `寄存器 2`：ready 标志
- `寄存器 3`：state 状态码

状态码：

- `0`：空闲
- `1`：测量中
- `2`：数据准备成功
- `3`：数据准备失败

### 4.3 RTSP 配置

定义在 `rtsp.py`：

- `RTSP_URL = "rtsp://admin:zlr151548@192.168.1.64:554/Streaming/Channels/102"`

### 4.4 模型配置

定义在 `water_level_recognition.py`：

- `MODEL_PATH = "/home/jetson/models/new_demo/best.engine"`
- 当前仍指向 Jetson 上旧目录名 `new_demo`
- 如果 Jetson 侧目录已经同步改名，需要同时检查这里是否要更新

其他识别参数包括：

- `CONF_LEVEL`
- `PHYSICAL_OFFSET_CM`
- `ALPHA`
- `BETA`
- `MIN_LEVEL_CM`
- `MAX_LEVEL_CM`
- `USE_ELEVATION`
- `BASE_ELEVATION`

### 4.5 模拟水位配置

定义在 `simulate_water_level.py`：

- `SIMULATED_LEVEL_CM = 58.8`

当前 `main.py` 默认使用这一模拟值，而不走真实算法输出。

## 5. 当前默认运行行为

当前 `main.py` 中，识别部分默认配置如下：

- 保留真实 RTSP 取流
- 保留真实模型加载能力
- 但识别结果默认来自：
  - `run_simulated_water_level_detection()`

真实算法调用这一行当前处于注释状态：

- `run_water_level_detection(model, frame)`

因此，当前代码更接近“真实取流 + 模拟水位 + 真实 Modbus 通信 + 真实休眠流程”的调试形态。

## 6. 日志与文件输出

### 6.1 日志

`log.py` 会将日志同时输出到：

- 终端
- `runtime_logs/` 目录下按天命名的日志文件

日志格式：

- `[YYYY-MM-DD HH:MM:SS] [阶段] 内容`

写日志后会立即：

- `flush`
- `fsync`

保证日志落盘，不走内存缓存。

### 6.2 图片

每次 RTSP 成功取帧后，都会保存当前图片到：

- `capture_images/`

图片命名格式：

- `2026-8-14_14:15:02.jpg`

## 7. 当前仓库情况

仓库已初始化为 Git 工程。

当前 `.gitignore` 已排除：

- `__pycache__/`
- `*.py[cod]`
- `.vscode/`
- `.idea/`
- `runtime_logs/`
- `capture_images/`
- `*.log`
- `*.engine`

说明：

- 当前忽略规则会排除 TensorRT 引擎文件
- 如果后续需要把 `.engine` 一并纳入版本管理，需要单独调整 `.gitignore`

## 8. 运行与部署注意事项

### 8.1 权限要求

涉及以下操作时，Jetson 侧通常需要足够权限：

- 访问 `/dev/rtc0`
- 执行 `rtcwake`
- 执行 `sudo rtcwake ...`
- 访问 `/dev/modbus_485`

当前 `wake_up.py` 的处理方式是：

- 如果不是 root，自动尝试执行：
  - `sudo -n rtcwake ...`

因此 Jetson 侧若要无人值守运行，需要预先处理好 `sudo` 免密码或以合适权限运行程序。

### 8.2 RTC 前提

程序依赖硬件 RTC 的绝对时间正确。

已知约束：

- 当前固定使用 `/dev/rtc0`
- 本项目不做动态 RTC 选择

### 8.3 串口设备前提

Modbus 设备路径固定为：

- `/dev/modbus_485`

这依赖 Jetson 上已经做好串口固定映射。

### 8.4 当前项目假设

本项目默认假设：

- 每轮资源都重新初始化
- 不继承上一轮硬件对象状态
- USB 转 485 在休眠唤醒后会重新枚举，因此每轮必须重新打开串口

## 9. 已知需要特别留意的点

### 9.1 模型路径仍是旧目录名

`water_level_recognition.py` 中：

- `MODEL_PATH = "/home/jetson/models/new_demo/best.engine"`

而当前项目名已经改为 `NXandRTU_WaterDemo`。  
如果 Jetson 侧模型目录也同步改名，这里需要一起改，否则模型加载会失败。

### 9.2 当前默认不是“真实识别”

`main.py` 当前默认启用的是模拟水位：

- `result = run_simulated_water_level_detection()`

不是：

- `result = run_water_level_detection(model, frame)`

如果后续切回真实识别，需要恢复这一行。

### 9.3 当前仓库历史中已包含缓存与编辑器文件

虽然现在已经加了 `.gitignore`，但从已有提交看，历史版本中已经提交过：

- `.vscode/settings.json`
- `__pycache__/...`

`.gitignore` 只能阻止未来继续跟踪新文件，不能自动从历史或索引中移除已经被跟踪的文件。

### 9.4 GPIO 唤醒方案尚未落地

当前代码仍然是：

- `RTC` 主唤醒
- `SC7` 深度休眠

GPIO 硬件唤醒、RTU 额外唤醒线、设备树或内核唤醒源配置，目前都还没有并入本项目代码。

## 10. 后续接手建议

如果后续继续开发，建议优先确认以下事项：

1. Jetson 侧模型路径是否已经和当前项目目录同步改名
2. 最终上线时是否继续使用模拟水位，还是切回真实识别
3. `/dev/modbus_485` 的 udev 固定映射是否已在目标板稳定生效
4. `/dev/rtc0` 是否始终为目标硬件 RTC 且时间可靠
5. 是否需要把仓库中已被跟踪的 `.vscode`、`__pycache__` 从 Git 索引里清理掉

## 11. 适合后续维护者的简短结论

这是一个“Jetson Orin NX + RTSP + AI 水位识别 + Modbus RTU + RTC 绝对时间休眠唤醒”的单轮周期式项目。

当前代码已经具备：

- 5 分钟绝对时间对齐
- 单轮初始化
- RTSP 取帧
- 模型加载
- Modbus RTU 从站回复
- 图片和日志落盘
- RTC 休眠唤醒

但当前默认仍处于调试形态：

- 真实取流
- 模型可初始化
- 水位值默认来自模拟模块

因此，后续修改前要先确认：

- 是继续调试链路
- 还是切回完整真实识别部署链路
