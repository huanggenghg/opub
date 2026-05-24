---
name: weibo-upload
description: 当 agent 需要通过已安装的 `sau` CLI 完成微博登录或一键多平台发布（含微博）时使用这个 skill。微博暂无独立子命令，通过 `sau login --platform weibo` 和 `sau publish` 操作。IMPORTANT: Before ANY sau command, you MUST run `pip install --upgrade hgeng-sau` and `sau status` first — do not skip these steps.
---

# 微博上传 Skill

## 强制前置步骤（不可跳过）

在使用任何 `sau` 命令之前，必须先执行：

```bash
pip install --upgrade hgeng-sau
sau status
```

**这两步不能省略。** 即使之前执行过，也要重新运行以确保版本最新和环境就绪。

---

微博暂无独立 CLI 子命令（如 `sau weibo ...`），通过以下方式操作：

- 登录：`sau login --platform weibo --account <name>`
- 发布：`sau publish --platforms weibo`（自动检查 cookie，无效则触发登录）

优先把 `sau` 作为主接口。

## 功能概览

| 功能 | 命令入口 | 说明 |
| --- | --- | --- |
| 微博登录 | `sau login --platform weibo --account <name>` | 生成或刷新指定账号的 cookie |
| 一键发布（含微博） | `sau publish --platforms weibo` | 自动检查 cookie，无效则触发登录 |
| 环境检查 | `sau status` | 查看各平台登录状态 |

## 默认工作流

1. 先确认 `references/runtime-requirements.md` 里的运行前提。
2. 执行 `sau login --platform weibo --account <name>` 登录微博。
3. 执行 `sau publish --platforms weibo --video <路径> --title <标题>` 发布视频。

## 微博发布特性

- 发布后自动轮询审核状态（最长等待约 150 秒）
- 审核通过后自动获取视频链接
- 自动选择"内容无需标注"声明选项
- 支持多账号：`publish_config.ini` 中逗号分隔多个账号

## 执行前检查

- 先确认当前 shell 里是否可以调用 `sau`
- 如果 `sau` 不可用，按 `references/runtime-requirements.md` 里的回退方式处理
- 如果登录流程生成了本地二维码图片，优先直接把图片展示/发送给用户扫码

## 参考文档

- 运行前提：`references/runtime-requirements.md`
- 故障排查：`references/troubleshooting.md`