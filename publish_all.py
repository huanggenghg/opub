# -*- coding: utf-8 -*-
"""
多平台统一发布脚本
一次配置，发布到多个平台
"""
import asyncio
import configparser
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from conf import BASE_DIR as PROJECT_BASE_DIR

# 内容模板文件路径
CONTENT_TEMPLATES_FILE = BASE_DIR / "templates" / "content_templates.json"

# 平台名称映射
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

# 平台标题长度限制
TITLE_LIMITS = {
    "douyin": 30,
    "xiaohongshu": 20,
    "kuaishou": 30,
    "bilibili": 80,
    "tencent": 30,
    "baijiahao": 30,
    "tk": 150,
    "weibo": 2000,
}


def load_content_templates() -> list:
    """加载内容模板"""
    if CONTENT_TEMPLATES_FILE.exists():
        with open(CONTENT_TEMPLATES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("templates", [])
    return []


def fill_empty_content(title: str, desc: str) -> tuple:
    """如果标题或描述为空，从模板随机填充"""
    title_empty = not title or not title.strip()
    desc_empty = not desc or not desc.strip()

    if title_empty or desc_empty:
        templates = load_content_templates()
        if templates:
            random_template = random.choice(templates)
            if title_empty:
                title = random_template.get("title", "")
            if desc_empty:
                desc = random_template.get("desc", "")
            print(f"[AUTO] 标题/描述为空，已自动填充: {title}")

    return title, desc


def read_config(config_file: str = "publish_config.ini") -> dict:
    """读取配置文件"""
    config_path = BASE_DIR / config_file
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8")

    config = {
        "common": dict(parser["common"]),
        "platforms": dict(parser["platforms"]),
    }
    return config


def parse_config(config: dict) -> dict:
    """解析配置，处理字段格式"""
    common = config["common"]
    platforms = config["platforms"]

    # 解析启用平台
    enabled_platforms = [p.strip() for p in platforms.get("enabled", "").split(",") if p.strip()]

    # 解析标签
    tags = [t.strip() for t in common.get("tags", "").split(",") if t.strip()]

    # 解析图片路径
    images_str = common.get("images", "")
    images = [img.strip() for img in images_str.split(",") if img.strip()]

    # 解析发布时间
    publish_strategy = common.get("publish_strategy", "immediate")
    publish_time_str = common.get("publish_time", "").strip()
    publish_time = None
    if publish_strategy == "scheduled" and publish_time_str:
        try:
            publish_time = datetime.strptime(publish_time_str, "%Y-%m-%d %H:%M")
        except ValueError:
            print(f"⚠️ 发布时间格式错误: {publish_time_str}，将使用立即发布")
            publish_strategy = "immediate"

    # 解析描述内容，支持 \n 换行
    desc = common.get("desc", "").replace("\\n", "\n")

    # 解析标题
    title = common.get("title", "")

    # 如果标题或描述为空，从模板随机填充
    title, desc = fill_empty_content(title, desc)

    # 解析图文转视频配置
    convert_to_video = common.get("convert_to_video", "false").strip().lower() in ("true", "yes", "1")
    video_duration = float(common.get("video_duration", "5").strip() or 5)

    # 解析起始视频序号（用于断点续传）
    start_from = int(common.get("start_from", "1").strip() or 1)

    return {
        "content_type": common.get("content_type", "video"),
        "title": title,
        "desc": desc,
        "tags": tags,
        "video_file": common.get("video_file", ""),
        "images": images,
        "publish_strategy": publish_strategy,
        "publish_time": publish_time,
        "enabled_platforms": enabled_platforms,
        "platforms": platforms,
        "convert_to_video": convert_to_video,
        "video_duration": video_duration,
        "start_from": start_from,
    }


def get_video_files(video_path: str) -> list:
    """获取视频文件列表，支持文件夹或单个文件"""
    if not video_path:
        return []

    path = resolve_path(video_path)

    if os.path.isfile(path):
        # 单个文件
        return [path]

    if os.path.isdir(path):
        # 文件夹，获取所有视频文件
        video_extensions = ['.mp4', '.mov', '.mkv', '.avi', '.flv', '.mpeg', '.ogg', '.vob', '.webm', '.wmv', '.rmvb']
        video_files = []
        for file in os.listdir(path):
            file_lower = file.lower()
            if any(file_lower.endswith(ext) for ext in video_extensions):
                video_files.append(os.path.join(path, file))
        # 按文件名排序
        video_files.sort()
        return video_files

    return []


def truncate_title(title: str, platform: str) -> str:
    """根据平台限制截断标题"""
    limit = TITLE_LIMITS.get(platform, 50)
    if len(title) > limit:
        return title[:limit]
    return title


def resolve_path(file_path: str) -> str:
    """解析相对路径为绝对路径"""
    if not file_path:
        return ""
    path = Path(file_path)
    if path.is_absolute():
        return str(path)
    return str(BASE_DIR / file_path)


async def ensure_login(platform: str, account_file: str) -> bool:
    """确保平台已登录，未登录则触发登录流程"""
    account_file = resolve_path(account_file)

    if platform == "douyin":
        from uploader.douyin_uploader.main import douyin_setup
        return await douyin_setup(account_file, handle=True)
    elif platform == "xiaohongshu":
        from uploader.xiaohongshu_uploader.main import xiaohongshu_setup
        return await xiaohongshu_setup(account_file, handle=True)
    elif platform == "kuaishou":
        from uploader.ks_uploader.main import ks_setup
        return await ks_setup(account_file, handle=True)
    elif platform == "tencent":
        from uploader.tencent_uploader.main import tencent_setup
        return await tencent_setup(account_file, handle=True)
    elif platform == "baijiahao":
        from uploader.baijiahao_uploader.main import baijiahao_setup
        return await baijiahao_setup(account_file, handle=True)
    elif platform == "weibo":
        from uploader.weibo_uploader.main import weibo_setup
        return await weibo_setup(account_file, handle=True)
    else:
        return False


async def publish_to_douyin(params: dict) -> dict:
    """发布到抖音"""
    from uploader.douyin_uploader.main import DouYinVideo, DouYinNote

    account_file = resolve_path(params["account_file"])

    # 检查/触发登录
    if not await ensure_login("douyin", account_file):
        return {"success": False, "message": "抖音登录失败"}

    title = truncate_title(params["title"], "douyin")
    tags = params["tags"]
    publish_strategy = params["publish_strategy"]
    publish_time = params["publish_time"]
    content_type = params["content_type"]

    try:
        if content_type == "video":
            video_file = resolve_path(params["video_file"])
            if not video_file or not os.path.exists(video_file):
                return {"success": False, "message": f"视频文件不存在: {video_file}"}

            uploader = DouYinVideo(
                title=title,
                file_path=video_file,
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                desc=params["desc"],
                publish_strategy=publish_strategy,
            )
            await uploader.main()
            return {"success": True, "message": "发布成功"}
        else:
            images = params["images"]
            if not images:
                return {"success": False, "message": "图文模式需要提供图片"}

            image_paths = [resolve_path(img) for img in images]
            for img_path in image_paths:
                if not os.path.exists(img_path):
                    return {"success": False, "message": f"图片文件不存在: {img_path}"}

            uploader = DouYinNote(
                image_paths=image_paths,
                note=params["desc"],
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                title=title,
                publish_strategy=publish_strategy,
            )
            await uploader.douyin_upload_note()
            return {"success": True, "message": "发布成功"}
    except Exception as e:
        return {"success": False, "message": str(e)}


async def publish_to_xiaohongshu(params: dict) -> dict:
    """发布到小红书"""
    from uploader.xiaohongshu_uploader.main import XiaoHongShuVideo, XiaoHongShuNote

    account_file = resolve_path(params["account_file"])

    # 检查/触发登录
    if not await ensure_login("xiaohongshu", account_file):
        return {"success": False, "message": "小红书登录失败"}

    title = truncate_title(params["title"], "xiaohongshu")
    tags = params["tags"]
    publish_strategy = params["publish_strategy"]
    publish_time = params["publish_time"]
    content_type = params["content_type"]

    try:
        if content_type == "video":
            video_file = resolve_path(params["video_file"])
            if not video_file or not os.path.exists(video_file):
                return {"success": False, "message": f"视频文件不存在: {video_file}"}

            uploader = XiaoHongShuVideo(
                title=title,
                file_path=video_file,
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                desc=params["desc"],
                publish_strategy=publish_strategy,
            )
        else:
            images = params["images"]
            if not images:
                return {"success": False, "message": "图文模式需要提供图片"}

            image_paths = [resolve_path(img) for img in images]
            for img_path in image_paths:
                if not os.path.exists(img_path):
                    return {"success": False, "message": f"图片文件不存在: {img_path}"}

            uploader = XiaoHongShuNote(
                image_paths=image_paths,
                note=params["desc"],
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                title=title,
                desc=params["desc"],
                publish_strategy=publish_strategy,
            )

        await uploader.main()
        return {"success": True, "message": "发布成功"}
    except Exception as e:
        return {"success": False, "message": str(e)}


async def publish_to_kuaishou(params: dict) -> dict:
    """发布到快手"""
    from uploader.ks_uploader.main import KSVideo, KSNote

    account_file = resolve_path(params["account_file"])

    # 检查/触发登录
    if not await ensure_login("kuaishou", account_file):
        return {"success": False, "message": "快手登录失败"}

    title = truncate_title(params["title"], "kuaishou")
    tags = params["tags"]
    publish_strategy = params["publish_strategy"]
    publish_time = params["publish_time"]
    content_type = params["content_type"]

    try:
        if content_type == "video":
            video_file = resolve_path(params["video_file"])
            if not video_file or not os.path.exists(video_file):
                return {"success": False, "message": f"视频文件不存在: {video_file}"}

            uploader = KSVideo(
                title=title,
                file_path=video_file,
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                desc=params["desc"],
                publish_strategy=publish_strategy,
            )
        else:
            images = params["images"]
            if not images:
                return {"success": False, "message": "图文模式需要提供图片"}

            image_paths = [resolve_path(img) for img in images]
            for img_path in image_paths:
                if not os.path.exists(img_path):
                    return {"success": False, "message": f"图片文件不存在: {img_path}"}

            uploader = KSNote(
                image_paths=image_paths,
                note=params["desc"],
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                title=title,
                publish_strategy=publish_strategy,
            )

        await uploader.main()
        return {"success": True, "message": "发布成功"}
    except Exception as e:
        return {"success": False, "message": str(e)}


async def publish_to_tencent(params: dict) -> dict:
    """发布到微信视频号"""
    from uploader.tencent_uploader.main import TencentVideo

    account_file = resolve_path(params["account_file"])

    # 检查/触发登录
    if not await ensure_login("tencent", account_file):
        return {"success": False, "message": "微信视频号登录失败"}

    title = truncate_title(params["title"], "tencent")
    tags = params["tags"]
    publish_strategy = params["publish_strategy"]
    publish_time = params["publish_time"]
    content_type = params["content_type"]

    try:
        if content_type == "video":
            video_file = resolve_path(params["video_file"])
            if not video_file or not os.path.exists(video_file):
                return {"success": False, "message": f"视频文件不存在: {video_file}"}

            uploader = TencentVideo(
                title=title,
                file_path=video_file,
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                desc=params["desc"],
                publish_strategy=publish_strategy,
            )
        else:
            return {"success": False, "message": "微信视频号不支持图文发布，请使用 convert_to_video=true 转为视频发布"}

        await uploader.main()
        return {"success": True, "message": "发布成功"}
    except Exception as e:
        return {"success": False, "message": str(e)}


async def publish_to_baijiahao(params: dict) -> dict:
    """发布到百家号"""
    from uploader.baijiahao_uploader.main import BaiJiaHaoVideo

    account_file = resolve_path(params["account_file"])

    # 检查/触发登录
    if not await ensure_login("baijiahao", account_file):
        return {"success": False, "message": "百家号登录失败"}

    title = truncate_title(params["title"], "baijiahao")
    tags = params["tags"]
    publish_strategy = params["publish_strategy"]
    publish_time = params["publish_time"]
    content_type = params["content_type"]

    try:
        if content_type == "video":
            video_file = resolve_path(params["video_file"])
            if not video_file or not os.path.exists(video_file):
                return {"success": False, "message": f"视频文件不存在: {video_file}"}

            uploader = BaiJiaHaoVideo(
                title=title,
                file_path=video_file,
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
            )
        else:
            return {"success": False, "message": "百家号不支持图文发布，请使用 convert_to_video=true 转为视频发布"}

        await uploader.main()
        return {"success": True, "message": "发布成功"}
    except Exception as e:
        return {"success": False, "message": str(e)}


async def publish_to_weibo(params: dict) -> dict:
    """发布到微博"""
    from uploader.weibo_uploader.main import WeiboVideo, WeiboNote

    account_file = resolve_path(params["account_file"])

    # 检查/触发登录
    if not await ensure_login("weibo", account_file):
        return {"success": False, "message": "微博登录失败"}

    title = truncate_title(params["title"], "weibo")
    tags = params["tags"]
    publish_strategy = params["publish_strategy"]
    publish_time = params["publish_time"]
    content_type = params["content_type"]

    try:
        if content_type == "video":
            video_file = resolve_path(params["video_file"])
            if not video_file or not os.path.exists(video_file):
                return {"success": False, "message": f"视频文件不存在: {video_file}"}

            uploader = WeiboVideo(
                title=title,
                file_path=video_file,
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                desc=params["desc"],
                publish_strategy=publish_strategy,
            )
        else:
            images = params["images"]
            if not images:
                return {"success": False, "message": "图文模式需要提供图片"}

            image_paths = [resolve_path(img) for img in images]
            for img_path in image_paths:
                if not os.path.exists(img_path):
                    return {"success": False, "message": f"图片文件不存在: {img_path}"}

            uploader = WeiboNote(
                image_paths=image_paths,
                note=params["desc"],
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                title=title,
                publish_strategy=publish_strategy,
            )

        await uploader.main()
        return {"success": True, "message": "发布成功"}
    except Exception as e:
        return {"success": False, "message": str(e)}


async def publish_to_platform(platform: str, params: dict) -> dict:
    """发布到指定平台"""
    if platform == "douyin":
        return await publish_to_douyin(params)
    elif platform == "xiaohongshu":
        return await publish_to_xiaohongshu(params)
    elif platform == "kuaishou":
        return await publish_to_kuaishou(params)
    elif platform == "bilibili":
        return {"success": False, "message": "B站平台暂未实现"}
    elif platform == "tencent":
        return await publish_to_tencent(params)
    elif platform == "baijiahao":
        return await publish_to_baijiahao(params)
    elif platform == "tk":
        return {"success": False, "message": "TikTok平台暂未实现"}
    elif platform == "weibo":
        return await publish_to_weibo(params)
    else:
        return {"success": False, "message": f"未知平台: {platform}"}


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


async def main():
    """主函数"""
    try:
        config = read_config()
    except FileNotFoundError as e:
        print(f"❌ 错误: {e}")
        return

    params = parse_config(config)

    if not params["enabled_platforms"]:
        print("❌ 错误: 未配置启用平台")
        return

    if not params["title"]:
        print("❌ 错误: 未配置标题")
        return

    # 处理图文转视频
    if params["content_type"] == "note" and params["convert_to_video"]:
        if not params["images"]:
            print("❌ 错误: 图文转视频需要提供图片")
            return

        print("正在将图片转换为视频...")
        try:
            from utils.image_to_video import convert_images_to_video_for_publish

            video_path = convert_images_to_video_for_publish(
                image_paths=params["images"],
                title=params["title"],
                duration=params["video_duration"],
            )
            # 更新参数，切换为视频模式
            params["content_type"] = "video"
            params["video_file"] = video_path
            print(f"[OK] 视频已生成: {video_path}\n")
        except Exception as e:
            print(f"[ERROR] 图片转视频失败: {e}")
            return

    # 获取视频文件列表
    video_files = get_video_files(params["video_file"])
    if not video_files:
        print("❌ 错误: 未找到视频文件")
        return

    print(f"找到 {len(video_files)} 个视频文件:")
    for vf in video_files:
        print(f"  - {os.path.basename(vf)}")
    print()

    # 遍历每个视频文件进行发布
    all_results = {}
    start_from = params.get("start_from", 1)
    if start_from > 1:
        print(f"\n[SKIP] 从第 {start_from} 个视频开始发布（跳过前 {start_from - 1} 个）\n")

    for video_idx, video_file in enumerate(video_files, 1):
        # 跳过已发布的视频
        if video_idx < start_from:
            continue

        print(f"\n========== 视频 [{video_idx}/{len(video_files)}] ==========")
        print(f"文件: {os.path.basename(video_file)}")

        # 为每个视频随机生成新的标题和描述
        title, desc = fill_empty_content("", "")

        # 更新参数
        video_params = {
            **params,
            "video_file": video_file,
            "title": title,
            "desc": desc,
        }

        print_header(video_params)

        results = {}
        total = len(video_params["enabled_platforms"])

        for i, platform in enumerate(video_params["enabled_platforms"], 1):
            platform_name = PLATFORM_NAMES.get(platform, platform)
            print(f"[{i}/{total}] 发布到 {platform_name}...")

            # 获取账号文件
            account_key = f"{platform}_account"
            account_file = video_params["platforms"].get(account_key, "")

            platform_params = {
                **video_params,
                "account_file": account_file,
            }

            result = await publish_to_platform(platform, platform_params)
            results[platform] = result

            if result["success"]:
                print(f"  ✅ 成功")
            else:
                print(f"  ❌ 失败: {result['message']}")

        print_results(results)
        all_results[video_file] = results

    # 打印总体汇总
    print("\n========== 总体发布汇总 ==========")
    success_count = 0
    fail_count = 0
    for video_file, results in all_results.items():
        for platform, result in results.items():
            if result["success"]:
                success_count += 1
            else:
                fail_count += 1
    print(f"成功: {success_count} 次")
    print(f"失败: {fail_count} 次")

    print_results(results)


if __name__ == "__main__":
    asyncio.run(main())
