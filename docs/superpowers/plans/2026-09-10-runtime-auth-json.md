# 发布可靠性实施计划

**Goal:** 完成用户批准的依赖统一、登录错误分类和 JSON 输出。

**Architecture:** 环境功能在 runtime，登录分类在独立轻量模块，JSON 采集使用上下文隔离并由 CLI 边界输出；平台上传逻辑保持现有结构。

**Tech Stack:** Python >=3.9、unittest/pytest、Patchright、setuptools。

- [x] 环境：先在 test_runtime_preflight_errors.py / test_publish_engine.py 写预检不安装测试，再改 runtime.py、依赖文件及锁文件；CLI 接入 --repair-env / --with-video。
- [x] 登录：先写网络/页面/环境异常不扫码及有效/失效回归测试，再修改独立异常类型、基类与覆盖 cookie_auth 的平台；编排保留错误分类。
- [x] JSON：先写 CLI 输出解析和失败测试，再实现上下文结果采集、错误采集、stdout 隔离及 --output 参数。
- [x] 集成：补中文文档和技能接口说明；运行相关测试和包构建检查，审查差异，不执行真实发布。

执行范围限定为本次三个改进；保留用户未跟踪文件。使用实施子代理处理独立模块，主代理负责 CLI 集成和最终验证。

## 验证结果

- 回归：678 passed，70 subtests passed；1 项既有百家号上传超时测试因真实 300 秒重试等待而排除。
- 回归包含 wheel/sdist 打包检查、CLI、JSON 结果隔离、许可校验和各平台登录检查。
- `uv lock --check`、`git diff --check`、CLI `--help` 通过。
- 未执行真实发布、扫码登录、付费激活或实际环境修复安装。
- 交叉审查发现并修复：缺失 cryptography 导致修复入口无法启动、重复 output 参数错误丢失 JSON、uv 环境缺少 pip、微博二次校验丢失分类。后两项由主代理完成最终检查。
