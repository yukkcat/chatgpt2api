<p align="center">
  <img src="web-vue/public/logo.svg" width="120" alt="ChatGPT2API logo" />
</p>
<h1 align="center">ChatGPT2API</h1>

<p align="center">ChatGPT 官网能力 → OpenAI 兼容 API 网关</p>
<p align="center">
  <img src="https://img.shields.io/badge/License-CNC--1.0-red.svg" />
  <img src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-ready-009688?logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white" />
  <img src="https://img.shields.io/badge/Vite-7-646CFF?logo=vite&logoColor=white" />
  <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" />
</p>
<p align="center"><strong>当前稳定版本：v3.0.0</strong> | <a href="https://github.com/yukkcat/chatgpt2api/releases/tag/v3.0.0">发布说明</a> | <a href="https://github.com/yukkcat/chatgpt2api/releases">全部版本</a></p>

---

## 联系我们

点击链接加入群聊【gemini/gpt-2API 交流群】：

- [https://qm.qq.com/q/yegwCqJisS](https://qm.qq.com/q/yegwCqJisS)

---

## 项目定位

本仓库基于原版 [basketikun/chatgpt2api](https://github.com/basketikun/chatgpt2api) 整理维护，核心仍是把 ChatGPT 官网能力封装为 OpenAI 兼容 API。

本版本使用新的 Vue 控制台，主题和交互与原版前端不同；除前端实现差异外，接口、配置和部署口径会尽量保持与原版一致。

在原版基础上，本分支重点扩展了多出口代理组、备用出口、图片链路诊断、对话画图 WebUI、远程账号导入、图片存储管理和搜索/推理强度等能力，目标是在保持 OpenAI 兼容入口的同时，提供更适合自托管、多账号和高并发图片场景的管理体验。

发布仓库只保留主服务、Vue 控制台、必要部署文件和长期维护文档；旧版前端、测试记录、临时文档和运行产物不进入发布内容。

---

## 核心能力

- OpenAI 兼容接口：覆盖图片生成、图片编辑、文本对话、Responses、Messages、网页搜索、PPT/PSD/可编辑文件任务等已实现链路，可接入常见 SDK、网关或客户端。
- 对话画图工作台：把文本对话、搜索、文生图、图生图、PPT/PSD 可编辑文件、多图参考、Markdown 渲染、官网式引用、推理强度和异步任务进度放在同一会话里。
- 图片链路诊断：记录账号、出口、conversation id、上游原始错误、SSE/轮询/下载阶段耗时，支持实时监控和调用日志排查。
- 多账号调度：支持账号导入、刷新、额度读取、分组、代理优先级、异常账号自动移除和批量管理。
- 远程账号导入：支持本地 CPA JSON、远程 CPA、Sub2API、access token 导入；Sub2API / CPA 可按远程分组折叠选择、全组选中、去重和批量导入。
- 代理与稳定出口：支持账号代理、账号组代理、多出口代理组、节点并发、备用出口、WARP / Privoxy / FlareSolverr 稳定代理运行时和 Cloudflare clearance 测试。
- 管理控制台：包含概览中心、账号管理、日志管理、实时监控、图片管理/存储管理、代理管理、对话画图和系统设置。
- 自托管部署：支持 Docker、一键脚本、SQLite / PostgreSQL 18 Application Database、WebDAV 图片存储和 R2 备份。

---

## 功能架构

```mermaid
flowchart TB
  Admin["管理员"] --> Console["Vue 管理控制台"]
  User["普通用户 / 画图用户"] --> Studio["对话画图"]
  Client["OpenAI 兼容客户端"] --> Gateway["/v1 兼容 API"]

  subgraph ConsoleModules["控制台模块"]
    Dashboard["概览中心"]
    Accounts["账号管理 / 远程导入"]
    Logs["调用日志"]
    Monitor["实时监控"]
    Gallery["图片管理"]
    Proxy["代理 / 代理组"]
    Settings["系统设置"]
  end

  Console --> ConsoleModules
  Studio --> Gateway
  Gateway --> Protocol["ChatGPT Web 协议层"]
  Protocol --> Upstream["ChatGPT 官网"]
  Protocol --> AccountsPool["账号调度 / 代理出口"]
  Protocol --> CallRecords["调用记录"]
  Protocol --> LiveMonitor["实时监控<br/>进程内窗口"]
  Protocol --> ImageStore["图片 / 生成文件<br/>本地或 WebDAV"]
  ConsoleModules --> AdminAPI["/api 管理接口"]
  AdminAPI --> DomainServices["领域服务 / Repository"]
  DomainServices --> ApplicationDB["Application Database<br/>SQLite / PostgreSQL 18<br/>账号 / User Key / 设置 / 日志 / 指标"]
  DomainServices --> TaskStore["图片任务 / 图片索引 / 生成文件<br/>独立文件存储"]
  DomainServices --> LiveMonitor
```

> [!WARNING]
> 免责声明：
>
> 本项目涉及对 ChatGPT 官网文本生成、图片生成与图片编辑等相关接口的逆向研究，仅供个人学习、技术研究与非商业性技术交流使用。
>
> - 严禁将本项目用于任何商业用途、盈利性使用、批量操作、自动化滥用或规模化调用。
> - 严禁将本项目用于破坏市场秩序、恶意竞争、套利倒卖、二次售卖相关服务，以及任何违反 OpenAI 服务条款或当地法律法规的行为。
> - 严禁将本项目用于生成、传播或协助生成违法、暴力、色情、未成年人相关内容，或用于诈骗、欺诈、骚扰等非法或不当用途。
> - 使用者应自行承担全部风险，包括但不限于账号被限制、临时封禁或永久封禁以及因违规使用等所导致的法律责任。
> - 使用本项目即视为你已充分理解并同意本免责声明全部内容；如因滥用、违规或违法使用造成任何后果，均由使用者自行承担。
> - 本项目基于对 ChatGPT 官网相关能力的逆向研究实现，存在账号受限、临时封禁或永久封禁的风险。请勿使用你自己的重要账号、常用账号或高价值账号进行测试。

## 快速开始

### 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/yukkcat/chatgpt2api/main/deploy/install.sh | sudo bash
```

固定安装当前稳定版：

```bash
curl -fsSL https://raw.githubusercontent.com/yukkcat/chatgpt2api/v3.0.0/deploy/install.sh | sudo bash -s -- --branch v3.0.0
```

### Docker 运行

```bash
git clone https://github.com/yukkcat/chatgpt2api.git
cd chatgpt2api
cp .env.example .env
# 将 .env 中的 CHATGPT2API_AUTH_KEY=your_secret_key_here 替换为私有密钥。
test -f config.json || printf '{}\n' > config.json
docker compose up -d
```

如需同时启动本地 PostgreSQL 18，在 `.env` 中设置 `POSTGRES_PASSWORD` 后叠加数据库 Compose：

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d
```

该模式使用命名卷持久化数据库，不默认向宿主机暴露 PostgreSQL 端口。`POSTGRES_PASSWORD` 请仅使用 URL 安全字符（字母、数字、下划线或连字符）。

`.env` 中的 `CHATGPT2API_AUTH_KEY` 优先于 `config.json` 的 `auth-key`。若要使用 `config.json`，先删除或注释 `.env` 中的该值，再填写 `auth-key`。
`config.json` 仅作为本地启动配置保留 `auth-key`；控制台中的系统设置存入 Application Database，不要把本地配置提交到仓库。

- Web 面板：`http://localhost:3000`
- API 地址：`http://localhost:3000/v1`
- 数据目录：`./data`

### WARP / FlareSolverr 稳定代理部署

如果图片链路经常遇到 Cloudflare 拦截，可以启用附带的 WARP + Privoxy + FlareSolverr 方案：

```bash
cp .env.example .env
# 将 .env 中的 CHATGPT2API_AUTH_KEY=your_secret_key_here 替换为私有密钥。
test -f config.json || printf '{}\n' > config.json
docker compose -f docker-compose.warp.yml up -d
```

该 compose 会启动：

- `warp-proxy`：提供 WARP SOCKS5 出口。
- `privoxy`：把 WARP SOCKS5 转成 HTTP 代理。
- `flaresolverr`：刷新 Cloudflare clearance。
- `init-config`：幂等写入 WARP 默认出口和代理会话配置。
- `app`：启动 ChatGPT2API 主服务。

默认只让上游 OpenAI / ChatGPT 请求走 WARP 默认出口，账号邮箱、CPA 等辅助链路不会被强制接管。出口优先级为账号个人代理 > 账号组代理/代理组 > 显式任务代理 > 默认出口 > 直连。

可在 `.env` 中调整端口和代理会话参数。默认出口在「代理管理」中选择直连、代理组或自定义代理；Cloudflare clearance 在设置页的「代理会话」面板维护。

### 维护文档

部署、存储边界、图片失败处理、控制台数据契约和内部 SSE 解析说明统一见 [`docs/README.md`](docs/README.md)。文档与实现冲突时，以当前代码、测试和公开接口契约为准。

### 本地开发

启动后端：

```bash
git clone https://github.com/yukkcat/chatgpt2api.git
cd chatgpt2api
uv sync
uv run main.py
```

启动前端：

```bash
cd web-vue
npm install
npm run dev
```

后续更新新版本：

```bash
git pull
docker compose up -d
```

### 应用数据库配置

结构化控制面数据使用 Application Database。未设置 `DATABASE_URL` 时默认使用
`data/chatgpt2api.db`；部署也可以通过 `DATABASE_URL` 连接 PostgreSQL 18。
选择新的数据库不会自动导入旧 JSON、Git 或账号 SQLite 数据。

示例：连接已有 PostgreSQL

```yaml
environment:
  - DATABASE_URL=postgresql://user:password@host:5432/dbname
```

仓库自带的本地 PostgreSQL 18 部署方式见 [`docs/deployment.md`](docs/deployment.md)。

## 功能详情

### API 兼容能力

> 兼容的是本项目已实现的 ChatGPT Web 逆向场景，不等同于官方 OpenAI 全量 API 代理。

- `GET /v1/models`：合并本地模型目录和上游实时模型，返回当前可暴露模型。
- `POST /v1/chat/completions`：支持文本、搜索和图片场景，支持 `stream`、`tools`、`web_search_options`、`reasoning_effort` / `thinking_effort`。
- `POST /v1/responses`：支持文本、搜索和图片工具调用，支持 `image_generation` 与 `web_search*` 工具。
- `POST /v1/messages`：Anthropic Messages 兼容入口，走同一账号池和调用日志。
- `POST /v1/search`：ChatGPT 搜索兼容入口，返回文本、引用来源和搜索结果信息。
- `POST /v1/images/generations`：图片生成，支持 `n=1..4`。
- `POST /v1/images/edits`：图片编辑，支持 multipart、远程 URL、base64、data URL 和多参考图。
- `POST /v1/editable-file-tasks`、`GET /v1/editable-file-tasks`：统一 PPT / PSD 可编辑文件任务。
- `POST /v1/ppt/generations`、`POST /v1/psd/generations`：PPT / PSD 生成快捷入口。
- `GET /files/{path}`：下载 PPT / PSD / 可编辑文件任务产物。

### 对话画图工作台

- 侧边栏会话 + 底部输入框布局，支持普通文本对话、搜索模式、文生图、图生图、PPT/PSD 可编辑文件和多图参考。
- 支持 `gpt-image-2`、`codex-gpt-image-2`、`auto` 以及模型目录返回的文本/搜索模型。
- 支持推理强度：低 / 中 / 高 / 超高，透传为 `reasoning_effort`。
- 支持 Markdown 渲染、代码块、搜索引用来源、官网式 `cite` / `image_group` 占位解析和图片建议展示。
- 搜索模式可按当前公开接口地址生成中英文 `chatgpt2api-search` Skill 安装指令；指令不嵌入登录密钥，运行时从 `CHATGPT2API_API_KEY` 环境变量读取。
- 图片任务内联展示生成中、成功和失败状态；切换会话后仍保留任务状态提示。
- 可编辑文件任务独立展示排队、生成、失败和下载状态，切回页面或刷新后会继续读取任务结果。
- 支持全屏偏好持久化、历史删除、清空、滚动定位和大量消息下的渲染性能优化。
- 可在系统设置中开启“图片成功后删除官网会话”，成功保存图片后尝试隐藏上游 ChatGPT conversation；默认关闭，便于保留恢复和排查现场。

### 图片链路和诊断

- 图片请求会记录 `call_id`、账号邮箱、模型、endpoint、conversation id、代理来源、代理组/节点和关键阶段耗时。
- 上游断流、SSE 超时、轮询超时、策略拒绝、文本回复但无图、图片解析/下载失败会尽量保留原始上游错误。
- `image_stream_timeout_secs` 控制上游 SSE/HTTP 流硬截止；`image_poll_timeout_secs` 控制结果解析和轮询总等待。
- 可通过实时监控查看活跃请求、入口排队、账号等待、出口等待、上游生成和慢请求分布。
- 可通过调用日志查看请求详情、错误码、上游原始诊断、图片结果和账号信息。

### 账号与导入

- 账号管理支持搜索、筛选、批量刷新、导出、编辑、分组、代理设置和异常账号处理。
- 异常账号不再走自动/手动重登；鉴权失效按“自动移除异常账号”开关决定删除或保留异常状态。
- 支持本地 CPA JSON、远程 CPA、Sub2API、access token 导入。
- 远程 CPA / Sub2API 连接可在设置页维护，也可在账号管理里打开统一导入弹窗。
- Sub2API 导入支持读取远程分组，按分组折叠、全组选中、单账号选择、按组导入和去重保存。

### 代理、存储和运维

- 代理优先级：账号个人代理 > 账号组代理/代理组 > 显式任务代理 > 默认出口 > 直连。
- 代理组支持多出口节点、节点图片并发、轮换间隔、健康展示和测试。
- 备用出口可用于图片早期 TLS / 连接超时失败后的重试，默认关闭。
- 支持本地图片存储、WebDAV、双写、图片索引、标签、下载、压缩和清理。
- R2 备份始终包含 Application Database，并可选包含图片任务记录、PPT / PSD 文件和图片文件目录。
- 概览中心的调用趋势、成功率和模型统计独立滚动保留最近 30 天。

### 关键配置项

| 配置项 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `image_stream_timeout_secs` | `80` | 图片上游 SSE / HTTP 流最长等待时间。 |
| `image_poll_timeout_secs` | `60` | 图片结果解析和轮询最长等待时间。 |
| `image_parallel_generation` | `true` | 多图请求是否并行生成。 |
| `image_account_concurrency` | `1` | 单账号图片并发上限，可设置为 1–3。 |
| `account_processing_concurrency` | `30` | 账号批量任务的进程级容量上限。远程刷新、同步、核验按账号占用并发；启用、禁用、重置、删除和批量保存按整个批次占用一个并发。可设置为 1–100，图片生成并发不受其控制。 |
| `image_remove_conversation_after_result` | `false` | 图片成功保存后尝试隐藏上游 ChatGPT 官网会话。 |
| `auto_remove_invalid_accounts` | `true` | 鉴权失效账号是否自动移除。 |
| `auto_remove_rate_limited_accounts` | `false` | 远程确认图片额度耗尽后是否自动移除账号。 |
| `log_retention_days` | `30` | 调用日志自动清理天数。 |
| `proxy` | `direct` | 默认出口，可设为直连、代理组引用或自定义代理 URL。 |
| `proxy_runtime` | 关闭 | 资源专用代理、TLS 和 Cloudflare clearance 会话配置，不参与默认出口选择。 |

### 状态说明

- 发布变更以 [CHANGELOG.md](./CHANGELOG.md) 为准。
- 仓库只保留发布必要文件和长期维护文档；被忽略的本地草稿、测试记录和运行产物不作为发布内容。

## 效果展示

<table width="100%">
  <tr>
    <td width="50%"><img src="docs/images/1.png" alt="screenshot 1" border="0"></td>
    <td width="50%"><img src="docs/images/2.png" alt="screenshot 2" border="0"></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/images/3.png" alt="screenshot 3" border="0"></td>
    <td width="50%"><img src="docs/images/4.png" alt="screenshot 4" border="0"></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/images/5.png" alt="screenshot 5" border="0"></td>
    <td width="50%"><img src="docs/images/6.png" alt="screenshot 6" border="0"></td>
  </tr>
</table>

## API

所有 AI 接口都需要请求头：

```http
Authorization: Bearer <auth-key>
```

管理接口需要管理员登录态或管理员 Key。普通用户 Key 默认只开放对话画图相关能力。

### 接口速览

| 接口 | 方法 | 说明 |
| :--- | :--- | :--- |
| `/v1/models` | `GET` | 返回当前模型列表。 |
| `/v1/chat/completions` | `POST` | Chat Completions 兼容入口，支持文本、搜索和图片场景。 |
| `/v1/responses` | `POST` | Responses 兼容入口，支持文本、搜索和图片工具调用。 |
| `/v1/messages` | `POST` | Messages 兼容入口。 |
| `/v1/search` | `POST` | ChatGPT 搜索兼容入口。 |
| `/v1/images/generations` | `POST` | OpenAI Images 文生图兼容入口。 |
| `/v1/images/edits` | `POST` | OpenAI Images 图生图 / 编辑兼容入口。 |
| `/v1/editable-file-tasks` | `GET/POST` | PPT / PSD / 可编辑文件任务创建与查询。 |
| `/v1/ppt/generations` | `POST` | PPT 生成任务快捷入口。 |
| `/v1/psd/generations` | `POST` | PSD 生成任务快捷入口。 |
| `/files/{file_path}` | `GET` | 公开下载 PPT/PSD 任务生成的文件。 |

文件任务的创建、查询和删除仍需 API Key，并按当前密钥隔离；结果返回的 `/files/...` 地址与生成图片一样无需鉴权，持有链接即可下载。公开路由仅接受随机存储目录下的 PPT、PSD 和 ZIP 文件，并校验路径与文件是否存在，不依赖任务记录的生命周期。

<details>
<summary><code>GET /v1/models</code></summary>
<br>

```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer <auth-key>"
```

返回本地模型目录与上游实时模型合并后的列表。实际可用模型以接口返回为准。

</details>

<details>
<summary><code>POST /v1/chat/completions</code></summary>
<br>

文本 / 搜索示例：

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{
    "model": "gpt-5",
    "messages": [
      {"role": "user", "content": "联网搜索并总结今天的 AI 新闻"}
    ],
    "tools": [{"type": "web_search_preview"}],
    "reasoning_effort": "medium"
  }'
```

聊天生图示例：

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{
    "model": "gpt-image-2",
    "messages": [
      {"role": "user", "content": "生成一张雨夜东京街头的赛博朋克猫"}
    ],
    "n": 1
  }'
```

常用字段：`model`、`messages`、`stream`、`tools`、`web_search_options`、`reasoning_effort`、`thinking_effort`、`reasoning.effort`、`n`。

</details>

<details>
<summary><code>POST /v1/responses</code></summary>
<br>

```bash
curl http://localhost:8000/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{
    "model": "gpt-5",
    "input": "生成一张未来感城市天际线图片",
    "tools": [{"type": "image_generation"}],
    "reasoning_effort": "high"
  }'
```

支持 `image_generation`、`web_search`、`web_search_preview`、`web_search_preview_2025_03_11`。

</details>

<details>
<summary><code>POST /v1/search</code></summary>
<br>

```bash
curl http://localhost:8000/v1/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{
    "prompt": "布偶猫性格特点是什么？"
  }'
```

返回搜索回答、引用来源和搜索结果结构；对话画图页会把官网式引用渲染为来源卡片。

</details>

<details>
<summary><code>POST /v1/images/generations</code></summary>
<br>

OpenAI 兼容图片生成接口，用于文生图。

```bash
curl http://localhost:8000/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "一只漂浮在太空里的猫",
    "n": 1,
    "response_format": "b64_json"
  }'
```

| 字段 | 说明 |
| :--- | :--- |
| `model` | 图片模型，推荐 `gpt-image-2` 或按 `/v1/models` 返回值选择。 |
| `prompt` | 图片生成提示词。 |
| `n` | 生成数量，当前限制 `1-4`。 |
| `size` | 可传官方尺寸字段，具体解析取决于上游能力。 |
| `response_format` | 默认兼容 `b64_json`，也会保存本地图片 URL 供日志和图库使用。 |

</details>

<details>
<summary><code>POST /v1/images/edits</code></summary>
<br>

OpenAI 兼容图片编辑接口，可上传图片文件，也可传图片链接 / base64 / data URL。

```bash
curl http://localhost:8000/v1/images/edits \
  -H "Authorization: Bearer <auth-key>" \
  -F "model=gpt-image-2" \
  -F "prompt=把这张图改成赛博朋克夜景风格" \
  -F "n=1" \
  -F "image=@./input.png"
```

JSON 图片 URL 示例：

```bash
curl http://localhost:8000/v1/images/edits \
  -H "Authorization: Bearer <auth-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "把这张图改成赛博朋克夜景风格",
    "images": [
      {"image_url": "https://example.com/input.png"}
    ],
    "n": 1
  }'
```

支持字段：`model`、`prompt`、`n`、`image`、`images`、`image_url`、`mask`。

</details>

<details>
<summary><code>POST /v1/messages</code></summary>
<br>

```bash
curl http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{
    "model": "gpt-5",
    "max_tokens": 1024,
    "messages": [
      {"role": "user", "content": "写一段产品介绍"}
    ]
  }'
```

</details>

<details>
<summary><code>POST /v1/editable-file-tasks</code></summary>
<br>

统一创建 PPT / PSD 等可编辑文件任务：

```bash
curl http://localhost:8000/v1/editable-file-tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{
    "kind": "ppt",
    "prompt": "做一份产品发布会 PPT"
  }'
```

查询任务：

```bash
curl "http://localhost:8000/v1/editable-file-tasks?task_id=<task_id>" \
  -H "Authorization: Bearer <auth-key>"
```

也可使用快捷入口：`POST /v1/ppt/generations`、`POST /v1/psd/generations`。

</details>

## 社区支持

学 AI , 上 L 站：[LinuxDO](https://linux.do)

## 原版项目贡献者

<a href="https://github.com/basketikun/chatgpt2api/graphs/contributors">
  <img alt="Contributors" src="https://contrib.rocks/image?repo=basketikun/chatgpt2api" />
</a>

## Star History

[![Star History Chart](https://api.star-history.com/chart?repos=yukkcat/chatgpt2api&type=date&legend=top-left)](https://www.star-history.com/?repos=yukkcat%2Fchatgpt2api&type=date&legend=top-left)
