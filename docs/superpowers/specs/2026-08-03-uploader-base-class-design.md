# Uploader 公共基类抽取设计

## 背景

8 个平台 uploader(douyin / xiaohongshu / kuaishou / tencent / baijiahao / bilibili / weibo / tk)各自独立实现了浏览器启动、context 创建、storage_state 保存、cookie 校验、QR 登录、参数校验等逻辑。5 个浏览器平台(douyin/xhs/ks/tencent/weibo)已经各自抽出 `*BaseUploader(BaseVideoUploader)` 中间层,但每个 `*BaseUploader` 又复制了同一份 launch/context/cookie_auth/cookie_gen/setup 代码 - 共约 400 行重复。

本 spec 是项目清洁架构重构的第二个子项目(sub-project B),承接 sub-project A(`publish_all.py` 拆分为 `publish/` 包,已完成合并到 main)。sub-project A 的 `publish/dispatch.py` 已把 8 个 `publish_to_*` 函数的入口统一,但每个函数内部仍要手写 result 提取(`result.get("share_link", "")` / `result.get("video_link", "")` 等)和异常映射 - 这部分重复留给 sub-project B 通过基类 + 统一返回契约解决。

后续 sub-project C(myUtils/utils 合并)、D(死代码清理)、E(配置约定统一)、F(前后端打通)各自独立 spec。

## 范围

**在范围内:**
- `uploader/base_video.py` 升级:加 `BasePlatformUploader` / `BaseBrowserUploader` / `BaseCliUploader` 三层基类、`PublishStrategy` enum、`PlatformResultExtras` TypedDict、`AccountRestrictedError` 异常
- 8 个平台 uploader 迁移到新基类(weibo / xiaohongshu / kuaishou / tencent / douyin / baijiahao / bilibili / tk)
- tk 从 firefox 迁移到 chromium + patchright,接入 `_PLATFORM_LOGIN` / `_PUBLISH_DISPATCH`
- `publish/dispatch.py` 8 个 `publish_to_*` 简化:删手写 result 提取,uploader 直接返回 `PlatformResultExtras`
- `publish/constants.py` 加 `"tk": 2200` 到 `TITLE_LIMITS`
- 新增测试:`test_base_uploader.py` / `test_base_uploader_login.py` / `test_base_uploader_session.py` / `test_tk_migration.py`
- 改写测试:`test_publish_dispatch.py` 加 tk 覆盖断言

**不在范围内(留给后续 spec):**
- `myUtils/` / `hgsau_backend.py` 完全不碰(sub-project C)
- 死代码清理:`probe_*.py`、`*_get_share_link.py`、`build/lib/`、`tk_uploader/main_chrome.py`、`baijiahao_uploader/main.py::ai2video`、`TencentNote` stub(sub-project D)
- Cookie 路径约定统一(快手异常路径)(sub-project E)
- `myUtils/postVideo.py` 的 `post_video_*` 函数批量调度逻辑( sub-project C 处理)
- 2-tier 结构 collapse(`*BaseUploader` 中间层保留,不合并到 `*Video`/`*Note`)
- baijiahao 定时发布按钮 bug(memory `project_baijiahao_scheduled_publish_button_bug.md` 记录,sub-project E 处理)
- tk 真实发布验证(需海外网络,manual smoke test 视环境而定)

## 架构

### 三层基类结构

升级 `uploader/base_video.py`(当前只有 validation-only 的 `BaseVideoUploader`),加三层基类:

```
BasePlatformUploader (uploader/base_video.py)
  abstract: cookie_auth, setup, upload
  shared: validate_video_file, validate_image_file, validate_publish_date,
          validate_base_args, PublishStrategy enum, PlatformResultExtras TypedDict,
          AccountRestrictedError
  ├── BaseBrowserUploader
  │     template classmethods: cookie_auth, setup, cookie_gen
  │     shared: _build_launch_kwargs, _init_context, _launch_browser,
  │            _save_storage_state, _browser_session (context manager),
  │            _msg, _build_login_result, _emit_qrcode_callback
  │     hooks (abstract / overridable): PLATFORM_NAME, UPLOAD_URL, LOGIN_URL,
  │            LOGIN_MARKERS, PUBLISH_MARKERS, extract_qrcode_src(page),
  │            is_login_completed(page)
  │     abstract instance: upload(self) -> PlatformResultExtras
  └── BaseCliUploader
        abstract classmethods: cookie_auth, setup
        abstract instance: upload(self) -> PlatformResultExtras
        shared: run_subprocess(cmd), parse_cli_output(output)
```

### 平台类映射

