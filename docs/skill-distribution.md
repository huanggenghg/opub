# Skill 分发与发布说明

这份文档记录当前仓库对 agent skill 的定位。

## 当前结论

当前主线不再维护旧命令，也不再维护按平台拆分的独立 CLI skill。

仓库只保留一个公开 CLI 工作流：

```bash
opub
```

对应的 agent skill 也只保留一个：

```text
skills/opub-cli/SKILL.md
```

## 为什么收敛

这个项目的核心使用场景已经收敛为“配置发布平台，然后执行统一发布流程”。

因此 skill 不应该继续把登录、校验、单平台上传拆成多个入口。那些入口会让 agent 在发布前先做一次独立校验，再要求用户确认发布，形成多余步骤。

当前职责划分是：

- `publish_config.ini` 负责声明平台、账号、素材、标题、简介、标签和定时发布。
- `opub` 负责读取配置、运行环境预检、账号登录校验、发布和结果汇总。
- `skills/opub-cli/SKILL.md` 负责告诉 agent 只使用统一入口。

## 分发方式

当前阶段 skill 随仓库维护，不通过 CLI 子命令安装，也不提供单独的 `skill install` 公共入口。

如果后续需要正式分发，可以选择：

- 继续随仓库提供 `skills/opub-cli/`。
- 在发布包中包含 `skills/opub-cli/` 资源。
- 独立维护一个只包含 `opub-cli` 的 skill 仓库。

无论采用哪种方式，都应保持 skill 文档和真实 CLI 契约一致：只有 `opub` 是公开主入口。

## 发布前检查

发布或交付前至少确认：

```bash
uv pip install -e .
opub --help
```

并扫描用户文档中是否仍出现旧入口关键字。

历史设计文档可以保留旧命名；当前用户文档和 skill 不应继续指导用户使用旧入口。
