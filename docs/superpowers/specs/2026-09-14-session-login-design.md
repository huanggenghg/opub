# 发布会话内登录合并（每素材单浏览器）

目标：同一平台对同一素材的发布只启动一次浏览器；登录判定、扫码登录、上传、结果确认都在同一会话内完成，素材发布结束统一关闭。

已确认的范围决策：会话粒度为**每素材一次**（不做跨素材复用）；主线 6 个浏览器平台（douyin / xiaohongshu / kuaishou / tencent / baijiahao / weibo）全面改造；tk 被动继承基类、不专门验证、不修其已知 iframe bug；bilibili 走 biliup 子进程无浏览器，不涉及。

## 现状

`publish_one_item` 在上传前单独调 `ensure_account_login`：`cookie_auth` 自起一套浏览器导航判定；失效时 `cookie_gen` 再起一套扫码，扫码后 `_save_state_and_validate` 又起一套校验；上传时 `upload()` 的 `_browser_session` 再起一套。cookie 有效时每素材每平台 2 次浏览器冷启动，需扫码时最多 4 次；tencent 扫码与上传之间的新上下文存在 22 秒 session 失效窗口。各平台 `upload_video_content(page)` 均自带 `goto(UPLOAD_URL)`；浏览器默认有头（`chrome_headless` 缺省 False），扫码可直接在页面完成。

## 核心机制

登录状态机做进 `_browser_session` 的 `yield page` 之前，全部在同一浏览器、同一 context、同一 page 上：

1. `new_page()` 后 `goto(UPLOAD_URL, 60s, domcontentloaded)`，等待 3s（参数与现 `cookie_auth` 一致）。
2. 无登录证据且 URL 未被重定向走：直接 `yield page`（快路径，cookie 有效时全程 1 次浏览器）。
3. `is_login_required` 命中（登录标记或登录表单，即发布页上的真实失效证据）：stderr 打印扫码提醒（现 `dispatch.ensure_login` 的文案，抽共享 helper，Agent ≥360s 超时契约不变）→ `goto(LOGIN_URL)` 规范化导航 → 轮询 `is_login_completed`（3s × 100 次，上限 300s，与"最长约 5 分钟"契约一致）→ 完成后 `context.storage_state(account_file)` 立即落盘（后续上传失败也不丢登录）→ `goto(UPLOAD_URL)` 回发布页 → `yield page`。
4. 导航阶段网络/超时/环境异常经 `classify_login_exception` 抛 `LoginCheckError`（NET-001 / PAGE-001 / ENV-006）；扫码轮询阶段超时、浏览器被用户关闭或页面崩溃抛 `LoginTimeoutError`。两阶段划分：登录证据确立之前的不确定异常不触发扫码，确立之后的交互阶段中断视为定论性登录失败。

`upload_video_content` 自带的 goto 等同刷新一次表单（约 1-3s，接受，换取平台上传代码零改动）。退出侧（`save_on_success_only`、`save_state`）一字不动：tencent 仍不退出保存（防止衰减 session 覆盖完整 cookie）。`_save_state_and_validate` 里"再开浏览器校验新 cookie"的路径不再出现在发布主路径——活体会话中 `is_login_completed` 已返回 True，回到发布页的导航即最终校验。异常路径的 `finally` 保证 context/browser 照常关闭，不留孤儿进程。

## 错误契约

| 场景 | 异常 | dispatch 转换 | safe_to_retry |
| --- | --- | --- | --- |
| 导航阶段不确定失败（网络/超时/环境/非登录重定向） | `LoginCheckError`（复用 auth.py 现有分类） | `to_result()`（NET-001/PAGE-001/ENV-006） | False，不触发扫码 |
| 扫码超时 / 用户关闭浏览器 / 交互阶段页面崩溃 | `LoginTimeoutError`（auth.py 新增，定论性登录失败） | AUTH-001 结果 | True |
| 登录成功、上传失败 | 现有各平台 except / 结果分支 | 不变 | 不变 |

