# 三角洲行动功能对照矩阵

本矩阵以 Yunzai `delta-force-plugin` 的 `apps` 目录为功能范围，以当前三角洲 Go API 文档和源码为接口权威来源，以本地 AstrBot 源码为框架权威来源。API 证据已更新至 `delta-force-api-go` 的 `main` 分支提交 `fbd0eb1d67731c99b012a999ee96cde47ad976c2`（2026-07-20）。

状态定义：

- **未开始**：AstrBot 中没有对应原生实现，或只有占位提示。
- **部分**：已有命令或实现，但业务闭环、字段、渲染或测试尚未全部确认。
- **已验证**：成功、空数据、错误分支和必要渲染均已实际验证。
- **阻塞**：已确认依赖当前环境之外的能力，并记录了证据。

测试栏中的“待测”表示没有验证证据，不能视为通过。API 栏只填写已经从当前 Go 后端源码或 Swagger 确认的路径；其余项目在后续审计时补全。

2026-08-15 使用本地 AstrBot v4.17.6 实际注册表验证：本插件的 `干员列表` 与终末地插件同名，`tts` 与 AstrBot 内置命令同名，帮助命令的 `help` 别名还会与内置帮助冲突。使用 AstrBot 原生命令管理移除本插件 `help` 别名，并将本插件的两个命令改为 `三角洲干员列表`、`三角洲tts` 后，三个三角洲入口均只激活一个 handler；插件源码仍保留完整 Yunzai 命令语义。战争雷霆的 `help` 实为 `wt help` 子命令，不属于根命令冲突。

2026-08-14 使用本地 AstrBot v4.17.6 实际启动验证：插件成功加载并在 WebUI 注册 82 个独立命令，全部启用且没有带空格的命令名、旧 `RegexFilter` 或 `#三角洲` 入口。

2026-08-14 使用真实后端完成脱敏联调：健康与公共元数据、QQ 扫码初始化及待扫码状态、QQ OAuth 初始化、失效本地绑定分类、WebSocket 握手与 `record.client.subscribe` 客户端级频道确认均通过。真实扫码后的绑定闭环和实际 `record.new` 事件下发仍需交互触发验证。

2026-08-14 将插件 82 个 HTTP 路径与最新版 Go 路由逐项对照，并对 19 组无需账号授权的查询执行真实字段契约验证；公共元数据、物品、材料价格、音频、TTS、每日密码、文章、AI 预设和两套改枪方案接口均返回成功且必需字段齐全。

2026-08-14 使用 AstrBot v4.17.6 真实依赖完成隔离子进程注册验证：插件类和元数据正常加载，注册器包含 82 个消息 handler、82 个 `CommandFilter`、0 个 `RegexFilter`；274 个命令与别名无重复、无空格名称，每条带参数消息只命中一个 handler。自定义多字符触发符 `!!` 经真实 `WakingCheckStage` 去除后，完整命令参数得到保留且只激活目标 handler。

