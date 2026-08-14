# sanjiaozhou

<img decoding="async" align="right" src="resources/imgs/readme/hz.png" width="35%">

- 当前版本：`0.4.1`，详细变更见 [更新日志](CHANGELOG.md)。
- 三角洲行动 AstrBot 插件，适用于 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的游戏数据查询、计算器和娱乐功能。
- 命令与渲染模板参考 Yunzai 版 `delta-force-plugin`，接口层和 AstrBot 命令入口按 AstrBot 插件机制重新实现。
- 支持 QQ/微信扫码与 OAuth 登录、网页数据授权、Token 手动绑定、个人信息、日报、周报、战绩、藏品、物品、价格、利润、语音、TTS 等功能入口。
- 使用插件内 Playwright 渲染 HTML 模板，帮助菜单和数据面板以图片形式返回。

> [!TIP]
> 三角洲行动是一款由腾讯琳琅天上工作室开发的 FPS 游戏。本插件用于在 AstrBot 中查询游戏数据、生成战报图片和使用常用工具。

> [!IMPORTANT]
> 以下命令示例均不写触发符。实际发送时请使用 AstrBot WebUI 中配置的指令触发符，例如 WebUI 配置为 `/` 时发送 `/帮助`。

## 安装插件

进入 AstrBot 的插件目录后克隆仓库：

```bash
git clone https://github.com/Entropy-Increase-Team/astrbot_plugin_sanjiaozhou.git
```

如 AstrBot 未自动安装依赖，可在 AstrBot Python 环境中执行：

```bash
pip install -r data/plugins/astrbot_plugin_sanjiaozhou/requirements.txt
playwright install chromium
```

安装完成后在 AstrBot WebUI 中重载插件，或重启 AstrBot。

## 插件配置

在 AstrBot WebUI 的插件配置中填写：

- `api_key`: 三角洲 API Key。
- `client_id`: 客户端 ID，建议填机器人 QQ 或在后端登记的 clientID。
- `api_mode`: 默认 `auto`，内置模式当前统一请求 `https://delta-test-api.shallow.ink`。
- `api_base_url`: 自定义 API 地址，仅 `api_mode=custom` 时生效。
- `enable_image_render`: 开启后使用 Playwright 渲染 HTML 模板；关闭后使用文本摘要兜底。
- `request_timeout`: API 请求超时时间，单位秒。
- `render_timeout`: Playwright 渲染超时时间，单位毫秒。
- `login_poll_timeout`: 扫码登录和网页登录授权的轮询超时时间，单位秒。
- `login_poll_interval`: 扫码登录和网页登录授权的轮询间隔，单位秒。
- `tts_max_length`: TTS 文本最大长度。
- `tts_poll_timeout`: TTS 合成任务最长等待时间，默认 450 秒。
- `tts_poll_interval`: TTS 合成任务状态轮询间隔，默认 5 秒。
- `record_poll_interval`: 战绩订阅轮询间隔，默认 300 秒，后端允许 60 至 3600 秒。
- `record_rank_detection`: 创建战绩订阅时是否开启排位判断，默认关闭。
- 改枪码社区写操作要求 API Key 具备 `gunmod:community:write` 权限；上传命令必须提供武器 ID 和配件 JSON，方案 ID 使用后端返回的 UUID。
- `push_check_interval`: 定时推送检查间隔，默认 60 秒，最小 30 秒。
- `daily_push_hour`: 日报推送小时，默认 10 点。
- `weekly_push_weekday` / `weekly_push_hour`: 周报推送星期和小时，默认周一 10 点。
- `keyword_push_hour`: 每日密码推送小时，默认 8 点。

## 功能列表

发送 `帮助` 查看基础菜单，发送 `娱乐帮助` 查看娱乐菜单，发送 `计算帮助` 查看计算器菜单。

### 个人类功能

- [x] QQ/微信扫码登录
- [x] QQ/微信授权登录
- [x] 网页数据授权登录（授权页选择已有账号，批准后自动绑定）
- [x] QQ/微信 Token 刷新
- [x] WeGame 登录入口
- [x] CK 登录入口
- [x] Token 绑定、解绑、账号切换
- [x] 角色绑定入口
- [x] 个人信息查询
- [x] UID 查询
- [x] 地图统计
- [x] 日报/周报数据
- [x] 战绩查询
- [x] 藏品/资产查询
- [x] 货币信息查询
- [x] 流水查询
- [x] 出红记录/大红收藏海报
- [x] 违规记录查询
- [x] 特勤处状态
- [x] 特勤处信息
- [x] AI 锐评/AI 评价
- [x] 战绩对局房间详情查询（`房间信息 [模式] [对局ID]`）
- [ ] 开黑房间管理（最新版后端没有创建、加入、退出等路由）
- [x] 战绩订阅与 WebSocket 实时推送
- [ ] 通用广播接入（最新版后端未提供对应通知协议）