| 平台 | 当前结构 | 迁移后 |
|---|---|---|
| douyin | `DouYinBaseUploader(BaseVideoUploader)` + `DouYinVideo` + `DouYinNote` | `DouYinBaseUploader(BaseBrowserUploader)`(缩成 hook 层) |
| xiaohongshu | `XiaoHongShuBaseUploader(BaseVideoUploader)` + `XiaoHongShuVideo` + `XiaoHongShuNote` | `XiaoHongShuBaseUploader(BaseBrowserUploader)` |
| kuaishou | `KSBaseUploader(BaseVideoUploader)` + `KSVideo` + `KSNote` | `KSBaseUploader(BaseBrowserUploader)` |
| tencent | `TencentBaseUploader(BaseVideoUploader)` + `TencentVideo` + `TencentNote`(stub) | `TencentBaseUploader(BaseBrowserUploader)` |
| weibo | `WeiboBaseUploader(BaseVideoUploader)` + `WeiboVideo` + `WeiboNote` | `WeiboBaseUploader(BaseBrowserUploader)` |
| baijiahao | `BaiJiaHaoVideo(object)`(1-tier) | `BaiJiaHaoVideo(BaseBrowserUploader)` |
| bilibili | `upload()` 函数 + 模块级 `cookie_auth`/`bilibili_setup` | `BilibiliUploader(BaseCliUploader)` + 模块级 wrapper |
| tk | `TiktokVideo(object)`(1-tier, firefox) | `TiktokVideo(BaseBrowserUploader)`(chromium + patchright) |

2-tier 结构保留:`*BaseUploader` 缩成只含平台 hook 的薄层,`*Video`/`*Note` 子类保留各自的 `upload()` 逻辑。不做 `*Video` + `*BaseUploader` 合并(避免单 task 改动过大)。

### 文件布局

| 文件 | 改动 |
|---|---|
| `uploader/base_video.py` | 升级:加 3 个基类 + enum + TypedDict + exception;保留 `BaseVideoUploader = BasePlatformUploader` 别名(Task 9 删除) |
| `uploader/douyin_uploader/main.py` | `DouYinBaseUploader` 缩成 hook 层,`DouYinVideo`/`DouYinNote` 改 `upload()` 返回 `PlatformResultExtras` |
| `uploader/xiaohongshu_uploader/main.py` | `XiaoHongShuBaseUploader` 缩成 hook 层,`XiaoHongShuVideo`/`XiaoHongShuNote` 改 `upload()` 返回 `PlatformResultExtras` |
| `uploader/ks_uploader/main.py` | `KSBaseUploader` 缩成 hook 层,`KSVideo`/`KSNote` 改 `upload()` 返回 `PlatformResultExtras` |
| `uploader/tencent_uploader/main.py` | `TencentBaseUploader` 缩成 hook 层,`TencentVideo` 改 `upload()` 返回 `PlatformResultExtras`(`TencentNote` stub 保留) |
| `uploader/weibo_uploader/main.py` | `WeiboBaseUploader` 缩成 hook 层,`WeiboVideo`/`WeiboNote` 改 `upload()` 返回 `PlatformResultExtras` |
| `uploader/baijiahao_uploader/main.py` | `BaiJiaHaoVideo` 改基类,保留 `@async_retry` + `ai2video` |
| `uploader/bilibili_uploader/main.py` | 包成 `BilibiliUploader(BaseCliUploader)` |
| `uploader/tk_uploader/main.py` | firefox->chromium+patchright,改基类,override `cookie_gen` |
| `publish/dispatch.py` | 8 个 `publish_to_*` 简化,加 `publish_to_tk`,删 "tk 暂未实现" 分支 |
| `publish/constants.py` | 加 `"tk": 2200` 到 `TITLE_LIMITS` |

## 登录流程模板方法

`BaseBrowserUploader` 提供三个 classmethod 模板方法,5 个浏览器平台 + baijiahao + tk 通过 hook 注入平台差异:

```python
class BaseBrowserUploader(BasePlatformUploader):
    PLATFORM_NAME: str
    UPLOAD_URL: str
    LOGIN_URL: str
    LOGIN_MARKERS: list[str]
    PUBLISH_MARKERS: list[str]

    @classmethod
    async def cookie_auth(cls, account_file: str) -> bool:
        """Navigate to upload page, check if still logged in."""
        # 模板:launch -> context(storage_state) -> goto UPLOAD_URL ->
        #       检测 LOGIN_MARKERS -> 返回 bool

    @classmethod
    async def setup(cls, account_file, handle=False, return_detail=False,
                    qrcode_callback=None, headless=LOCAL_CHROME_HEADLESS):
        """Resolve path -> cookie_auth -> if invalid and handle: cookie_gen."""
        # 模板:调 cookie_auth -> False 且 handle=True 则调 cookie_gen

    @classmethod
    async def cookie_gen(cls, account_file, qrcode_callback=None,
                         headless=LOCAL_CHROME_HEADLESS, return_detail=False):
        """QR login: goto login URL -> extract QR -> poll until complete -> save state."""
        # 模板:launch -> context -> goto LOGIN_URL -> extract_qrcode_src ->
        #       emit callback -> poll is_login_completed -> storage_state save
```

### Hook 列表

| Hook | 类型 | 作用 |
|---|---|---|
| `PLATFORM_NAME` | str | 平台标识,用于日志和 result |
| `UPLOAD_URL` | str | 上传页 URL,cookie_auth 跳此页检测登录 |
| `LOGIN_URL` | str | 登录页 URL,cookie_gen 跳此页 |
| `LOGIN_MARKERS` | list[str] | URL/selector 列表,出现即视为未登录 |
| `PUBLISH_MARKERS` | list[str] | URL/selector 列表,出现即视为发布成功 |
| `extract_qrcode_src(page)` | async, returns str \| None | 从登录页提取 QR 图片 src |
| `is_login_completed(page)` | async, returns bool | 轮询登录是否完成 |

