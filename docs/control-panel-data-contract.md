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

## 调用和图片结果

`CallOutcome` 的当前值为 `success`、`failed`、`rate_limited`、`text_review`、`partial_success` 和 `unknown`。日志、实时监控和概览读取同一套后端结果投影；它们可以显示不同粒度，但不能各自重新分类。

图片任务是独立的异步资源。任务存储状态为 `queued`、`running`、`success` 或 `error`；`/api/image-tasks` 再根据结果数量和失败分类投影为 `success`、`partial_success`、`failed` 或 `text_review`。`text_review` 表示上游返回可展示文本，而不是图片生成失败后再由前端推断出的状态。

可编辑文件任务同样是独立的异步资源，但不复用图片任务字段。`/v1/editable-file-tasks` 直接返回 `queued`、`running`、`success` 或 `error`；成功结果包含主文件和 ZIP 下载地址，Studio 只按该投影更新会话状态与下载操作。任务的创建、查询和删除按用户密钥隔离；成功发布后的 `/files/...` 是与图片一致的公开资产地址，只校验存储路径和文件存在性，不反查任务记录。

## 页面生命周期

`usePageRuntime` 与 `usePageQuery` / `usePagedQuery` 统一页面请求生命周期：

1. 首次加载没有快照时显示加载态。
2. 有快照后的刷新保留旧结果，不把页面清空。
3. 成功后以新投影替换快照；空结果和请求错误是不同状态。
4. 只有需要实时更新的页面在可见时串行轮询；页面隐藏后停止。

这套生命周期属于前端交互层，不改变后端的业务结果。

## 变更顺序

改变业务含义时，先修改后端服务和 Pydantic 契约，再修改前端 API 适配和页面渲染。不能先在页面中临时拼接规则，再把该规则复制到其他页面。
