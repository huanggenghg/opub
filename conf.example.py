# opub 配置文件模板
# pip install 后无需手动创建此文件，conf.py 会自动使用默认值
# 如需自定义配置，请将此文件复制为 config.json 放到数据目录中
#
# 数据目录位置：
#   所有 Agent 与运行方式统一使用当前系统用户的 ~/.opub/
#
# config.json 示例：
# {
#   "chrome_path": "",
#   "debug": false,
#   "zhipu_api_key": "",
#   "zhipu_vision_model": "glm-4v-plus",
# }
#
# 已废弃："chrome_headless" 不再有任何效果。
# 发布过程默认无头(不弹窗),排查问题时用 opub --no-headless 回到有头模式;
# 扫码登录始终显示浏览器窗口。