### tk 的 cookie_gen 例外

tk 用 gmail/phone 手动登录,不是 QR。`TiktokVideo` override 整个 `cookie_gen`:

```python
@classmethod
async def cookie_gen(cls, account_file, qrcode_callback=None,
                     headless=LOCAL_CHROME_HEADLESS, return_detail=False):
    """tk 用 page.pause 手动登录,qrcode_callback 被忽略。"""
    async with async_playwright() as p:
        browser = await cls._launch_browser(p, headless)
        context = await cls._init_context(browser, None)
        page = await context.new_page()
        await page.goto(cls.LOGIN_URL)
        await page.pause()  # 用户手动登录,调试器点继续
        await context.storage_state(path=account_file)
        await context.close()
        await browser.close()
    return True
```

`extract_qrcode_src` / `is_login_completed` hook 对 tk 不生效(其 `cookie_gen` 不调模板),但 `is_login_completed` 仍被 `cookie_auth` 模板使用。

### 模块级 wrapper(dispatch.py 兼容层)

每个平台保留模块级 `cookie_auth(account_file)` 和 `<platform>_setup(account_file, handle, return_detail, qrcode_callback, headless)` 薄 wrapper,内部委托 classmethod。`dispatch.py` 的 `_PLATFORM_LOGIN` 注册表继续指向这些 wrapper,不动:

```python
# uploader/douyin_uploader/main.py
async def cookie_auth(account_file):
    return await DouYinBaseUploader.cookie_auth(account_file)

async def douyin_setup(account_file, handle=False, return_detail=False,
                       qrcode_callback=None, headless=LOCAL_CHROME_HEADLESS):
    return await DouYinBaseUploader.setup(account_file, handle, return_detail,
                                          qrcode_callback, headless)
```

`setup` 统一 5 参数签名:`(account_file, handle, return_detail, qrcode_callback, headless)`。当前各平台签名不一致(有的没有 `return_detail`/`qrcode_callback`),迁移时统一。

## 上传流程

### `_browser_session` context manager

`BaseBrowserUploader` 提供 shared context manager,强制 storage_state 在 finally 块保存:

```python
@asynccontextmanager
async def _browser_session(self, headless=None):
    """Launch browser + context with stored cookies, yield page.
    Saves storage_state on exit (finally). Ensures cleanup."""
    async with async_playwright() as p:
        browser = await self._launch_browser(p, headless or self.headless)
        context = await self._init_context(browser, self.account_file)
        page = await context.new_page()
        try:
            yield page
        finally:
            await context.storage_state(path=self.account_file)
            await context.close()
            await browser.close()
```

每个平台的 `upload()` 用 `async with self._browser_session() as page:` 包裹,平台特定的 upload 步骤(set_title_tags / detect_upload_status / click_publish 等)在 `yield page` 之后执行。当前各平台在 `upload()` 末尾手写 `context.storage_state(path=...)` + `context.close()` + `browser.close()` - 这三行全部删除,由 context manager 接管。

### `validate_base_args` 移到基类

当前 5 个 `*BaseUploader` 各自复制参数校验(`validate_video_file` / `validate_publish_date` 等)。移到 `BasePlatformUploader.validate_base_args(params)` 作为 staticmethod,dispatch 在 resolve 路径后、构造 uploader 前调:

```python
class BasePlatformUploader:
    @staticmethod
    def validate_base_args(params: dict) -> PlatformResultExtras | None:
        """Returns error dict if invalid, None if OK.
        Expects paths already resolved by dispatch (resolve_path applied).
        Called by dispatch before construction."""
        if params.get("content_type") == "video":
            video_file = params.get("video_file")
            if not video_file or not os.path.exists(video_file):
                return {"success": False, "message": f"视频文件不存在: {video_file}"}
        elif params.get("content_type") == "note":
            images = params.get("images") or []
            if not images:
                return {"success": False, "message": "图文模式需要提供图片"}
            for img_path in images:
                if not os.path.exists(img_path):
                    return {"success": False, "message": f"图片文件不存在: {img_path}"}
        return None
```

`dispatch.py` 的 8 个 `publish_to_*` 在 resolve 路径后、构造 uploader 前调 `BasePlatformUploader.validate_base_args(params)`(或经子类继承),有错直接返回 - 当前每个 `publish_to_*` 手写 ~10 行校验逻辑全部删除。

### PublishStrategy enum

替换当前 5 个平台各自定义的 `PUBLISH_STRATEGY_IMMEDIATE` / `PUBLISH_STRATEGY_SCHEDULED` 常量对:

```python
class PublishStrategy(str, Enum):
    IMMEDIATE = "immediate"
    SCHEDULED = "scheduled"
```

uploader `__init__` 收 `publish_strategy: PublishStrategy` 参数。当前 5 个平台用字符串 `"immediate"` / `"scheduled"`,迁移时改为 enum(因 `str` 基类,字符串字面量仍可比)。

