# 单设备统一数据目录设计

## 目标

opub 只面向同一设备、同一系统用户下运行的 Agent。所有 Agent 固定从用户目录下的 `.opub` 读取账号、许可证、发布记录和 B 站运行文件，不再根据源码目录或环境变量切换数据目录。

## 路径规则

运行时数据目录统一为 `Path.home() / ".opub"`。该表达式由操作系统解析：macOS 和 Linux 通常为 `/Users/<user>/.opub` 或 `/home/<user>/.opub`，Windows 为 `C:\Users\<user>\.opub`。代码不保存或拼接具体用户名。

`SAU_HOME` 不再参与路径解析。即使 Agent 的环境中遗留了该变量，opub 仍读取同一份 `~/.opub`。源码仓库中的 `.git` 也不再改变运行时目录。

## 数据范围

以下状态统一位于 `~/.opub`：

- `cookies/`：各平台账号状态；
- `license.json`：本机许可证；
- `publish-history.sqlite3`：发布记录和恢复保护；
- `tools/biliup/`：B 站本地运行文件；
- `config.json`、日志和生成文件。

## 兼容与迁移

旧安装版本来就使用 `~/.opub`，无需迁移。此前源码模式写入仓库根目录的数据只在本设备上做一次人工合并：按平台保留已验证且更新的账号文件；发布记录先备份，再按 `run_id` 和条目复合主键在单个 SQLite 事务中合并，最后执行完整性检查。旧目录保留作备份，但新版本不再读取。

## 验证

- 设置任意 `SAU_HOME` 后，`conf.BASE_DIR` 仍等于 `Path.home() / ".opub"`；
- 从源码目录和安装环境导入配置时得到同一路径；
- 许可模块与发布模块返回相同数据目录；
- WorkBuddy 沙箱和 Codex 对 `~/.opub` 的同一临时文件以及 SQLite DELETE/WAL 数据库完成交叉读写；
- 完整测试、构建、安装包冒烟测试通过。
