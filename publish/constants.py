# -*- coding: utf-8 -*-
"""发布流程共享常量"""

PLATFORM_NAMES = {
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "kuaishou": "快手",
    "bilibili": "B站",
    "tencent": "微信视频号",
    "baijiahao": "百家号",
    "tk": "TikTok",
    "weibo": "微博",
}

TITLE_LIMITS = {
    "douyin": 30,
    "xiaohongshu": 20,
    "kuaishou": 30,
    "bilibili": 80,
    "tencent": 30,
    "baijiahao": 30,
    "tk": 2200,
    "weibo": 2000,
}

PUBLISH_TASK_FIELD_DEFAULTS = {
    "common": {
        "content_type": "video",
        "convert_to_video": "false",
        "video_duration": "5",
        "title": "",
        "desc": "",
        "tags": "",
        "video_file": "",
        "images": "",
        "publish_strategy": "immediate",
        "publish_time": "",
        "start_from": "",
    },
    "platforms": {
        "enabled": "",
    },
}
