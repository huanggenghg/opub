# 多平台统一发布功能设计

## 概述

实现一次内容配置，发布到多个平台的功能。基于现有各平台 uploader，通过统一配置文件和调度脚本实现。

## 目标

- 一个配置文件设置内容
- 一键发布到多个平台
- 输出发布结果汇总

## 支持平台

- 抖音 (douyin)
- 小红书 (xiaohongshu)
- 快手 (kuaishou)
- B站 (bilibili)
- 微信视频号 (tencent)
- 百家号 (baijiahao)
- TikTok (tk)

## 文件结构

```
social-auto-upload/
├── publish_config.ini      # 统一配置文件
├── publish_all.py          # 总调度脚本
├── cookies/                # 各平台 cookie（现有）
└── uploader/               # 各平台 uploader（现有）
```

## 配置文件设计

### `publish_config.ini`

```ini
[common]
# 内容类型: note=图文, video=视频
content_type = note

# 内容配置（所有平台共用）
title = 标题内容
desc = 描述内容，支持\n换行
tags = 标签1,标签2,标签3

# 文件路径（相对于项目根目录）
video_file = videos/demo.mp4
images = videos/a.png,videos/b.png

# 发布配置
publish_strategy = immediate    # immediate=立即发布, scheduled=定时发布
publish_time =                  # 定时发布时间，格式: YYYY-MM-DD HH:MM

[platforms]
# 启用的平台（逗号分隔）
enabled = douyin,xiaohongshu

# 各平台账号文件（默认路径，通常不需要修改）
douyin_account = cookies/douyin_uploader/account.json
xiaohongshu_account = cookies/xiaohongshu_uploader/account.json
kuaishou_account = cookies/ks_uploader/account.json
bilibili_account = cookies/bilibili_uploader/account.json
tencent_account = cookies/tencent_uploader/account.json
baijiahao_account = cookies/baijiahao_uploader/account.json
tk_account = cookies/tk_uploader/account.json
```

## 调度脚本设计

### `publish_all.py`

**功能：**
1. 读取 `publish_config.ini` 配置
2. 遍历 `enabled` 中的平台
3. 调用各平台现有 uploader 执行发布
4. 收集并输出发布结果汇总

**输出示例：**
```
========== 多平台发布 ==========
内容类型: 图文
标题: xxx
标签: [标签1, 标签2]
启用平台: douyin, xiaohongshu

[1/2] 发布到 抖音...
  ✅ 成功

[2/2] 发布到 小红书...
  ✅ 成功

========== 发布结果 ==========
抖音: ✅ 成功
小红书: ✅ 成功
```

## 平台差异处理

各平台有不同限制，脚本需处理：

| 平台 | 标题限制 | 标签限制 | 备注 |
|------|---------|---------|------|
| 抖音 | 30字 | - | - |
| 小红书 | 20字 | - | - |
| 其他 | - | - | 按平台自动截断 |

脚本自动截断超长标题，避免发布失败。

## 使用流程

1. 编辑 `publish_config.ini` 设置内容和启用平台
2. 确保各平台已登录（cookie 有效）
3. 运行 `python publish_all.py`
4. 查看发布结果

## 实现要点

1. 复用现有各平台 uploader，不修改其内部逻辑
2. 配置文件使用 INI 格式，简单易编辑
3. 错误处理：单个平台失败不影响其他平台继续发布
4. 结果汇总：清晰展示各平台发布状态