### upload() 命名约定

- `BasePlatformUploader.upload(self) -> PlatformResultExtras` - 抽象方法,**无参**(用 `self.*` 字段)
- 各平台 `*Video.upload(self)` / `*Note.upload(self)` - 实例方法,签名统一无参
- 当前各平台 Video/Note 类的入口方法改名为 `upload()`:
  - 大多数类已有 `main()` 方法 -> 直接改名 `main()` -> `upload()`
  - `DouYinNote.douyin_upload_note()` -> 改名 `upload()`(它是唯一无 `main()` 的 Note 类)
  - `XiaoHongShuVideo.xiaohongshu_upload_video()` / `XiaoHongShuNote.xiaohongshu_upload_note()` 等平台特定别名**保留**(它们内部调 `main()` 或 `upload()`,不影响 dispatch)
- 保留旧方法名作为 `upload()` 的薄别名,确保 `myUtils/postVideo.py` 的 `app.main()` / `app.douyin_upload_note()` 调用不断:
  - `async def main(self): return await self.upload()`(所有有 `main()` 的类)
  - `async def douyin_upload_note(self): return await self.upload()`(DouYinNote)
- dispatch.py 的 note 分支从 `await uploader.douyin_upload_note()` 改为 `await uploader.upload()`(统一)
- Task 9 删所有 `main()` / `douyin_upload_note()` 别名(sub-project C 迁移 myUtils 时改调 `upload()`)

## 返回类型契约

### PlatformResultExtras TypedDict

替换 `publish/dispatch.py:11-20` 当前的 `PlatformResult` + `PlatformResultExtras` 两个 TypedDict,合并定义到 `uploader/base_video.py`:

```python
class PlatformResult(TypedDict):
    success: bool
    message: str

class PlatformResultExtras(PlatformResult, total=False):
    result_url: str       # 发布内容公开 URL(share_link / video_link 统一)
    result_id: str        # 平台内容 ID(note_id / video_id 统一)
    account_issue: bool   # 失败为账号相关(登录/限制/封禁)
    issue_type: str       # "login_failed" | "publish_restricted" | "cookie_invalid" | ""
```

### 字段映射

| 平台 | 当前字段 | 统一后 |
|---|---|---|
| douyin | (无) | `result_url=""`, `result_id=""` |
| xiaohongshu | `share_link`, `note_id` | `result_url=share_link`, `result_id=note_id` |
| kuaishou | `share_link`, `video_id` | `result_url=share_link`, `result_id=video_id` |
| tencent | (无) | `result_url=""`, `result_id=""` |
| baijiahao | `video_link` | `result_url=video_link`, `result_id=""` |
| bilibili | (biliup 返回) | 尽量映射,无则空 |
| weibo | `video_link` | `result_url=video_link`, `result_id=""` |
| tk | (无) | `result_url=""`, `result_id=""` |

### uploader.upload() 直接返回 PlatformResultExtras

uploader 拥有 result 形状,`dispatch.py` 不再 re-wrap:

```python
# uploader/xiaohongshu_uploader/main.py
class XiaoHongShuVideo(BaseBrowserUploader):
    async def upload(self) -> PlatformResultExtras:
        async with self._browser_session() as page:
            # ... 平台特定 upload 逻辑 ...
            return {
                "success": True,
                "message": "发布成功",
                "result_url": share_link,
                "result_id": note_id,
            }
```

`dispatch.py::publish_to_xiaohongshu` 缩成:

```python
async def publish_to_xiaohongshu(params: dict) -> dict:
    from uploader.xiaohongshu_uploader.main import XiaoHongShuVideo, XiaoHongShuNote

    account_file = resolve_path(params["account_file"])
    title = truncate_title(params["title"], "xiaohongshu")

    # resolve paths into params, then validate
    if params["content_type"] == "video":
        params = {**params, "video_file": resolve_path(params["video_file"])}
    elif params.get("images"):
        params = {**params, "images": [resolve_path(img) for img in params["images"]]}
    err = XiaoHongShuVideo.validate_base_args(params)
    if err:
        return err

    try:
        if params["content_type"] == "video":
            uploader = XiaoHongShuVideo(title=title, file_path=params["video_file"],
                                        tags=params["tags"], publish_date=params["publish_time"] or 0,
                                        account_file=account_file, desc=params["desc"],
                                        publish_strategy=params["publish_strategy"])
        else:
            uploader = XiaoHongShuNote(image_paths=params["images"], note=params["desc"],
                                       tags=params["tags"], publish_date=params["publish_time"] or 0,
                                       account_file=account_file, title=title,
                                       publish_strategy=params["publish_strategy"])
        return await uploader.upload()
    except Exception as e:
        return {"success": False, "message": str(e)}
```

5 个 `result.get("share_link", "")` / `result.get("video_link", "")` 提取块和 ~10 行手写校验逻辑全部删除。

### account_issue / issue_type 标准化

