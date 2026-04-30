# 微博发布功能设计

## 概述

为多平台统一发布系统添加微博发布支持，包括视频发布和图文发布功能。

## 需求

- 支持视频发布
- 支持图文发布（图片+文字）
- 支持立即发布和定时发布
- 集成到现有的 `publish_all.py` 统一发布流程

## 技术方案

### 发布入口

使用微博创作者中心 `https://media.weibo.com/` 作为发布入口，原因：
- 发布流程规范，适合自动化
- 支持视频和图文发布
- 支持定时发布功能

### 文件结构

```
uploader/
└── weibo_uploader/
    └── main.py          # 微博上传器主模块
```

### 核心类设计

#### WeiboVideo 类

视频发布器，继承 `BaseVideoUploader`。

```python
class WeiboVideo(BaseVideoUploader):
    def __init__(
        self,
        title: str,           # 视频标题/正文
        file_path: str,       # 视频文件路径
        tags: list,           # 话题标签
        publish_date: datetime | int,
        account_file: str,
        desc: str | None = None,  # 额外描述
        publish_strategy: str = "immediate",
    ):
        ...
```

主要方法：
- `upload_video_content(page)` - 上传视频文件
- `fill_content(page)` - 填写正文和话题
- `set_schedule_time(page, publish_date)` - 设置定时发布
- `main()` - 主入口

#### WeiboNote 类

图文发布器。

```python
class WeiboNote(BaseVideoUploader):
    def __init__(
        self,
        image_paths: list,    # 图片路径列表
        note: str,            # 微博正文
        tags: list,           # 话题标签
        publish_date: datetime | int,
        account_file: str,
        title: str | None = None,
        publish_strategy: str = "immediate",
    ):
        ...
```

主要方法：
- `upload_images(page)` - 上传图片
- `fill_content(page)` - 填写正文和话题
- `set_schedule_time(page, publish_date)` - 设置定时发布
- `main()` - 主入口

### 登录流程

微博创作者中心支持扫码登录：
1. 访问 `https://media.weibo.com/`
2. 检测登录状态，未登录则显示二维码
3. 用户扫码登录后保存 Cookie

### 发布流程

#### 视频发布

1. 访问视频发布页面
2. 上传视频文件，等待上传完成
3. 填写正文（标题+描述）
4. 添加话题标签（#话题#）
5. 设置定时发布（如需要）
6. 点击发布

#### 图文发布

1. 访问微博发布页面
2. 上传图片（最多 9 张）
3. 填写正文
4. 添加话题标签
5. 设置定时发布（如需要）
6. 点击发布

### 平台限制

| 项目 | 限制 |
|------|------|
| 正文长度 | 2000 字 |
| 图片数量 | 最多 9 张 |
| 视频大小 | 根据账号等级不同 |
| 话题标签 | 无明确限制 |

### 集成到 publish_all.py

1. 添加平台映射：
```python
PLATFORM_NAMES = {
    ...
    "weibo": "微博",
}

TITLE_LIMITS = {
    ...
    "weibo": 2000,  # 微博正文限制
}
```

2. 添加 `publish_to_weibo()` 函数

3. 更新 `publish_to_platform()` 分发逻辑

4. 更新 `publish_config.ini` 配置示例

## 实现步骤

1. 创建 `uploader/weibo_uploader/main.py`
   - 实现登录和 Cookie 管理
   - 实现 `WeiboVideo` 类
   - 实现 `WeiboNote` 类

2. 更新 `publish_all.py`
   - 添加微博平台支持

3. 更新 `publish_config.ini`
   - 添加微博配置项

4. 测试验证
   - 测试视频发布
   - 测试图文发布
   - 测试定时发布

## 风险和注意事项

1. **页面结构变化** - 微博页面可能更新，需要维护选择器
2. **登录验证** - 微博可能有安全验证，需要处理
3. **发布审核** - 微博内容可能需要审核，发布后不一定立即可见
