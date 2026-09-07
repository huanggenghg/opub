# opub 许可服务部署手册

`license_server/` 是只部署在服务器上的私有激活服务，不会进入 opub 的 wheel 或
sdist。生产地址使用现有阿里云服务器上的 `https://dachitech.xyz/license`。

公网只开放一个接口：

| 方法与路径 | 用途 |
| --- | --- |
| `POST /v1/code-activations` | 将一个爱发电激活码绑定到首次兑换的设备并返回签名许可 |

没有公网管理、库存查询、重签或文档接口。库存管理仅通过服务器本地命令完成。

## 1. 四个服务环境变量

服务只读取以下四项。将它们写入 `/etc/opub-license.env`，文件所有者设为
`opub-license:opub-license`，权限设为 `0600`：

```bash
OPUB_PUBLIC_BASE_URL=https://dachitech.xyz/license
OPUB_LICENSE_PRIVATE_KEY=<base64 编码的 32 字节 Ed25519 私钥种子>
OPUB_LICENSE_KEY_ID=opub-license-2026-09
OPUB_LICENSE_DB_PATH=/opt/opub/license_server/data/license.sqlite3
```

私钥只能保存在服务器环境文件和加密离线备份中，不得进入 Git、日志、聊天记录或
发行包。数据库目录只能由 `opub-license` 服务用户写入。

## 2. 首次安装与密钥生成

将项目部署到 `/opt/opub` 后，在服务器上安装服务：

```bash
sudo apt-get update
sudo apt-get install -y python3-venv sqlite3
sqlite3 --version
sudo useradd --system --home /opt/opub --shell /usr/sbin/nologin opub-license
sudo mkdir -p /opt/opub/license_server/data /var/backups/opub-license
sudo chown -R opub-license:opub-license /opt/opub /var/backups/opub-license
cd /opt/opub
sudo -u opub-license python3 -m venv .venv
sudo -u opub-license .venv/bin/python -m pip install -r license_server/requirements.txt
sudo install -o opub-license -g opub-license -m 600 /dev/null /etc/opub-license.env
```

首次上线时在受信任环境生成一对密钥，并同时生成客户端公开配置：

```bash
.venv/bin/python -m license_server.keygen \
  --private-file .secrets/license-ed25519-private.b64 \
  --client-file publish/licensing/deployment.py \
  --base-url https://dachitech.xyz/license \
  --purchase-url https://afdian.com/item/69bf71f0a9f511f1bc065254001e7c00 \
  --key-id opub-license-2026-09
```

私钥文件权限为 `0600`。把其中唯一一行写入服务器环境文件的私钥项；客户端配置只
包含公开 URL、产品标识和公钥，可以随 opub 发布。妥善保存私钥的加密离线备份；
丢失私钥将无法继续签发许可，泄露私钥将允许伪造许可。

## 3. systemd 与 Caddy

安装并启动单进程服务：

```bash
sudo cp license_server/deploy/opub-license.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now opub-license
sudo systemctl status opub-license
```

必须保持一个 worker。兑换的一致性由 SQLite 事务保障，但限流窗口保存在进程内；
增加 worker 会把限流拆成多份。服务仅监听 `127.0.0.1:8013`，公网入口由 Caddy
提供。将 `license_server/deploy/Caddyfile.example` 中的两个许可路由合并到现有
`dachitech.xyz` 站点块后，先检查再重载：

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy 只把外部 `/license/v1/code-activations` 改写为内部
`/v1/code-activations`。`/license` 下的其他路径统一返回 `404`，不能把服务根路径
或文档路径反向代理到公网。

## 4. 本地激活码库存

以下命令只能在服务器本地运行，并使用与服务相同的数据库路径。正式库存只能在确认
部署配置和备份后生成：

```bash
cd /opt/opub
sudo -u opub-license env \
  OPUB_LICENSE_DB_PATH=/opt/opub/license_server/data/license.sqlite3 \
  .venv/bin/python -m license_server.codes generate \
  --count 100 \
  --output /opt/opub/license_server/data/afdian-codes.txt

sudo -u opub-license env \
  OPUB_LICENSE_DB_PATH=/opt/opub/license_server/data/license.sqlite3 \
  .venv/bin/python -m license_server.codes stats
```

库存工具只需要 `OPUB_LICENSE_DB_PATH`。不要读取或批量导出服务环境文件，避免把
签名私钥传给不需要它的子进程。

`generate` 会以 `0600` 权限创建新文件，文件已存在时拒绝覆盖，同时只把激活码哈希
写入 SQLite。`stats` 只输出 `available`、`redeemed` 和 `total` 数量，不输出激活
码、设备哈希或许可内容。生成后确认 `available` 与文件行数一致。