三值:
- `"login_failed"` - `orchestrator.publish_one_item` 已用(当 `ensure_account_login` 返回 False)
- `"publish_restricted"` - douyin `DouyinPublishRestrictedError` 已用,其他平台可主动 raise `AccountRestrictedError` 加入
- `"cookie_invalid"` - `BaseBrowserUploader.cookie_auth` 检测到 storage_state 存在但失效时用

`AccountRestrictedError` 新异常类放 `uploader/base_video.py`:

```python
class AccountRestrictedError(Exception):
    """平台限制发布(风控/限流/封禁)。upload() 捕获后映射为 account_issue=True。"""
```

### Excel 写入保留在 dispatch

baijiahao / weibo 发布成功后写 Excel 是平台副作用,不属于 result 契约。`dispatch.py::publish_to_baijiahao` / `publish_to_weibo` 保留:

```python
result = await uploader.upload()
if result["success"] and result.get("result_url"):
    try:
        write_result = write_video_link(result["result_url"])
        if write_result["success"]:
            print(f"  📝 视频链接已写入 Excel: {result['result_url']}")
        else:
            print(f"  ⚠️ 写入 Excel 失败: {write_result['message']}")
    except Exception as e:
        print(f"  ⚠️ 写入 Excel 异常: {e}")
return result
```

### 向后兼容

`reporter.py` 只读 `success`/`message`/`account_issue` - 字段名不变,无影响。
`orchestrator.py` 只读 `success`/`message` - 无影响。
`hgsau_backend.py` 不读这些字段(grep 确认) - 无影响。
`utils/excel_writer.write_video_link` 在 dispatch 内被调,不从 result dict 读 - 无影响。

无外部消费者读 `share_link`/`video_link`/`note_id`/`video_id` 字段(grep 确认),所以不需要 shim 期。

## tk 迁移细节

### 浏览器引擎:firefox -> chromium + patchright

```python
# Before
from playwright.async_api import Playwright, async_playwright
browser = await playwright.firefox.launch(headless=LOCAL_CHROME_HEADLESS)

# After
from patchright.async_api import Playwright, async_playwright
browser = await playwright.chromium.launch(headless=LOCAL_CHROME_HEADLESS)
```

`--lang en-GB` arg 在 chromium 上同样有效。`set_init_script(context)` 已在用,保留。

### TiktokVideo 类结构

```python
class TiktokVideo(BaseBrowserUploader):
    PLATFORM_NAME = "tk"
    UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"
    LOGIN_URL = "https://www.tiktok.com/login?lang=en"
    LOGIN_MARKERS = ["/login", "/signup"]
    PUBLISH_MARKERS = []  # tk 用 success_flag_div selector,不用 URL

    def __init__(self, title, file_path, tags, publish_date, account_file,
                 publish_strategy=PublishStrategy.IMMEDIATE, **kwargs):
        super().__init__(title=title, file_path=file_path, tags=tags,
                         publish_date=publish_date, account_file=account_file,
                         publish_strategy=publish_strategy, **kwargs)
        self.locator_base = None

    async def upload(self) -> PlatformResultExtras:
        async with self._browser_session() as page:
            # 平台特定:choose_base_locator / add_title_tags / detect_upload_status /
            #          set_schedule_time / click_publish
            return {"success": True, "message": "发布成功"}

    @classmethod
    def is_login_completed(cls, page) -> bool:
        return cls._is_tiktok_auth_page_valid(page)

    @classmethod
    async def cookie_gen(cls, account_file, qrcode_callback=None,
                         headless=LOCAL_CHROME_HEADLESS, return_detail=False):
        """tk 用 page.pause 手动登录,qrcode_callback 被忽略。"""
        # ... override 整个模板 ...

    # tk 私有方法(平台特定,不上移):
    # set_schedule_time, add_title_tags, click_publish, detect_upload_status,
    # choose_base_locator, handle_upload_error, _is_tiktok_auth_page_valid
```

### 接入 dispatch

```python
# publish/dispatch.py
_PLATFORM_LOGIN = {
    # ... 现有 7 个 ...
    "tk": ("uploader.tk_uploader.main", "cookie_auth", "tiktok_setup"),
}

async def publish_to_tk(params: dict) -> dict:
    from uploader.tk_uploader.main import TiktokVideo
    account_file = resolve_path(params["account_file"])
    title = truncate_title(params["title"], "tk")

    if params["content_type"] != "video":
        return {"success": False, "message": "TikTok 暂只支持视频发布"}

    video_file = resolve_path(params["video_file"])
    if not video_file or not os.path.exists(video_file):
        return {"success": False, "message": f"视频文件不存在: {video_file}"}

    try:
        uploader = TiktokVideo(
            title=title, file_path=video_file, tags=params["tags"],
            publish_date=params["publish_time"] or 0,
            account_file=account_file, desc=params.get("desc", ""),
            publish_strategy=params["publish_strategy"],
        )
        return await uploader.upload()
    except Exception as e:
        return {"success": False, "message": str(e)}

_PUBLISH_DISPATCH = {
    # ... 现有 7 个 ...
    "tk": publish_to_tk,
}
```

`publish_to_platform` 里 `if platform == "tk": return "暂未实现"` 分支删除。

### publish_strategy 采用

