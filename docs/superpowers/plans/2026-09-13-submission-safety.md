# 平台提交安全实施计划

**Goal:** 完成用户选择的 1、2、3 项可靠性优化。
**Architecture:** 保留现有编排/上传分层；百家号最终提交只执行一次；B站 runtime 只执行本地程序，由显式修复负责安装。
**Tech Stack:** Python 3.9+、pytest、Patchright、subprocess。

- [ ] 百家号：在 tests/test_baijiahao_submission_safety.py 重现即时/定时提交重试和标题改写；修改 uploader/baijiahao_uploader/main.py，验证点击后异常不重复、截图失败可继续验证结果、缺按钮明确报错。
- [ ] B站执行：在 tests/test_bilibili_runtime.py / test_bilibili_uploader.py 添加缺程序/分阶段超时/成功后查询失败/事件循环响应测试，再修改 uploader/bilibili_uploader/runtime.py、main.py。require_biliup_binary() 只读；ensure_biliup_binary() 只供修复调用。
- [ ] CLI 集成：publish/runtime.py 增加 platform_runtime_preflight(platforms) 和 repair_environment(with_bilibili=False)；orchestrator.py 增加 --with-bilibili 严格参数组合检查，并在普通/恢复/预检的可执行平台上运行检查。先在 tests/test_platform_runtime_preflight.py 和 test_cli_improvements.py 建立失败测试。
- [ ] 文档与验收：更新 CLI、README 和技能说明中的 B站安装及超时契约；运行相关测试和全部 tests、license_server/tests，检查版本一致和打包，无真实发布。

执行采用 subagent-driven-development：B站 runtime/上传器作为独立子任务，其余由主代理完成，完成后对照规格与实际差异审查。已有用户确认覆盖以上常规实现选择，无需重复确认。
