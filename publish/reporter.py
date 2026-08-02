# -*- coding: utf-8 -*-
"""发布信息打印:头部与结果汇总"""
from publish.constants import PLATFORM_NAMES


def print_header(params: dict):
    """打印发布信息头部"""
    content_type_name = "图文" if params["content_type"] == "note" else "视频"
    print("\n========== 多平台发布 ==========")
    print(f"内容类型: {content_type_name}")
    if params["content_type"] == "note" and params["convert_to_video"]:
        print("图文转视频: 是")
    print(f"标题: {params['title']}")
    if params["tags"]:
        print(f"标签: {params['tags']}")
    print(f"启用平台: {', '.join(params['enabled_platforms'])}")
    print()


def print_results(results: dict):
    """打印发布结果汇总"""
    print("\n========== 发布结果 ==========")
    for platform, result in results.items():
        platform_name = PLATFORM_NAMES.get(platform, platform)
        status = "✅ 成功" if result["success"] else f"❌ 失败: {result['message']}"
        print(f"{platform_name}: {status}")