tk 当前用 `if self.publish_date != 0` 判断是否定时。迁移后采用 `PublishStrategy` enum,`set_schedule_time(page, publish_date)` 调用改由 `publish_strategy == PublishStrategy.SCHEDULED` gate。

### 风险:firefox -> chromium 可能触发 TikTok 反爬

TikTok 反爬激进。其他 7 个平台已用 patchright+chromium 成功(含海外面向的 bilibili)。若 tk 在 chromium 上反爬失败,**fallback**:`_launch_browser` hook 允许子类 override engine 选择,tk 可保留 firefox - 但这意味着 tk 不能完全用 `BaseBrowserUploader` 模板。**决策**:先按 chromium 试,真实测试失败则在 `TiktokVideo._launch_browser` 内 override 回 firefox,文档记录例外。

## 测试策略

### 现有测试(回归安全网)

`tests/test_publish_engine.py`(427 行,16 用例)- sub-project A 的核心回归网,通过 `from publish_all import ...` 调用。base class 抽取后必须保持模块级函数签名不变(`cookie_auth`/`*_setup`/`publish_to_*`),测试才能继续通过。**零修改。**

### 改写测试

| 测试文件 | 改动 |
|---|---|
| `tests/test_publish_engine.py` | 零修改(回归网) |
| `tests/test_publish_dispatch.py` | 加 `tk` 到 `_PLATFORM_LOGIN` 和 `_PUBLISH_DISPATCH` 覆盖断言 |

### 新增测试

| 测试文件 | 测什么 |
|---|---|
| `tests/test_base_uploader.py` | `BasePlatformUploader` / `BaseBrowserUploader` / `BaseCliUploader` 纯逻辑:`validate_video_file` / `validate_publish_date` / `validate_base_args` / `_build_launch_kwargs` / `PublishStrategy` enum / `PlatformResultExtras` TypedDict 实例化。完全 mock,不发网络。 |
| `tests/test_base_uploader_login.py` | `cookie_auth` / `setup` / `cookie_gen` 模板方法流程:mock `async_playwright` / `_launch_browser` / `_init_context`,验证模板调 hook 的顺序(`get_login_url` -> `extract_qrcode_src` -> `is_login_completed`)、storage_state 保存时机、`return_detail=True` 返回结构。用 `FakeUploader(BaseBrowserUploader)` 注入测试 hook。 |
| `tests/test_base_uploader_session.py` | `_browser_session` context manager:进入时 launch+context+new_page,退出时 `storage_state(path=...)` 必被调用(即使中间抛异常)、context/browser 必关闭。用 `pytest.raises` 验证异常路径下 finally 仍执行。 |
| `tests/test_tk_migration.py` | `TiktokVideo` 继承 `BaseBrowserUploader`、`cookie_gen` 走 `page.pause` 分支(不被 base 模板覆盖)、`is_login_completed` 用 `_is_tiktok_auth_page_valid` 逻辑、`upload` 返回 `PlatformResultExtras`。不发网络。 |

### 覆盖目标

| 组件 | 覆盖来源 |
|---|---|
| `BasePlatformUploader` 纯逻辑 | `test_base_uploader.py` |
| `BaseBrowserUploader` 模板方法 | `test_base_uploader_login.py` |
| `_browser_session` context manager | `test_base_uploader_session.py` |
| 7 个浏览器 uploader | `test_publish_engine.py` 间接覆盖(通过 dispatch mock 检查构造 + 调用) |
| tk 迁移 | `test_tk_migration.py` |
| dispatch 表完整性 | `test_publish_dispatch.py` |
| reporter | `test_publish_reporter.py`(sub-project A 已有,不动) |

### 不测的(明确排除)

- 真实浏览器端到端发布 - 当前就没有,本 spec 不引入。每个平台真实发布验证靠迁移顺序里的 manual smoke test。
- 8 个 uploader 的 `upload()` 方法内部 - 平台特定,逻辑复杂,UI 选择器易变。靠 manual smoke test,不写单测。
- `myUtils/` 的 backward compat - 已确认 sub-project B 不碰 myUtils/。

### TDD 执行顺序

每个任务:写失败测试 -> 跑确认失败 -> 写最小实现让测试过 -> 跑确认通过 -> commit。跟 sub-project A 的 TDD 节奏一致。

## 全局约束