### 工具类功能

- [x] 每日密码查询
- [x] 官方文章列表/详情
- [x] 社区改枪码入口
- [x] 干员列表和干员详情
- [x] 健康状态
- [x] 物品列表和物品搜索
- [x] 当前价格/价格历史
- [x] 材料价格
- [x] 利润历史和利润排行
- [x] 特勤处利润
- [x] 改枪码社区列表、详情、上传、更新、删除、投票和收藏
- [x] 伤害计算
- [x] 维修/修甲计算
- [x] 计算映射表
- [x] 日报、周报、特勤处和每日密码定时推送
- [x] 原生交互式战备会话和最低成本配装计算

### 娱乐类功能

- [x] 随机语音
- [x] 角色/场景/动作语音
- [x] 语音列表、标签列表、语音统计
- [x] 鼠鼠音乐
- [x] 鼠鼠音乐列表
- [x] 鼠鼠歌单
- [x] 点歌
- [x] 歌词
- [x] 音乐本地缓存、统计和管理员清理
- [x] TTS 语音合成
- [x] TTS 角色列表、预设列表、角色详情
- [x] 最近 TTS 文件上传和语音重播

## 命令示例

<details>
<summary>点击展开</summary>

| 命令 | 功能 | 示例 |
| --- | --- | --- |
| `帮助` | 查看基础帮助菜单 | `帮助` |
| `娱乐帮助` | 查看娱乐功能菜单 | `娱乐帮助` |
| `计算帮助` | 查看计算器菜单 | `计算帮助` |
| `登录` | QQ/微信扫码登录 | `登录` |
| `网页登录` | 打开网页授权页，选择已有账号并在批准后自动绑定 | `网页登录` |
| `绑定 <token>` | 手动绑定 frameworkToken | `绑定 eyJ...` |
| `账号` | 查看已绑定账号 | `账号` |
| `账号切换 <序号>` | 切换当前账号并同步后端主绑定 | `账号切换 2` |
| `解绑 <序号>` | 解除后端账号绑定并同步移除本地记录 | `解绑 1` |
| `删除 <序号>` | 删除 QQ/微信登录数据并解除账号绑定 | `删除 1` |
| `信息` | 查询账号信息 | `信息` |
| `UID` | 查询当前账号 UID | `UID` |
| `数据 [模式] [赛季]` | 查询个人统计数据 | `数据 烽火` |
| `战绩 [模式] [页码]` | 查询近期战绩 | `战绩 烽火 2` |
| `订阅 战绩 [sol/mp/both]` | 创建战绩订阅 | `订阅 战绩 both` |
| `取消订阅 战绩` | 取消当前账号战绩订阅 | `取消订阅 战绩` |
| `订阅状态 战绩` | 查看战绩订阅状态 | `订阅状态 战绩` |
| `开启本群订阅推送` | 将当前群设为战绩推送目标 | `开启本群订阅推送` |
| `开启私信订阅推送` | 将当前私聊设为战绩推送目标 | `开启私信订阅推送` |
| `开启日报推送` / `关闭日报推送` | 设置当前群日报推送 | `开启日报推送` |
| `开启周报推送` / `关闭周报推送` | 设置当前群周报推送 | `开启周报推送` |
| `开启特勤处推送` / `关闭特勤处推送` | 设置当前用户在本群的生产完成提醒 | `开启特勤处推送` |
| `开启每日密码推送` / `关闭每日密码推送` | 管理当前群每日密码推送（管理员） | `开启每日密码推送` |
| `日报 [模式]` | 查询日报 | `日报 全面` |
| `周报 [模式] [日期] [展示]` | 查询周报 | `周报 烽火` |
| `藏品 [类型]` | 查询藏品/资产 | `藏品 枪皮` |
| `出红记录 [物品名]` | 查询藏品解锁记录 | `出红记录` |
| `大红收藏 [赛季数字]` | 生成大红收藏海报 | `大红收藏 4` |
| `封号记录` | 查询当前账号的 QQ 安全中心违规记录 | `封号记录` |
| `健康状态` | 查询游戏内健康增益与负面状态 | `健康状态` |
| `服务器状态` | 查询 API 服务、数据库和运行环境状态 | `服务器状态` |
| `用户统计` | 管理员查看 AstrBot 本地绑定统计 | `用户统计` |
| `每日密码` | 查询今日密码 | `每日密码` |
| `文章列表` | 查询文章列表 | `文章列表` |
| `文章详情 <ID>` | 查看文章详情 | `文章详情 123` |
| `物品搜索 <名称/ID>` | 搜索游戏物品 | `物品搜索 金条` |
| `当前价格 <名称/ID>` | 查询当前价格 | `当前价格 金条` |
| `价格历史 <名称/ID>` | 查询价格历史 | `价格历史 金条` |
| `利润历史 <物品名称/ID> [天数]` | 查询指定物品的制造利润历史 | `利润历史 燃料电池 14天` |
| `改枪码列表 [武器/模式/页码]` | 查询公开改枪方案 | `改枪码列表 M4A1 烽火 page2` |
| `改枪码详情 <UUID>` | 查看改枪方案详情 | `改枪码详情 550e8400-e29b-41d4-...` |
| `上传改枪码 <改枪码> <武器ID> [sol/mp] [描述] <配件JSON>` | 提交改枪方案 | `上传改枪码 CODE123 180100001 sol 满配 [{"slotId":"scope","objectId":1001}]` |
| `改枪码点赞/点踩 <UUID>` | 对改枪方案投票 | `改枪码点赞 550e8400-e29b-41d4-...` |
| `收藏改枪码/取消收藏改枪码 <UUID>` | 添加或取消收藏 | `收藏改枪码 550e8400-e29b-41d4-...` |
| `改枪码收藏列表` | 查看我的收藏 | `改枪码收藏列表` |
| `利润排行 [类型] [场所] [数量]` | 查询制造利润排行 | `利润排行 时均 工作台 10` |
| `特勤处利润 [类型] [场所] [数量]` | 查询特勤处实时制造利润 | `特勤处利润 总利润 技术中心 5` |
| `伤害 <模式> <武器> <子弹> <护甲> <距离> <次数> <部位>` | 快捷伤害计算 | `伤害 烽火 腾龙 dvc12 41:37 50 6 1:2,2:4` |
| `修甲 <装备> <剩余>/<当前> <局内/局外>` | 快捷维修计算 | `修甲 fs 0/100 局内` |
| `战备` | 启动交互式最低成本配装计算 | `战备` |
| `语音 [角色/标签]` | 播放语音 | `语音 麦晓雯` |
| `鼠鼠音乐 [关键词]` | 播放或搜索音乐 | `鼠鼠音乐` |
| `鼠鼠音乐列表 [页码]` | 查看音乐排行榜并记忆当前列表 | `鼠鼠音乐列表 1` |
| `鼠鼠歌单 <名称/ID/艺术家>` | 查询歌单或艺术家的歌曲 | `鼠鼠歌单 曼波` |
| `点歌 <序号>` | 播放列表中的歌曲 | `点歌 1` |
| `歌词` | 获取最近播放歌曲的歌词 | `歌词` |
| `音乐缓存状态` | 查看本地音乐缓存 | `音乐缓存状态` |
| `清理音乐缓存` | 管理员清空本地音乐缓存 | `清理音乐缓存` |
| `tts <角色> [情感] <文本>` | 合成语音并等待发送 | `tts 麦晓雯 开心 你好呀` |
| `tts上传` / `tts重播` | 发送最近五分钟内合成的文件或语音 | `tts上传` |

