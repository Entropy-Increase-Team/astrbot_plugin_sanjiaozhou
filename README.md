# sanjiaozhou

三角洲行动 AstrBot 插件。命令与渲染模板参考 Yunzai 版 `delta-force-plugin`，接口层按 Go 版 Delta Force API 文档实现，并使用 AstrBot 插件内 Playwright 截图渲染。

## 配置

在 AstrBot 插件配置中填写：

- `api_key`: 三角洲 API Key。
- `client_id`: 机器人 QQ 或在后端登记的客户端 ID。
- `api_mode`: 默认 `auto`，内置模式当前统一请求 `https://delta-test-api.shallow.ink`。
- `enable_image_render`: 开启后使用 Playwright 渲染云崽模板；关闭则输出文本摘要。

## 常用命令

- `帮助`
- `娱乐帮助`
- `计算帮助`
- `登录`、`绑定 <token>`、`账号`、`账号切换 <序号>`
- `信息`、`数据`、`战绩 [模式] [页码]`、`日报 [模式]`、`周报 [模式]`
- `藏品`、`出红记录 [物品名]`、`大红收藏 [赛季数字]`、`健康状态`
- `每日密码`、`文章列表`、`物品搜索 <名称/ID>`、`当前价格 <名称/ID>`
- `伤害 <模式> <武器> <子弹> <护甲/头盔:护甲> <距离> <次数> <部位分配>`、`修甲 <装备> <剩余>/<当前> <局内|局外>`
- `语音`、`鼠鼠音乐`、`tts状态`、`tts <角色> <情感> <文本>`

资源模板来自 Yunzai 版 `delta-force-plugin-main/resources`，但 API client 和 AstrBot 命令入口没有复用云崽基建。房间、WebSocket、定时推送类命令保留入口提示，后续需要按 AstrBot 任务/适配器单独接入。计算器当前支持快捷伤害、快捷修甲和映射表，云崽交互式会话入口会返回 AstrBot 版用法。
