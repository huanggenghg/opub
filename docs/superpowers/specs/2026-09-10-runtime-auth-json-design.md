# 发布环境、登录错误与 JSON 输出

用户已确认实施评估中的第 1、3、4 项。本次保留文本输出和原有退出码，不引入发布记录或并发发布。

## 环境

以 pyproject.toml 为依赖源，requirements.txt 仅引用本项目。添加 video 可选依赖（MoviePy 2 和 Pillow）。发布预检只检查依赖与浏览器，不执行安装。独立 `opub --repair-env` 使用当前解释器修复核心依赖并安装 Chromium；`--with-video` 仅用于该命令。保持源码和 wheel 安装一致。

## 登录

保留 cookie_auth 的布尔接口：True 表示检测通过，False 只用于账号文件缺失或有明确登录页/失效证据。网络、页面无法识别、依赖/浏览器故障用结构化异常上抛；编排映射稳定错误码，不触发扫码、不报告账号异常。保留已有“上传前明确失效才可自动重试一次”的限制。

## JSON

新增 `--output text|json`，默认 text。JSON 模式 stdout 只输出一份 schema_version=1 的文档；进度、第三方输出和日志写 stderr。结果含 exit_code、summary、results、errors；每项包含素材、平台、success、message、error_code、result_url、result_id、safe_to_retry。缺省重试权限为 false。结果逐平台采集，后续异常仍保留已完成项。配置、环境和许可错误也进入文档。不依赖解析中文日志。

## 验证

先写失败测试，覆盖只读预检、修复命令隔离、安装元数据、登录异常不扫码、明确失效扫码、JSON 成败混合/配置/许可/意外异常与输出隔离。运行相关回归和包构建测试，不执行真实发布或付费激活。