| 分类 | Yunzai 源文件 | Yunzai fnc | 原命令/别名摘要 | AstrBot 注册命令 | AstrBot 实现函数 | API 方法与路径 | 渲染模板 | 文本兜底 | 成功测试 | 空数据测试 | 错误测试 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 账户 | `apps/account/Account.js` | `showAccounts`、`bindToken`、`unbindToken`、`deleteToken`、`switchAccount`、`refreshWechat`、`refreshQq` | 账号、绑定、解绑、删除、切换、刷新 | 账号、绑定、解绑、账号切换、微信刷新及别名 | `_account_list`、`_bind_token`、`_delete_account`、`_switch_account`、`_refresh_account` | `GET/POST/DELETE /api/v1/user/bindings` 及主绑定子路由；`GET /api/v1/login/{qq,wechat}/refresh`；`DELETE /api/v1/login/{qq,wechat}/token` | 无 | 有 | 绑定、切换、解绑、登录删除和刷新 fixture 通过 | 空账号列表 fixture 通过 | 远端失败不改本地、类型不匹配 fixture 通过 | 已验证 |
| 登录 | `apps/account/Login.js` | `login`、`loginWithCookie`、`qqOAuthLogin`、`wechatOAuthLogin`、`webLogin`、`bindCharacter` | 扫码登录、CK 登录、QQ/微信 OAuth、网页登录、角色绑定 | 登录、ck登录、qq授权登录、微信授权登录、网页登录、角色绑定及别名 | `_login`、`_cookie_login`、`_oauth_login`、`_web_login`、`_bind_character` | `GET /api/v1/login/{platform}/qr`；`GET /api/v1/login/{platform}/status`；`POST /api/v1/login/qq/ck`；`GET/POST /api/v1/login/{qq,wechat}/oauth`；`POST/GET /api/v1/authorization/requests` 及状态子路由；`GET /api/v1/df/person/bind?method=bind` | 无 | 有 | 二维码组件、动态有效期、OAuth 回调、网页授权领取、账号与角色自动绑定 fixture 通过 | 缺少二维码与未绑定账号 fixture 通过 | 过期二维码、授权拒绝/过期/重复领取、API 错误、state 不匹配、远端绑定失败和凭证失效 fixture 通过 | 部分（仍需真实扫码与网页授权复验） |
| 娱乐 | `apps/entertainment/Music.js` | `getLyrics`、`sendShushuVoice`、`getMusicCacheStats`、`cleanMusicCache`、`getShushuMusicRank`、`getShushuPlaylist`、`selectMusicByNumber`、`sendShushuMusic` | 歌词、鼠鼠语音、音乐缓存、排行、歌单、点歌、鼠鼠音乐 | 歌词、鼠鼠音乐列表、鼠鼠歌单、点歌、鼠鼠音乐、音乐缓存状态、清理音乐缓存 | `_music`、`_music_list`、`_music_playlist`、`_music_select`、`_music_lyrics`、`_music_replay`、`_music_cache_status`、`_music_cache_clear` | `GET /api/v1/df/audio/shushu`；`GET /api/v1/df/audio/shushu/list`；音乐缓存位于 AstrBot 插件数据目录 | `musicList` | 有 | 搜索、歌单、点歌、远程 LRC、缓存统计/清理 fixture 与 Playwright 通过 | 空歌曲、无歌词和无最近播放 fixture 通过 | API、下载、过期列表、越界选择和管理员权限 fixture 通过 | 已验证 |
| 娱乐 | `apps/entertainment/TTS.js` | `getTtsHealth`、`getTtsPresets`、`getTtsPresetDetail`、`downloadLastTts`、`synthesize` | TTS 状态、角色列表、角色详情、下载、合成 | tts状态、tts角色列表、tts角色详情、tts、tts上传、tts重播 | `_tts_status`、`_tts_presets`、`_tts_preset`、`_tts`、`_tts_recent` | `GET /api/v1/df/tts/health`；`GET /api/v1/df/tts/presets`；`GET /api/v1/df/tts/preset?character=`；`POST /api/v1/df/tts/synthesize`；`GET /api/v1/df/tts/task`；音频签名下载地址由任务结果提供 | 无 | 有 | 元数据、队列字段真实契约、异步任务轮询、语音与文件组件 fixture 通过 | 空状态、空预设和空详情 fixture 通过 | 查询、提交、任务失败和最近记录缺失 fixture 通过 | 已验证 |
| 娱乐 | `apps/entertainment/Voice.js` | `getCharacterList`、`getTagList`、`getCategoryList`、`getAudioStats`、`sendVoice` | 角色、标签、分类、统计、语音 | 语音列表、语音及别名 | `_voice_meta`、`_voice` | `GET /api/v1/df/audio/random`；`GET /api/v1/df/audio/categories`；`GET /api/v1/df/audio/characters`；`GET /api/v1/df/audio/stats`；`GET /api/v1/df/audio/tags` | 无 | 有 | 权威路由、四类元数据真实契约、嵌套下载地址与语音组件 fixture 通过 | 五类空数据 fixture 通过 | 五类 API 错误 fixture 通过 | 已验证 |
| 信息 | `apps/info/banhistory.js` | `getBanHistory` | 封号记录、违规记录/历史 | 封号记录及别名 | `_ban_history` | `GET /api/v1/df/qqsafe/ban`；Header：`X-Framework-Token` | 无 | 有 | 权威字段格式化 fixture 通过 | 空列表 fixture 通过 | 凭证失效 fixture 通过 | 已验证 |
| 信息 | `apps/info/Collection.js` | `getCollection` | 藏品、资产 | 藏品及别名 | `_collection` | `GET /api/v2/df/person/collection`；`GET /api/v1/df/object/collection` | `collection` | 有 | 合并映射 fixture 与 Playwright 通过 | fixture 通过 | fixture 通过 | 已验证 |
| 信息 | `apps/info/Data.js` | `getPersonalData` | 数据、data，含模式和赛季参数 | 数据及别名 | `_personal_data` | `GET /api/v1/df/person/personaldata`；Query：`type`、`seasonid` | `personalData` | 有 | fixture 与 Playwright 通过 | fixture 通过 | fixture 通过 | 已验证 |
| 信息 | `apps/info/Flows.js` | `getFlows` | 流水，设备/道具/货币、分页 | 流水及别名 | `_flows`、`_money_trend_chart` | `GET /api/v1/df/person/flows`；Query：`type`、`page` | `flows`、`moneyTrendChart` | 有 | 三类型、多日趋势和单日趋势 fixture 与 Playwright 通过 | 空流水、无效余额 fixture 通过 | API、趋势渲染失败隔离 fixture 通过 | 已验证 |
| 信息 | `apps/info/health.js` | `getServerHealth` | 服务器健康状态 | 服务器状态 | `_server_status` | `GET /health/detailed`；HTTP 503 且 `code=0` 时保留降级数据 | 无 | 有 | 正常与降级 fixture 通过 | 空响应 fixture 通过 | 上游错误 fixture 通过 | 已验证 |
| 信息 | `apps/info/HealthInfo.js` | `getHealthInfo` | 健康状态 | 健康状态 | `_health_info` | `GET /api/v1/df/object/health`；后端提取 AMS `jData.data.data.list` | `healthInfo` | 有 | 字段适配与模板 fixture 通过 | 空列表 fixture 通过 | 凭证失效 fixture 通过 | 已验证 |
| 信息 | `apps/info/Info.js` | `getUserInfo`、`getUid` | 信息、UID | 信息、uid及别名 | `_user_info`、`_uid` | `GET /api/v1/df/person/personalinfo` | `userInfo` | 有 | fixture 与 Playwright 通过 | 缺少角色 fixture 通过 | fixture 通过 | 已验证 |
| 信息 | `apps/info/MapStats.js` | `getMapStats` | 地图统计，含模式、赛季、地图 | 地图统计及别名 | `_map_stats` | `GET /api/v1/df/person/mapstats`；Query：`type`、`serial`、`mapId` | `mapStats` | 有 | 双模式 fixture 与 Playwright 通过 | 搜索空结果 fixture 通过 | fixture 通过 | 已验证 |
| 信息 | `apps/info/Money.js` | `getMoney` | 货币、余额 | 货币及别名 | `_money` | `GET /api/v1/df/person/money`；默认三种货币 | 无 | 有 | fixture 通过 | fixture 通过 | fixture 通过 | 已验证 |
| 信息 | `apps/info/Operator.js` | `getOperatorInfo` | 干员详情 | 干员 | `_operator_info` | `GET /api/v1/df/object/operator` | `operator` | 有 | AMS 字段 fixture 与 Playwright 通过 | 空列表 fixture 通过 | API 错误 fixture 通过 | 已验证 |
| 信息 | `apps/info/OperatorList.js` | `getOperatorList` | 干员列表 | 干员列表 | `_operator_list` | `GET /api/v1/df/object/operator2` | 无 | 有 | endpoint 与参数 fixture 通过 | 空列表 fixture 通过 | API 错误 fixture 通过 | 已验证 |
| 信息 | `apps/info/PlaceInfo.js` | `getPlaceInfo` | 特勤处信息 | 特勤处信息 | `_place_info` | `GET /api/v1/df/place/info`；Query：`place` | `placeInfo` | 有 | 中文类型/等级 fixture 与 Playwright 通过 | fixture 通过 | fixture 通过 | 已验证 |
| 信息 | `apps/info/red.js` | `getRedCollection`、`getRedByName` | 大红收藏、按名称查询 | 出红记录及相关别名 | `_red_records`、`_red_list`、`_red_one`、`_red_collection` | `GET /api/v1/df/person/redlist`；`GET /api/v1/df/person/redone?objectid=`；个人数据与称号接口 | `redCollection`、`redRecord`、`redRecordList` | 有 | 列表、单物品层级与模板 fixture 通过 | 空记录 fixture 通过 | 凭证失效 fixture 通过 | 已验证 |
| 信息 | `apps/info/Stats.js` | `getUserStats` | 用户统计 | 用户统计 | `_user_stats` | 最新后端无 Yunzai 旧版全站统计路由；改为 AstrBot 本地绑定统计 | 无 | 有 | 管理员计数 fixture 通过 | 零绑定 fixture 通过 | 非管理员权限 fixture 通过 | 已验证 |
| 推送 | `apps/push/DailyPush.js` | `pushDailyReports` | 日报定时推送 | 开启/关闭日报推送 | `_scheduled_push_loop`、`_run_fixed_push` | `GET /api/v1/df/person/dailyrecord` | `dailyReport` | 有 | fixture 与模板测试通过 | 空日报 fixture 通过 | API、发送与单任务异常隔离 fixture 通过 | 已验证 |
| 推送 | `apps/push/Notification.js` | `enableNotification`、`disableNotification`、`getNotificationStatus` | 广播/通知开启、关闭、状态 | 广播开启及大量别名 | `_dispatch` 中阻塞提示 | 当前后端 `plugins/ws` 仅有 echo、record、ocr、price，未提供通知广播 handler | 无 | 有阻塞提示 | 不适用 | 不适用 | 不适用 | 阻塞 |
| 推送 | `apps/push/placestatus.js` | `getPlaceStatus`、`togglePlaceStatusPush` | 特勤处状态、订阅切换 | 特勤处状态；开启/关闭特勤处推送 | `_place_status`、`_toggle_scheduled_push` | `GET /api/v1/df/person/placestatus` | 无 | 有 | 权威字段摘要与订阅目标 fixture 通过 | 空设施 fixture 通过 | API 错误 fixture 通过 | 已验证 |
| 推送 | `apps/push/PlaceTask.js` | `checkAndPushScheduledTasks`、`pollAndScheduleTasks` | 特勤处后台调度 | 初始化后台任务 | `_scheduled_push_loop`、`_run_place_push` | `GET /api/v1/df/person/placestatus`；字段 `pushTime`、`leftTime`、`objectDetail` | 无 | 有 | 跨轮询完成与去重 fixture 通过 | 空设施 fixture 通过 | API、发送与单任务异常隔离 fixture 通过 | 已验证 |
| 推送 | `apps/push/Task.js` | `toggleDailyKeywordPush`、`pushDailyKeyword` | 每日密码订阅与定时推送 | 开启/关闭每日密码推送 | `_toggle_scheduled_push`、`_run_fixed_push` | `GET /api/v1/df/tools/dailykeyword` | 无 | 有 | fixture 通过 | 空密码 fixture 通过 | API、发送与单任务异常隔离 fixture 通过 | 已验证 |
| 推送 | `apps/push/WeeklyPush.js` | `pushWeeklyReports` | 周报定时推送 | 开启/关闭周报推送 | `_scheduled_push_loop`、`_run_fixed_push` | `GET /api/v1/df/person/weeklyrecord` | `weeklyReport` | 有 | 模板与调度 fixture 通过 | 空周报 fixture 通过 | API、发送与单任务异常隔离 fixture 通过 | 已验证 |
| 报告 | `apps/report/Daily.js` | `getDailyReport`、`getYesterdayProfit`、`toggleDailyPush` | 日报、昨日收益、日报推送开关 | 日报、昨日收益；开启/关闭日报推送 | `_daily`、`_toggle_scheduled_push` | `GET /api/v1/df/person/dailyrecord`；Query：`type` | `dailyReport` | 有 | 查询、推送 fixture 与 Playwright 通过 | 日报/昨日日期 fixture 通过 | fixture 通过 | 已验证 |
| 报告 | `apps/report/Record.js` | `getRecord` | 战绩，含模式和分页 | 战绩 | `_record` | `GET /api/v1/df/person/record`；Query：`type`、`page`、`enrich` | `record` | 有 | fixture 与 Playwright 通过 | fixture 通过 | fixture 通过 | 已验证 |
| 报告 | `apps/report/RecordSubscription.js` | `subscribeRecord`、`unsubscribeRecord`、`getSubscriptionStatus`、`enableGroupPush`、`disableGroupPush`、`enablePrivatePush`、`disablePrivatePush` | 战绩订阅、状态、群/私聊推送开关 | 合法根命令 `订阅`、`取消订阅`、`订阅状态`，以 `战绩` 为参数 | `_record_subscription`、`_subscription_target`、`_ws_supervisor`、`_push_record_event` | `GET/POST /api/v1/user/record-subscriptions`；详情、删除、启停、事件、最近战绩子路由；WS `/ws` 的 `record.client.subscribe`、`record.new` | `recordPush` | 有 | 创建、取消、状态、类型切换、SOL/MP 图片推送、事件去重、多目标及重载任务去重 fixture 通过；真实客户端级订阅确认通过 | 无订阅、无订阅 ID、无后端绑定 fixture 通过 | REST、删除旧订阅、目标查询、订阅拒绝、图片渲染失败、多目标发送和资源关闭异常隔离 fixture 通过 | 部分（真实握手与频道订阅已验证，仍需实际新战绩事件和消息下发复验） |
| 报告 | `apps/report/Weekly.js` | `getWeeklyReport`、`toggleWeeklyPush` | 周报、周报推送开关 | 周报；开启/关闭周报推送 | `_weekly`、`_toggle_scheduled_push` | `GET /api/v1/df/person/weeklyrecord`；Query：`type`、`date`、`showExtra` | `weeklyReport` | 有 | 查询、推送 fixture 与 Playwright 通过 | fixture 通过 | fixture 通过 | 已验证 |
| 系统 | `apps/system/Help.js` | `help`、`entertainmentHelp` | 帮助、娱乐帮助 | 帮助、娱乐帮助、计算帮助及别名 | `_help`、`_calculator_help` | 无 | `help/index.html` | 有 | Playwright fixture 通过 | 不适用 | 配置读取失败 fixture 通过 | 已验证 |
| 系统 | `apps/system/Update.js` | `update`、`update_log` | 更新、强制更新、更新日志 | 更新、强制更新、插件更新、update、更新日志、update_log | `_update_plugin`、`_update_log`、`_parse_changelog` | AstrBot 原生 `StarManager.update_plugin("sanjiaozhou")`；本地 `CHANGELOG.md` | `help/version-info.html` | 有 | 原生更新管理器、最近两版解析、图片组件与 Playwright fixture 通过 | 空日志与管理器缺失 fixture 通过 | 非管理员、更新失败、日志读取和渲染失败 fixture 通过 | 已验证 |
| 系统 | `apps/system/WebSocketClient.js` | `connectWebSocket`、`disconnectWebSocket`、`getWebSocketStatus` | WebSocket 连接、断开、状态 | ws连接及大量别名 | `_ws_supervisor`、`_ws_run_once`、`_push_record_event` | `/ws`；`X-API-Key` 握手；`record.client.subscribe`；`record.new` | 无 | 有 | 权威协议、零值 `code` 省略、订阅确认、事件分发、去重、多目标与重载任务替换 fixture 通过；真实握手与频道确认通过 | 不适用 | `kind=error` 拒绝、非 JSON、消费异常、关闭超时与发送失败隔离 fixture 通过 | 部分（连接和订阅已真实验证，仍需实际 `record.new` 事件复验） |
| 工具 | `apps/tools/AIEvaluation.js` | `getAiCommentary`、`getAiCommentaryWithPreset`、`listAiPresets` | AI 锐评、指定预设、预设列表 | ai锐评、ai评价、ai预设列表 | `_ai_review`、`_ai_presets` | `POST /api/v1/df/tools/ai`，Body：`type`、`preset`；`GET /api/v1/df/tools/ai/presets` | 无 | 有 | 正文、模式别名、预设列表与请求 Body fixture 通过 | 空正文、空预设 fixture 通过 | API 错误 fixture 通过 | 已验证 |
| 工具 | `apps/tools/Calculator.js` | `startDamageCalculation`、`startReadinessCalculation`、`startRepairCalculation`、`quickRepairCalculation`、`quickDamageCalculation`、`showHelp`、`showMappingTable`、`cancelCalculation` | 伤害、战备、维修、修甲、帮助、映射表、取消 | 伤害计算、战备计算、维修计算、修甲、计算帮助、计算映射表、取消计算 | `_quick_damage`、`_quick_repair`、`_readiness_session`、`DeltaCalculator.calculate_readiness` | `resources/data` 静态数据与本地计算逻辑；会话使用 AstrBot `SessionWaiter` | 帮助 YAML | 有 | 快速伤害/维修、最低成本排序、交互会话与真实静态数据 fixture 通过 | 无组合 fixture 通过 | 参数错误、静态数据失败和会话超时 fixture 通过 | 已验证 |
| 工具 | `apps/tools/Object.js` | `getObjectList`、`searchObject` | 物品列表、物品搜索 | 物品列表、物品搜索 | `_object_list`、`_object_search`、`_object_info` | `GET /api/v1/df/object/list`；`GET /api/v1/df/object/search` | 无 | 有 | 默认分类、分页、多 ID 参数及四类物品字段真实契约通过 | 列表与搜索空数据 fixture 通过 | 列表与搜索 API 错误 fixture 通过 | 已验证 |
| 工具 | `apps/tools/Price.js` | `getPriceHistory`、`getCurrentPrice`、`getMaterialPrice`、`getProfitHistory`、`getProfitRank`、`getProfitRankV2`、`getSpecialOpsProfit` | 当前/历史/材料价格、利润历史和排行 | 当前价格、价格历史、材料价格、利润历史及别名 | `_price_now`、`_price_history`、`_material_price`、`_profit` | `GET /api/v1/df/object/price/ams/latest`；`GET /api/v1/df/object/price/ams/history/v2`；`GET /api/v1/df/place/material/price`；`GET /api/v1/df/place/profit`；`GET /api/v1/df/place/profit/history`；`GET /api/v1/df/place/profit/rank` | 无 | 有 | 当前/材料价格、利润历史/排行参数与文本 fixture 通过；材料价格真实字段契约通过 | 六类查询空数据 fixture 通过 | 主接口、后备接口错误 fixture 通过 | 已验证 |
| 工具 | `apps/tools/Room.js` | `getRoomList`、`createRoom`、`joinRoom`、`quitRoom`、`kickMember`、`getRoomInfo`、`getMapList`、`getTagList` | 房间列表、创建、加入、退出、踢人、信息、地图、标签 | 房间信息、房间列表及相关别名 | `_battle_room_info`；`_dispatch` 中房间管理阻塞提示 | `GET /api/v1/df/person/roominfo?roomId=&type=`；最新版没有开黑房间管理路由 | 无 | 有 | 烽火列表、全面嵌套玩家详情及 URL 编码昵称 fixture 通过 | 空成员列表 fixture 通过 | API 错误、模式错误和未绑定 fixture 通过 | 部分（战绩对局房间详情已验证；开黑房间管理因后端无路由而阻塞） |
| 工具 | `apps/tools/SolutionV2.js` | `uploadSolution`、`getSolutionList`、`getSolutionDetail`、`voteSolution`、`updateSolution`、`deleteSolution`、`collectSolution`、`getCollectList` | 改枪方案上传、列表、详情、投票、更新、删除、收藏、收藏列表 | 上传改枪码、改枪码列表、改枪码详情、改枪码点赞/点踩、更新/删除/收藏改枪码、改枪码收藏列表 | `_solution_upload`、`_solution_list`、`_solution_detail`、`_solution_vote`、`_solution_update`、`_solution_delete`、`_solution_favorite` | `/api/v1/df/gunmod/community/solutions` 及 UUID 子路由；写操作需 `gunmod:community:write`、`X-Client-User-ID`、`X-Client-User-Type` | 无 | 有 | 公开与旧版列表真实字段契约、上传、更新、删除、投票和收藏 fixture 通过 | 普通/收藏列表、详情空数据及参数错误 fixture 通过 | 查询错误与写权限不足 fixture 通过 | 已验证 |
| 工具 | `apps/tools/Tools.js` | `getDailyKeyword`、`getArticleList`、`getArticleDetail` | 每日密码、文章列表、文章详情 | 每日密码、文章列表、文章详情 | `_daily_keyword`、`_article_list`、`_article_detail` | `GET /api/v1/df/tools/dailykeyword`；`GET /api/v1/df/tools/article/list`；`GET /api/v1/df/tools/article/detail?threadID=` | 无 | 有 | 每日密码与文章列表真实字段契约、分类合并、详情正文与请求参数 fixture 通过 | 公共池不可用、空列表与文章缺失 fixture 通过 | API 错误 fixture 通过 | 已验证 |

