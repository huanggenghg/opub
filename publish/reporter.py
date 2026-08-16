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
        if result["success"]:
            status = "✅ 成功"
        else:
            error_code = result.get("error_code") or f"PUB-{platform.split('_')[0]}"
            status = f"❌ 失败 [{error_code}]: {result['message']}"
        print(f"{platform_name}: {status}")


def print_summary(all_results: dict) -> None:
    """打印总体发布汇总 + 账号异常反馈"""
    print("\n========== 总体发布汇总 ==========")
    success_count = sum(1 for results in all_results.values() for result in results.values() if result["success"])
    fail_count = sum(1 for results in all_results.values() for result in results.values() if not result["success"])
    print(f"成功: {success_count} 次")
    print(f"失败: {fail_count} 次")

    seen_issues = set()
    account_issues = []
    for results in all_results.values():
        for result_key, result in results.items():
            if not result.get("account_issue"):
                continue
            if result_key in seen_issues:
                continue
            seen_issues.add(result_key)
            platform_name = PLATFORM_NAMES.get(result_key.split("_")[0], result_key)
            account_issues.append((result_key, platform_name, result.get("message", "")))

    if account_issues:
        print("\n========== ⚠️ 账号异常反馈 ==========")
        for result_key, platform_name, message in account_issues:
            print(f"  [{result_key}] {platform_name}: {message}")
        print("\n以上账号可能已失效、被限制或登录异常，请前往对应平台检查账号状态，")
        print("必要时重新扫码登录或联系平台客服。")