- **Python 3.9+ 兼容**:`PlatformResultExtras` 用 `TypedDict` + `total=False` 继承,不用 `Required[]`(3.11+ 才有)
- **patchright**:`from patchright.async_api import async_playwright`(不是 `playwright`)。tk 迁移必须从 `playwright` 切到 `patchright`
- **`LOCAL_CHROME_HEADLESS` / `LOCAL_CHROME_PATH`**:从 `conf` 导入,所有浏览器启动用这两个配置
- **`set_init_script`**:`utils.base_social_media.set_init_script`,每个 `browser.new_context()` 后必调(防爬)
- **`resolve_path`**:`publish.content.resolve_path`,所有文件路径解析用此函数(不用 `myUtils` 的 `get_absolute_path` 或 `utils.files_times.get_absolute_path`)
- **`truncate_title`**:`publish.content.truncate_title`,dispatch 调用前先截断
- **`write_video_link`**:`utils.excel_writer.write_video_link`,baijiahao / weibo 发布成功后调,参数为 `result["result_url"]`(原 `video_link`)
- **`<platform>_logger`**:`utils.log.<platform>_logger`,每个平台用自己的 logger
- **`build_login_qrcode_path` / `decode_qrcode_from_path` / `print_terminal_qrcode` / `remove_qrcode_file` / `save_data_url_image`**:`utils.login_qrcode`,QR 登录流程用,迁到 `BaseBrowserUploader.cookie_gen` 模板
- **5 参数 setup 签名**:`(account_file, handle, return_detail, qrcode_callback, headless)`,所有平台统一
- **`PublishStrategy` enum**:`str` 子类,字符串字面量 `"immediate"`/`"scheduled"` 仍可比,向后兼容
- **`BaseVideoUploader` 别名**:Task 1-8 保留 `BaseVideoUploader = BasePlatformUploader`,Task 9 删除并改 5 个 `*BaseUploader` import
- **`main()` / `douyin_upload_note()` 别名**:各平台旧入口方法名改为 `upload()` 的别名 wrapper(因 `myUtils/postVideo.py` 调 `app.main()` 和 `app.douyin_upload_note()`),Task 9 删

## 迁移顺序

共 9 个 task,每个 task 独立可测、可 revert。

### Task 1: 升级 `uploader/base_video.py` 基类基金会

**Files:** `uploader/base_video.py`(升级), `tests/test_base_uploader.py`(新), `tests/test_base_uploader_login.py`(新), `tests/test_base_uploader_session.py`(新)

- 加 `BasePlatformUploader`(abstract: `validate_video_file`/`validate_image_file`/`validate_publish_date`/`validate_base_args` + `PublishStrategy` enum + `PlatformResultExtras` TypedDict + `AccountRestrictedError`)
- 加 `BaseBrowserUploader(BasePlatformUploader)`(template: `cookie_auth`/`setup`/`cookie_gen` classmethod;hooks: `PLATFORM_NAME`/`UPLOAD_URL`/`LOGIN_URL`/`LOGIN_MARKERS`/`PUBLISH_MARKERS`/`extract_qrcode_src`/`is_login_completed`;shared: `_build_launch_kwargs`/`_init_context`/`_launch_browser`/`_save_storage_state`/`_browser_session`/`_msg`/`_build_login_result`/`_emit_qrcode_callback`)
- 加 `BaseCliUploader(BasePlatformUploader)`(abstract: `cookie_auth`/`setup`/`upload`;shared: `run_subprocess`/`parse_cli_output`)
- 保留 `BaseVideoUploader = BasePlatformUploader` 别名
- 测试用 `FakeUploader(BaseBrowserUploader)` 注入假 hook
- **不碰任何平台文件**
- `tests/test_publish_engine.py` 必须全绿

### Task 2: 迁移 weibo(首个浏览器平台,验证模式)

**Files:** `uploader/weibo_uploader/main.py`, `publish/dispatch.py`

- `WeiboBaseUploader` 改继承 `BaseBrowserUploader`,删已上移代码,留 hook
- `WeiboVideo`/`WeiboNote` 的 `main()` 改 `upload() -> PlatformResultExtras`(无参,沿用 `self.*` 字段),返回 `{"result_url": video_link}`;保留 `main()` 别名 wrapper(`async def main(self): return await self.upload()`)
- 模块级 `cookie_auth` / `weibo_setup` 改薄 wrapper
- `dispatch.py::publish_to_weibo` 删 `result.get("video_link", "")` 提取,Excel 写入读 `result["result_url"]`
- Manual smoke test: 配 weibo 账号跑一次真实发布

### Task 3: 迁移 xiaohongshu

**Files:** `uploader/xiaohongshu_uploader/main.py`, `publish/dispatch.py`

- `XiaoHongShuBaseUploader` 缩,`XiaoHongShuVideo`/`XiaoHongShuNote` 改 `upload()` 返回 `{"result_url": share_link, "result_id": note_id}`
- `dispatch.py::publish_to_xiaohongshu` 删 `result.get("share_link", "")` / `result.get("note_id", "")` 提取
- 验证 note 分支也走统一返回

### Task 4: 迁移 kuaishou

**Files:** `uploader/ks_uploader/main.py`, `publish/dispatch.py`

- `KSBaseUploader` 缩,`KSVideo`/`KSNote` 改 `upload()` 返回 `{"result_url": share_link, "result_id": video_id}`
- 保留快手 cookie 路径异常(sub-project E 处理)
- `dispatch.py::publish_to_kuaishou` 删 `result.get("share_link", "")` / `result.get("video_id", "")` 提取

### Task 5: 迁移 tencent

**Files:** `uploader/tencent_uploader/main.py`, `publish/dispatch.py`

- `TencentBaseUploader` 缩,`TencentVideo` 改 `upload()` 返回 `{"result_url": "", "result_id": ""}`
- 保留 `TencentNote` stub(不删,sub-project D)
- cookie_auth headless bug 修复(memory `project_tencent_cookie_auth_headless_bug.md`)迁到 `BaseBrowserUploader.cookie_auth` 模板