</details>

## 与 Yunzai 版的关系

- 命令设计、帮助菜单、HTML/CSS 渲染模板和 `resources/data` 静态数据参考 Yunzai 版 `delta-force-plugin`。
- API client、AstrBot 命令注册、用户绑定存储、Playwright 渲染封装按 AstrBot 重新实现。
- 不复用云崽插件的运行基建，也不提供 `#三角洲` 这类云崽命名空间入口。

## 鸣谢

- **API 支持**：感谢 [浅巷墨黎](https://github.com/dnyo666) 整理并提供三角洲行动 API 接口文档及后端。
- **原始插件参考**：[delta-force-plugin](https://github.com/Dnyo666/delta-force-plugin)
- **登录功能参考**：[deltaforce-酷曦科技](https://github.com/coolxitech/deltaforce)
- **计算器数据与算法参考**：繁星攻略组
- **AstrBot 框架**：[AstrBot](https://github.com/AstrBotDevs/AstrBot)
- **三角洲行动官方**：[df.qq.com](https://df.qq.com)

## 其他框架

- **Yunzai**：[delta-force-plugin](https://github.com/Dnyo666/delta-force-plugin)
- **NoneBot2**：[nonebot-plugin-delta-force](https://github.com/Entropy-Increase-Team/nonebot-plugin-delta-force)
- **Koishi**：[koishi-plugin-delta-force](https://github.com/Entropy-Increase-Team/koishi-plugin-delta-force)
- **Karin**：[karin-plugin-delta-force](https://github.com/Entropy-Increase-Team/karin-plugin-delta-force)
