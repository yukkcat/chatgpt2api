# 控制台数据契约

状态：当前

## 原则

控制台的业务语义由后端投影产生，Vue 只消费契约、维护页面交互和渲染。这里的“后端拥有”不是后端输出 HTML，而是后端输出稳定的 JSON 视图模型。

- 后端负责状态、标签、色调、诊断、统计口径和操作结果。
- `web-vue/src/api/` 负责传输、类型和必要的字段适配。
- 页面负责筛选条件、草稿、选中项、弹窗、图表交互、加载生命周期与响应式布局。
- 页面不得通过错误文本、HTTP 状态或多个原始字段重新判断业务结果。

## 主要投影

| 页面 / 能力 | 后端入口与投影 | 前端消费边界 |
| --- | --- | --- |
| 概览中心 | `GET /api/dashboard`、`services/dashboard_view.py`、`api/dashboard_contract.py` | `api/stats.ts` 和 Dashboard 图表 |
| 实时监控 | `GET /api/monitor/realtime`、`services/monitor_view.py`、`api/monitor_contract.py` | `api/monitor.ts` 和监控行 / 详情 |
| 调用日志 | `GET /api/logs`、`GET /api/logs/{id}`、`services/call_view.py`、`api/call_contract.py` | `api/logs.ts`、列表与详情抽屉 |
| 账号管理 | `/api/accounts`、`/api/account-groups`、`api/accounts.py` | `api/accounts.ts` 与账号页面运行时 |
| 代理管理 | `/api/proxy/*`、代理管理服务 | `api/proxy.ts` 与代理页面运行时 |
| 系统设置 | `GET/PATCH /api/settings`、`services/settings_management_service.py`、`contracts/settings.py` | `api/settings.ts` 与设置分区 |
| 图片管理 | `/api/images`、`ImageStorageService` | `api/gallery.ts` 与图库页面运行时 |
| 对话画图 | `/api/image-tasks`、`api/image_task_contract.py`、`services/image_task_view.py` | Studio 的任务运行时 |
| 可编辑文件 | `/v1/editable-file-tasks`、`services/editable_file_task_service.py` | Studio 的独立文件任务运行时 |
| 提示词库 | `/api/prompts`、`contracts/prompts.py` | Studio 和设置中的提示词来源界面 |

## 概览中心

`GET /api/dashboard` 一次返回三个所有权清晰的投影：`ranges` 是 Application Database 中 Dashboard 指标的 `24h`、`7d`、`30d` 持久化汇总，`runtime` 是当前进程与运行环境的实时采样，`operations` 是当前 Active Requests 数量。前端只校验并展示这些字段，不扫描 Call Records，也不从实时监控详情反算并发。

图表默认周期和自动刷新间隔属于浏览器交互偏好，由 Dashboard 页面 Module 通过 `localStorage` 持有，不进入后端系统设置或 Application Database。每次重新进入概览页面时，五张图读取同一个默认周期；进入页面后仍可分别切换。浏览器标签页仅从隐藏恢复可见时继续现有选择，不重置图表周期。

## 账号记忆状态

账号列表投影提供 `memory_state`（`enabled`、`disabled`、`unknown`）、
`memory_label`、`memory_tone`、`memory_checked_at`，以及 `memory_actions`
允许的操作。页面直接渲染标签、色调和动作，不根据凭据或原始布尔值反算。
`memory_label` 分别为“开启”“关闭”“未确认”；开启使用 `success`，关闭和未确认使用
`neutral`。旧账号及未查询账号显示为未确认。状态和时间表示最后一次确认的快照，不代表实时查询。

`memory_operation_status`、`memory_operation_label`、`memory_operation_tone`
和安全的 `memory_operation_error` 描述最近操作；待验证或失败不覆盖之前确认的
状态。关闭记忆只修改上游 `m3m` 开关，不删除已有记忆。

清空结果独立投影为 `memory_clear_status`（`never`、`verified`、`pending`、`failed`）、
`memory_clear_label`、`memory_clear_tone` 和经过脱敏的 `memory_clear_error`。
标签分别为“未操作”“清空成功”“待验证”“清空失败”；色调分别为
`neutral`、`success`、`warning`、`error`。`memory_clear_at` 表示最近清空尝试时间，
`memory_cleared_at` 表示最近确认成功时间。失败或后续待验证不会抹除过去成功时间。
这些字段只记录历史操作结果，不能据此断定账号当前没有记忆；后续仍可能产生新记忆。
清空不修改记忆开关，也不覆盖开关操作结果，后端不保存或返回记忆内容。