## 第一阶段接口证据

### 扫码登录状态

当前 Go 后端 `internal/service/login/helpers.go` 的状态映射为：

| code | status | 含义 | AstrBot 预期行为 |
| --- | --- | --- | --- |
| `1` | `pending` | 等待扫码 | 继续轮询 |
| `2` | `scanned` | 已扫码，等待手机确认 | 提示一次后继续轮询 |
| `0` | `authed` / `done` | 授权或登录成功 | 绑定返回的 `frameworkToken` |
| `-2` | `expired` | 二维码过期或会话不存在 | 终止并提示重新登录 |
| `-3` | `risk_control` | 风控 | 终止并提示用户改用其他登录方式 |
| `-4` | 其他 | 未知状态 | 终止并返回简短错误 |

二维码接口返回的 `expire` 为 Unix 毫秒时间戳，当前后端固定有效期为 120 秒。AstrBot 按响应动态显示剩余秒数并限制轮询时长；同时兼容 Unix 秒、Unix 毫秒和 ISO 时间，字段缺失或非法时才回退 `login_poll_timeout`。

### OAuth 请求字段

当前 Go 后端和 Swagger 对 QQ、微信 OAuth 的共同约束为：

- 获取授权：`GET /api/v1/login/{qq,wechat}/oauth`，可选 Query 为 `platformID`、`botID`。
- 获取响应字段：`frameworkToken`、`loginUrl`、`state`、`expire`。
- 提交回调：`POST /api/v1/login/{qq,wechat}/oauth`。
- 完整回调 URL 字段：`callbackUrl`、`callback_url` 或 `url`。
- 分离字段：`frameworkToken` 与 `authCode`/`code`，微信额外支持 `wx_code`。
- 当前 Go 请求结构不包含 Yunzai 旧客户端使用的 `authurl` 字段，因此 AstrBot 不使用该旧字段。