不变量：不确定失败不触发扫码、不自动重试；登录阶段异常发生在任何提交动作之前，`_submission_attempted` 必为 False，重复提交保护（RUN-004）语义不受影响。

## 编排层

- orchestrator 登录预检循环：浏览器平台整段跳过 `ensure_account_login`，登录由上传会话完成；仅 bilibili 保留预检（其 `cookie_auth` 为 biliup 查询子进程，无浏览器）。`platform_requires_account_login` 相应收窄。"未发现账号文件，将触发扫码登录"提示保留。
- orchestrator 中途失效重试（`_is_safe_login_expiry` 命中，如 tencent `_TencentPreMediaLoginExpired`）：改为直接重调一次 `publish_to_platform`——新会话的状态机自行完成重新登录——移除 `ensure_account_login(force=True)`。重试仍限一次；`safe_to_retry=True` 契约保证未发生提交，重试安全。重试路径从 2-3 次浏览器降到 1 次。
- dispatch：扫码提醒抽共享 helper（dispatch 与基类状态机共用同一文案）；`publish_to_platform` 统一包裹 `LoginCheckError` / `LoginTimeoutError` 转换为结果 dict，各 `publish_to_*` 内现有 `except LoginCheckError` 分支保留（先到先转，行为一致）。
- `cookie_auth` / `cookie_gen` / `ensure_login` / `ensure_account_login` 本体保留：bilibili 预检与独立登录路径仍在用，发布主路径不再经过。

## 平台层

6 平台各在 `upload()` except 链最前加一行 `except (LoginCheckError, LoginTimeoutError): raise` 放行：douyin / xiaohongshu / kuaishou / weibo 各 2 个调用点（video + note），baijiahao 1 个，tencent 2 个。登录异常发生在 `yield` 之前，不会落入平台通用 except 误判成 `PUB-xxx`，也不会触碰 `_submission_attempted` 分支。

tencent 补充：确认 `LOGIN_MARKERS` 覆盖 login.html 重定向（不足则补）；其 `is_login_completed` 为 DOM marker override，状态机直接复用；扫码后保存点（状态机内）与退出保存（`save_state=False` 禁用）天然分离。各平台类的 `UPLOAD_URL` / `LOGIN_URL` / `LOGIN_MARKERS` 类属性需对状态机可用（tencent 现用模块级常量，需对齐到类属性）。tk 被动继承。bilibili 无改动。

## 验证

先写失败测试再实现。状态机单元测试（fake page）：快路径不进登录流程、不打印扫码提醒；扫码路径完整（提醒 → 轮询 → 落盘 → 回导航 → yield）；扫码超时抛 `LoginTimeoutError` 且 dispatch 转 AUTH-001；goto 网络异常抛 `LoginCheckError` 且**不** `goto(LOGIN_URL)`（契约锁定）；非登录重定向报 PAGE-001 不扫码；扫码成功后上传失败 cookie 文件仍保留；退出保存规则（`save_on_success_only` / `save_state=False`）与现状一致。

改造现有测试：浏览器平台不再调 `ensure_account_login`、bilibili 仍调；中途失效重试改为重调 publish 而非 force 登录；dispatch 两类异常转换；平台层放行不被吞成 `PUB-xxx`。全量回归无真实账号或发布；需要时真实平台 e2e（建议 weibo，快路径 + 扫码路径各一次）。

## 发布

随 0.8.5 发布（工作区已 bump pyproject / SKILL / test_package_build；发布前 `uv lock` 同步 uv.lock）。SKILL.md / docs/CLI.md 登录流程措辞微调，对外行为不变（无账号文件仍自动弹浏览器扫码）。

## 非目标

tk iframe bug；bilibili 流程；跨素材会话复用；平台并行化；dry-run 行为；删除 `cookie_auth` / `cookie_gen`。
