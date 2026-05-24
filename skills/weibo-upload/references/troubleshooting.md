# 微博故障排查

## 找不到 `sau` 命令

先确认是否已安装：

```bash
pip install hgeng-sau>=0.2.4
```

开发模式：

```bash
uv pip install -e .
```

环境检查：

```bash
sau status
```

## cookie 无效或已过期

重新登录：

```bash
sau login --platform weibo --account <account>
```

## 发布后审核超时

微博发布后会自动轮询审核状态（最长约 150 秒）。如果超时：

- 检查微博视频管理页面是否需要人工确认
- 确认视频内容是否符合微博发布规范
- 可稍后手动检查视频管理页面

## 内容声明选择失败

微博上传时会自动选择"内容无需标注"。如果选择失败：

- 可能是微博页面结构变更
- 检查 `uploader/weibo_uploader/main.py` 中的声明选择逻辑是否需要更新

## 登录二维码问题

- 优先使用 CLI 生成的本地二维码图片
- agent 应直接把图片展示/发送给用户扫码，不要只回传路径