### 网页数据授权

- 创建请求：`POST /api/v1/authorization/requests`，发送 `client_id`、`client_name`、`client_type=bot`、`platform_id` 及三个权威授权范围。
- 用户打开后端返回的 `auth_url`，在 Web 端选择已有绑定并批准；插件轮询 `GET /api/v1/authorization/requests/{request_id}/status`。
- `used` 或携带 `framework_token` 的 `approved` 结果进入统一账号与角色绑定收尾；`pending` 继续等待，`rejected`、`expired` 和缺失凭证均明确终止。
- 不再依赖 Yunzai 写死的 `https://df.shallow.ink/oauth-login`，也不要求用户在聊天中复制或发送 frameworkToken。

### HTTP 客户端安全边界

- 默认启用系统 TLS 证书校验，不再使用 `verify=False`。
- `auto` 模式会去重相同 API 地址，避免对同一服务重复请求。
- 仅 `GET`、`HEAD`、`OPTIONS` 可在备用地址间重试；登录提交、绑定和其他非幂等 `POST` 不自动重放。
- 文本资源采用限额流式读取，响应声明或实际读取量超过上限时立即终止。
- HTTP 204 统一归一为成功；非 JSON 服务端错误只返回状态摘要，不向用户透传完整正文。
- 请求超时与普通网络失败使用不同提示，并在非幂等请求中保持单次提交。
- 网络错误日志只记录方法、路径和异常类型，不记录 Header、请求体、OAuth 回调 URL 或 token。
- TLS、流式大小限制、故障切换、非幂等超时、204、错误正文脱敏和客户端关闭均有固定响应测试。