明文库存文件是一次性商品库存，必须遵守：

1. 通过受保护的管理连接下载或直接从受信任浏览器上传到爱发电商品的随机激活码发放设置。
2. 一行一个激活码，不编辑、不排序、不复制到剪贴板工具、工单或聊天软件。
3. 不执行会打印文件内容的命令，不把命令跟踪或调试日志打开。
4. 绝不提交 Git，也不放入 wheel、sdist、普通云盘或公开备份。
5. 爱发电确认接收且数量一致后，将本地明文移入加密离线存档或安全销毁；数据库只保留哈希。

## 5. 备份与恢复

SQLite 处于 WAL 模式。在线备份必须使用 SQLite 的备份命令，不能在服务写入时直接
复制活动数据库：

```bash
sudo -u opub-license sqlite3 /opt/opub/license_server/data/license.sqlite3 \
  ".backup '/var/backups/opub-license/license-$(date +%F).sqlite3'"
sudo -u opub-license sqlite3 /var/backups/opub-license/license-$(date +%F).sqlite3 \
  'PRAGMA integrity_check;'
```

以上命令依赖系统提供 `sqlite3 CLI`。每日执行并保留至少 30 天；备份与私钥分开加密保存。恢复前先在副本上运行
`PRAGMA integrity_check`。正式恢复时停止服务，将验证通过的备份安装为
`/opt/opub/license_server/data/license.sqlite3`（所有者
`opub-license:opub-license`、权限 `0600`），再启动服务并运行下方空 JSON
冒烟测试。不要用生产激活码做恢复验证。

```bash
sudo systemctl stop opub-license
sudo sqlite3 /var/backups/opub-license/license-YYYY-MM-DD.sqlite3 \
  'PRAGMA integrity_check;'

restore_stamp=$(date +%Y%m%dT%H%M%S)
rollback_dir=/var/backups/opub-license/pre-restore-$restore_stamp
restore_tmp=/opt/opub/license_server/data/.license.sqlite3.restore-$restore_stamp
sudo install -d -o opub-license -g opub-license -m 700 "$rollback_dir"
sudo install -o opub-license -g opub-license -m 600 \
  /var/backups/opub-license/license-YYYY-MM-DD.sqlite3 \
  "$restore_tmp"
sudo -u opub-license sqlite3 "$restore_tmp" 'PRAGMA integrity_check;'

sudo mv /opt/opub/license_server/data/license.sqlite3 \
  "$rollback_dir/license.sqlite3"
if sudo test -e /opt/opub/license_server/data/license.sqlite3-wal; then
  sudo mv /opt/opub/license_server/data/license.sqlite3-wal \
    "$rollback_dir/license.sqlite3-wal"
fi
if sudo test -e /opt/opub/license_server/data/license.sqlite3-shm; then
  sudo mv /opt/opub/license_server/data/license.sqlite3-shm \
    "$rollback_dir/license.sqlite3-shm"
fi
sudo mv "$restore_tmp" /opt/opub/license_server/data/license.sqlite3
sudo systemctl start opub-license
```

`restore_tmp` 与正式数据库位于同一文件系统，最后一次 `mv` 是原子替换。若安装或
启动失败，保持服务停止，把当前数据库移入该唯一时间戳目录，再将其中保存的
`license.sqlite3` 及存在的 `-wal`、`-shm` 文件逐个移回数据目录，随后重新启动服务。
不要删除该回滚目录，直到恢复后的数据库完成完整性检查和冒烟测试。

## 6. 无敏感数据冒烟测试

每次部署或恢复后运行：

```bash
curl -sS -o /dev/null -w '%{http_code}\n' \
  -X POST https://dachitech.xyz/license/v1/code-activations \
  -H 'content-type: application/json' \
  --data '{}'
```

预期输出 `422`。这同时证明 TLS、Caddy 路由、路径改写和请求校验已生效，而且没有
发送激活码。若不是 `422`，先查看 `systemctl status opub-license` 和 Caddy 日志；
排查时仍不得记录请求体、激活码、设备哈希、私钥或许可内容。

## 7. 上线检查

- 服务环境文件恰好包含上面的四项，权限与所有者正确。
- systemd 只有一个 worker，监听回环地址，Caddy 只开放兑换路径。
- 数据库和私钥已有可恢复的加密备份。
- 生成库存前已确认爱发电随机激活码发放格式和商品设置。
- 明文库存不在 Git、日志、聊天记录、发行包或普通备份中。
- 退款后无法吊销已经签发并可离线使用的许可；商品说明必须明确这一点。

本手册只描述部署流程。不要在开发、测试或文档更新任务中生成生产码、部署服务、
上传库存或发布软件。