### Task 6: 迁移 douyin(最复杂)

**Files:** `uploader/douyin_uploader/main.py`, `publish/dispatch.py`

- `DouYinBaseUploader` 缩,`DouYinVideo`/`DouYinNote` 改 `upload()`
- 保留 `DouyinPublishRestrictedError`,在 `upload()` 内 try/except 映射到 `{"account_issue": True, "issue_type": "publish_restricted"}`
- `dispatch.py::publish_to_douyin` 删手写异常处理块

### Task 7: 迁移 baijiahao(1-tier + @async_retry)

**Files:** `uploader/baijiahao_uploader/main.py`, `publish/dispatch.py`

- `BaiJiaHaoVideo(object)` -> `BaiJiaHaoVideo(BaseBrowserUploader)`
- 保留 `@async_retry` 装饰器(套在 `upload()` 上)
- 保留 `ai2video` 方法(sub-project D 确认)
- 加 `publish_strategy` 参数(保持 IMMEDIATE-only,sub-project E 处理定时)
- `dispatch.py::publish_to_baijiahao` 简化,Excel 写入读 `result["result_url"]`

### Task 8: 加 BaseCliUploader 用法 + 迁移 bilibili

**Files:** `uploader/bilibili_uploader/main.py`, `publish/dispatch.py`

- 把 `upload()` 函数包成 `BilibiliUploader(BaseCliUploader).upload() -> PlatformResultExtras`(无参,用 `self.*` 字段)
- 保留 subprocess 调 biliup CLI 逻辑
- `cookie_auth`/`bilibili_setup` 改 classmethod(可能仍调 biliup cookie 检查命令)
- `dispatch.py::publish_to_bilibili` 简化

### Task 9: 迁移 tk + 删 `BaseVideoUploader` 别名 + dispatch 最终清理

**Files:** `uploader/tk_uploader/main.py`, `publish/dispatch.py`, `publish/constants.py`, `uploader/base_video.py`(删别名 + 删 `main()` 别名),5 个 `*BaseUploader` import(改名)

- `TiktokVideo(object)` -> `TiktokVideo(BaseBrowserUploader)`,firefox->chromium+patchright
- override `cookie_gen`(走 `page.pause`)
- 加到 `_PLATFORM_LOGIN` / `_PUBLISH_DISPATCH`,删 "tk 暂未实现" 分支
- `publish/constants.py` 加 `"tk": 2200` 到 `TITLE_LIMITS`,确认 `PLATFORM_NAMES["tk"]` 存在
- 删 `BaseVideoUploader = BasePlatformUploader` 别名,5 个 `*BaseUploader` 的 `from uploader.base_video import BaseVideoUploader` 改为 `BasePlatformUploader`
- 删所有 `main()` 别名 wrapper(5 个平台 Video + xhs/ks/weibo Note)和 `DouYinNote.douyin_upload_note()` 别名(sub-project C 迁移 myUtils 时改调 `upload()`)。**注意:** `myUtils/postVideo.py` 调 `app.main()` 和 `app.douyin_upload_note()` 会断 - 但 myUtils 不在本 spec 范围,sub-project C 处理。Task 9 commit message 标注 `BREAKING: myUtils/postVideo.py app.main() / app.douyin_upload_note() 调用需 sub-project C 同步迁移`。
- `tests/test_publish_dispatch.py` 加 tk 到两个 dispatch 表覆盖断言
- `tests/test_tk_migration.py` 新增
- 全量测试 + `python publish_all.py --help` + 一次真实 tk 发布(如可行)

### 任务依赖图

```
Task 1 (foundation)
  ├─ Task 2 (weibo)  ── validates pattern
  │    ├─ Task 3 (xhs)
  │    ├─ Task 4 (ks)
  │    ├─ Task 5 (tencent)
  │    └─ Task 6 (douyin)
  ├─ Task 7 (baijiahao)  ── independent, 1-tier
  ├─ Task 8 (bilibili)  ── independent, CLI sublayer
  └─ Task 9 (tk + cleanup)  ── depends on all above done
```

Task 2-8 互相独立,建议按上述顺序(risk ascending)。Task 9 必须最后(删别名要求所有 `*BaseUploader` 已迁移完)。

### 每 task 验证标准

- `pytest tests/` 全绿(`test_publish_engine.py` 是核心回归网)
- 该 task 涉及平台 manual smoke test 一次真实发布(tk 视环境)
- diff 只动该 task 声明的文件,不溢出

## 验证标准

- `pytest tests/` 全绿
- `python publish_all.py --help` 显示新 argparse(sub-project A 已有,不破)
- `hgsau --help` 显示新 argparse
- 8 个平台 manual smoke test 各一次真实发布(tk 视环境)
- `grep -rn "share_link\|video_link\|note_id\|video_id" publish/dispatch.py` 返回空(所有提取已上移到 uploader)
- `grep -rn "from playwright.async_api" uploader/` 返回空(所有平台用 patchright)
- `grep -rn "BaseVideoUploader" uploader/` 返回空(别名已删)