`GET /api/accounts` 和选择范围均接受 `memory_state`（`all | enabled | disabled | unknown`）
筛选；列表数量、分页、预览、跨页全选及筛选导出共用后端条件。
`POST /api/accounts/memory` 接收现有
选择范围和 `action: enable | disable | refresh | clear`，单个账号也走同一路径。
操作启动时固定目标 ID，结果在现有进度契约中提供 `confirmed`、`pending`、
失败和跳过计数；仅收到上游接受响应不能视为已确认成功。
清空后读取上游记忆列表，只在明确为空且 token 数为 0 时确认成功，其余接受结果保持待验证。
`refresh` 对待验证的清空记录只执行回读，不重发清空请求；成功后保留原清空尝试时间，
更新最近成功时间。界面复用已有确认框、单个与批量菜单和操作进度，清空前明确提示不可恢复；
清空记录放在记忆状态悬浮详情中，与开关状态分开展示。

## 调用和图片结果

`CallOutcome` 的当前值为 `success`、`failed`、`rate_limited`、`text_review`、`partial_success` 和 `unknown`。日志、实时监控和概览读取同一套后端结果投影；它们可以显示不同粒度，但不能各自重新分类。

图片 Call Record 的 `request_meta` 记录请求中的尺寸、质量、张数和返回格式等参数；Responses 的图片工具参数由同一个提取入口读取。这些字段表示请求值，不代表上游实际采用了相应质量或尺寸。`raw_detail.result_images` 按已返回图片保存实际 `width`、`height`，无法识别宽高的图片保留空对象，列表和详情显示“未知”，不以请求尺寸代填。`result_data_count` 记录结果数量。

日志摘要的 `presentation.request.parameters` 提供请求尺寸、质量和返回格式，`presentation.result.resolution` 提供去重后的实际分辨率。列表的尺寸列只展示实际分辨率，请求参数和每张图片的分辨率在详情中查看。列表不逐条读取详情或图片文件，缺少元数据的历史日志不追溯补充。

普通图片响应、聊天生图、Responses、SSE 和 Studio 任务复用日志元数据提取。SSE 仅累计结果元数据，不保留整段图片流；内部 `_image_metadata` 在对外响应前移除。宽高复用图片结果整理阶段已读取的图片头信息，日志不会额外下载或解码图片。终端的 `image_single_done` 成功事件也包含请求尺寸、质量、返回格式、数量和实际宽高。历史日志不追溯补充这些字段。

图片任务是独立的异步资源。任务存储状态为 `queued`、`running`、`success` 或 `error`；`/api/image-tasks` 再根据结果数量和失败分类投影为 `success`、`partial_success`、`failed` 或 `text_review`。`text_review` 表示上游返回可展示文本，而不是图片生成失败后再由前端推断出的状态。

可编辑文件任务同样是独立的异步资源，但不复用图片任务字段。`/v1/editable-file-tasks` 直接返回 `queued`、`running`、`success` 或 `error`；成功结果包含主文件和 ZIP 下载地址，Studio 只按该投影更新会话状态与下载操作。任务的创建、查询和删除按用户密钥隔离；成功发布后的 `/files/...` 是与图片一致的公开资产地址，只校验存储路径和文件存在性，不反查任务记录。Editable File Task Service 持有固定 20 分钟总时限，一次上游准备、生成、轮询和下载共享同一截止时间；前端轮询不拥有该时限。

## 页面生命周期

`usePageRuntime` 与 `usePageQuery` / `usePagedQuery` 统一页面请求生命周期：

1. 首次加载没有快照时显示加载态。
2. 有快照后的刷新保留旧结果，不把页面清空。
3. 成功后以新投影替换快照；空结果和请求错误是不同状态。
4. 只有需要实时更新的页面在可见时串行轮询；页面隐藏后停止。

这套生命周期属于前端交互层，不改变后端的业务结果。

## 变更顺序

改变业务含义时，先修改后端服务和 Pydantic 契约，再修改前端 API 适配和页面渲染。不能先在页面中临时拼接规则，再把该规则复制到其他页面。
