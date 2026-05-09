# -*- coding: utf-8 -*-
"""
项目配置文件
用户可根据需要修改以下配置项
"""
from pathlib import Path

# 项目根目录（自动获取，无需修改）
BASE_DIR = Path(__file__).parent.resolve()

# XHS 服务器地址（仅小红书相关流程使用）
XHS_SERVER = "http://127.0.0.1:11901"

# 本地 Chrome 浏览器路径（可选）
# 示例: "C:/Program Files/Google/Chrome/Application/chrome.exe"
# 留空则使用系统默认浏览器或 Playwright 内置浏览器
LOCAL_CHROME_PATH = ""

# 是否使用无头模式运行浏览器
# True: 后台运行，不显示浏览器窗口
# False: 显示浏览器窗口，便于调试
LOCAL_CHROME_HEADLESS = True

# 调试模式
# True: 输出详细日志，便于排查问题
# False: 只输出关键信息
DEBUG_MODE = True

# ============ 多模态模型配置 ============
# 智谱 AI GLM-4V 视觉模型配置（用于视频内容分析）
# 注册地址: https://bigmodel.cn/
# API Key 获取: https://bigmodel.cn/user/apikey
ZHIPU_API_KEY = ""  # 智谱 AI API Key

# 视觉模型名称（可选: glm-4v, glm-4v-plus）
ZHIPU_VISION_MODEL = "glm-4v-flash"