### 第一阶段验证记录

- 真实 AstrBot v4.17.6 源码导入成功；注册结构检查为 82 个独立命令 handler、274 个命令名/别名。
- 注册结果中空格命令、重复命令名和 `RegexFilter` 数量均为 0。
- 脱敏登录二维码 fixture 为 `328×328` PNG，可由图片解析器识别并通过 `Image.fromBase64()` 路径发送。
- 帮助菜单已由插件自身的 `DeltaRenderer` 和 Playwright 渲染为 `2560×6090` PNG，已人工检查中文、背景、图标、换行和底部完整性。

## 第二阶段核心查询证据

- Go API 的单模式结果保留 AMS `data.data` 业务层级；AstrBot 只移除最外层统一响应信封。个人数据、日报和周报均覆盖单模式与双模式 fixture。
- 战绩按 Yunzai 行为使用 `GET /api/v1/df/person/record`，保留烽火 `teammateArr`；适配玩家、AI 玩家、AI 三类击杀和队友数据。
- 地图统计按当前后端要求发送 `type`、`serial`、`mapId`；未指定模式时分别查询 `sol`、`mp`，地图名称搜索在返回列表上执行。
- “昨日收益”仅在 `recentGainDate` 确实等于昨天时展示，避免将任意最近收益误标为昨日数据。
- 第二阶段当时累计 25 项脱敏单元测试通过，覆盖登录安全与核心查询的成功、空数据、错误分支。
- Playwright 已生成并人工检查信息、烽火数据、全面数据、战绩、日报、周报、烽火地图统计、全面地图统计共 8 张截图；长昵称、趋势首尾数值、中文、底部和动态高度均无重叠或裁切。

## 第三阶段工具与娱乐证据

- 音乐接口按最新版 `songs[]`、`playlistId`、`artist`、`keyword` 适配；歌单名称在客户端按 `playlistName` 匹配，未命中时回退艺术家查询。
- 远程 LRC 会下载并去除时间标签；异常 `metadata`、空音频、空音乐和服务错误均有 fixture。
- TTS 使用 `character` 参数提交异步任务并轮询 `taskId`，已覆盖完成与失败状态、相对音频 URL 和 AstrBot `Record` 组件。
- 最近 TTS 结果保留五分钟，`tts上传` 使用 AstrBot `File` 组件，`tts重播` 使用 `Record` 组件；不把带签名音频 URL 写入持久化数据。
- 鼠鼠音乐下载到 AstrBot 插件数据目录，使用 SHA-256 文件名和原子元数据写入；单文件限制 64 MiB，14 天未访问缓存自动清理，下载失败时继续使用远程语音地址。
- 战备计算使用 AstrBot 原生 `SessionWaiter`，支持目标战备、指定胸挂/背包、最高单件价格和会话内取消；组合计算在线程中运行，不阻塞事件循环。
- 干员详细数据来自 `/api/v1/df/object/operator`，静态列表来自 `/api/v1/df/object/operator2`；干员模板已从 Yunzai 语法转换为 Jinja2。
- 第三阶段当时累计 70 项脱敏单元测试通过。Playwright 已额外生成并人工检查流水、藏品、特勤处、音乐和干员 5 张截图；干员截图为 `2400×1400`，背景、技能卡、长描述和底部均完整。
- 2026-08-14 使用插件内素材 fixture 通过 Playwright 实际渲染并人工检查 `redCollection`、`redRecordList`、`redRecord` 和 `healthInfo` 四张截图；出红收藏的统计卡、标题条、收藏卡背景路径已校正，周报头像失败回退改用已存在的插件 Logo，长昵称、长物品名、记录列表和健康状态双栏均无破图、重叠或裁切。
- 2026-08-14 增加可重复执行的全模板视觉验收：17 个业务模板和更新日志卡片均通过真实 Chromium 截图、PNG 解码、尺寸、文件体积、可见像素与非白像素检查，测试结束后不保留渲染产物。

## 当前验证汇总

- 2026-08-14 全量脱敏单元测试持续通过；当前准确数量以本轮测试输出为准。
- 登录专项覆盖二维码有效期的未来、已过期、缺失、非法值，以及 Unix 秒、Unix 毫秒和 ISO 时间格式。
- 扫码、Cookie、OAuth 的收尾提示覆盖后端账号绑定成功/失败与角色绑定成功/失败组合；后端未确认时只说明本地暂存，不再误报完整绑定成功。
- 网页授权覆盖权威请求体、相对授权链接、批准领取、拒绝、过期、重复领取缺失凭证及连续状态查询失败。
- 使用 AstrBot v4.17.6 真实源码重新导入插件：82 个处理器均为 `CommandFilter`，`RegexFilter` 和无过滤器处理器均为 0。
- 后台任务使用事件循环级登记表防止插件重载或重复初始化产生重复推送；终止流程覆盖任务回收、关闭超时、资源异常隔离与幂等调用。
