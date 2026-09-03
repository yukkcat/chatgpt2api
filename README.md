<p align="center">
  <img src="web-vue/public/logo.svg" width="112" alt="ChatGPT2API logo" />
</p>

<h1 align="center">ChatGPT2API</h1>

<p align="center">将 ChatGPT 官网能力接入 OpenAI 兼容 API，并提供面向多账号、图片任务与自托管场景的管理控制台。</p>

<p align="center">
  <strong>简体中文</strong> · <a href="./README_EN.md">English</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-v3.2.2-111827" alt="Version v3.2.2" />
  <img src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white" alt="Python 3.13" />
  <img src="https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white" alt="Vue 3" />
  <img src="https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL 18" />
  <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" alt="Docker ready" />
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-AGPL--3.0-blue" alt="License AGPL-3.0" /></a>
</p>

<p align="center">
  <a href="https://github.com/yukkcat/chatgpt2api/releases/tag/v3.2.2">v3.2.2 Release</a>
  · <a href="./CHANGELOG.md">更新说明</a>
  · <a href="./docs/README.md">维护文档</a>
</p>

> [!IMPORTANT]
> `v3.0.0` 是新的发布起点。远程 `main` 历史已重新整理，旧版本源代码、Git 标签、Release 和容器镜像不再作为当前发布线维护。3.0 使用全新的 Application Database，不能直接读取 2.x 的分散存储数据；升级时请重新配置或导入账号。

> [!WARNING]
> 本项目通过逆向研究接入 ChatGPT 官网的文本、图片和文件生成能力，并非 OpenAI 官方服务。接口可能随上游变化失效，并可能导致账号受限、临时或永久封禁；请勿使用重要、常用或高价值账号。
>
> 使用者须自行了解技术、账号与合规风险，遵守 OpenAI 服务条款及当地法律法规。严禁用于批量滥用、恶意竞争、账号盗用、诈骗、骚扰，以及生成或传播违法、暴力、色情或涉及未成年人的内容；使用者自行承担全部风险与责任。

<p align="center">
  <a href="https://qm.qq.com/q/yegwCqJisS">QQ 交流群：1005859624</a>
  &nbsp;&nbsp;·&nbsp;&nbsp; <a href="https://pay.ldxp.cn/shop/yukkcat">购买生图账号</a>
  &nbsp;&nbsp;·&nbsp;&nbsp; <a href="https://api.klong.lat">生图 API：小量 ¥0.02/张 · 中转 ¥0.01/张 · 大量/企业 ¥0.009/张</a>
</p>

## 赞助商

<table width="100%">
  <tr>
    <td align="center" valign="middle">
      <a href="https://www.ipwo.net/?ref=githubchatgpt2api"><img src="docs/images/IPWO.png" width="100%" alt="IPWO住宅代理"></a>
    </td>
  </tr>
  <tr>
    <td valign="middle">
      &nbsp;<strong><a href="https://www.ipwo.net/?ref=githubchatgpt2api"><u>IPWO</u></a></strong>&nbsp;覆盖195+地区动态住宅代理、静态住宅代理和不限量住宅代理支持HTTP、HTTPS及SOCKS5协议，为AI应用、多账号管理、自动化及海外网络访问提供灵活的代理解决方案。专属折扣码：<strong>0205</strong>
    </td>
  </tr>
</table>

## 快速部署

### 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/yukkcat/chatgpt2api/main/deploy/install.sh | sudo bash
```

安装时可选择 SQLite、本地 PostgreSQL 18 容器或已有 PostgreSQL URL。SQLite 无需额外配置；本地 PostgreSQL 由 Compose 自动启动并持久化。

固定安装 `v3.2.2`：

```bash
curl -fsSL https://raw.githubusercontent.com/yukkcat/chatgpt2api/v3.2.2/deploy/install.sh | sudo bash -s -- --branch v3.2.2
```

### Docker Compose

默认使用 SQLite：

```bash
git clone https://github.com/yukkcat/chatgpt2api.git
cd chatgpt2api
cp .env.example .env
# 编辑 .env，为 CHATGPT2API_AUTH_KEY 设置私有密钥
test -f config.json || printf '{}\n' > config.json
docker compose up -d
```

| 入口            | 地址                       |
| :-------------- | :------------------------- |
| 管理控制台      | `http://localhost:3000`    |
| OpenAI 兼容 API | `http://localhost:3000/v1` |
| 数据目录        | `./data`                   |

`.env` 中的 `CHATGPT2API_AUTH_KEY` 优先于 `config.json` 的 `auth-key`。Compose 使用独立运行时卷支持控制台在线更新；控制台设置、账号、用户密钥、调用日志和指标写入 Application Database。不要提交本地 `.env`、`config.json` 或 `data/`。

### PostgreSQL 18

在 `.env` 中设置 `POSTGRES_PASSWORD`，再叠加 PostgreSQL Compose：

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d
```

该模式使用 `postgres:18-alpine` 和命名卷持久化数据，默认不暴露数据库端口。连接已有 PostgreSQL 时直接设置：

```env
DATABASE_URL=postgresql://user:password@host:5432/database
```

完整的升级、备份、PostgreSQL 和故障排查说明见 [部署文档](./docs/deployment.md)。

## 核心能力

通用 UI 组件、主题和基础交互来自 [yukkcat/nanocat-ui](https://github.com/yukkcat/nanocat-ui)；本项目负责业务页面、后端状态投影和产品流程。

|       | 领域       | 能力                                                                                                           |
| :---: | :--------- | :------------------------------------------------------------------------------------------------------------- |
|   🔌   | API 网关   | Chat Completions、Responses、Messages、搜索、图片生成、图片编辑、PPT / PSD 与统一可编辑文件任务                |
|   💬   | 对话画图   | 文本对话、联网搜索、文生图、图生图、多图参考、局部编辑、Markdown、代码高亮、引用来源和推理强度                 |
|   👥   | 账号管理   | 手动添加、OAuth、Access Token、Session JSON、CPA、远程 CPA、Sub2API 导入，以及搜索、筛选、分组、导出和批量处理 |
|   🔑   | 凭证与额度 | 独立展示 AT / RT 状态，支持 RT 刷新 AT、同步套餐与额度、指定账号文本/画图测试和异常账号处置                    |
|   ⚙️   | 调度与并发 | 多账号选择、账号处理并发、单账号图片并发、多图并行、失败换号、额度与限流状态管理                               |
|   🌐   | 代理出口   | 账号代理、账号组代理、多出口代理组、节点图片并发、轮换间隔、默认出口、备用出口和连通性检测                     |
|   📊   | 日志与监控 | 调用日志、活跃请求、最近完成、慢请求、账号切换、出口信息、图片阶段时间线和原始上游诊断                         |
|   🖼️   | 图片与文件 | 本地 / WebDAV 存储、图库、标签、缩略图、下载、ZIP、压缩、清理、PPT / PSD 产物和可选图片放大                    |
|   ✨   | 提示词库   | 本地提示词资产、云端来源同步、分类选择和更新状态管理                                                           |
|   💾   | 数据与备份 | SQLite、PostgreSQL 18、R2 备份、保留策略，以及调用趋势、成功率和模型统计                                       |
|   🖥️   | 管理控制台 | 概览、账号、代理、日志、实时监控、图片、对话画图和系统设置，适配桌面与移动端                                   |

## 架构

```mermaid
flowchart LR
  Client["兼容 API 客户端"] --> API["/v1 兼容 API"]
  User["管理员 / Web 用户"] --> Console["Vue 管理控制台"]
  API --> Services["业务服务"]
  Console --> AdminAPI["/api 管理接口"]
  AdminAPI --> Services
  Services --> Scheduler["账号调度与代理出口"]
  Scheduler --> Upstream["ChatGPT Web"]
  Services --> AppDB["Application Database<br/>SQLite / PostgreSQL 18"]
  Services --> Assets["图片与生成文件<br/>本地 / WebDAV"]
  Services --> Monitor["进程内实时监控"]
  Services --> Backup["R2 备份"]
```

Application Database 保存账号、用户密钥、设置、日志和指标；图片与生成文件使用独立文件存储。详见 [存储架构](./docs/storage-architecture.md)。

## API

所有 AI 接口使用 Bearer Key：

```http
Authorization: Bearer <auth-key>
```

| 接口                                | 方法         | 说明                                                 |
| :---------------------------------- | :----------- | :--------------------------------------------------- |
| `/v1/models`                        | `GET`        | 返回本地目录与上游实时模型合并后的模型列表           |
| `/v1/chat/completions`              | `POST`       | 文本、搜索和图片场景的 Chat Completions 入口         |
| `/v1/responses`                     | `POST`       | 支持文本、搜索和图片工具调用的 Responses 入口        |
| `/v1/messages`                      | `POST`       | Anthropic Messages 兼容入口                          |
| `/v1/search`                        | `POST`       | 返回回答、引用来源和搜索结果                         |
| `/v1/images/generations`            | `POST`       | 图片生成，支持 `n=1..4`                              |
| `/v1/images/edits`                  | `POST`       | multipart、远程 URL、base64、data URL 和多参考图编辑 |
| `/v1/editable-file-tasks`           | `GET / POST` | 创建与查询 PPT / PSD 可编辑文件任务                  |
| `/v1/editable-file-tasks/{task_id}` | `DELETE`     | 删除当前密钥所属任务                                 |
| `/v1/ppt/generations`               | `POST`       | PPT 任务快捷入口                                     |
| `/v1/psd/generations`               | `POST`       | PSD 任务快捷入口                                     |
| `/files/{file_path}`                | `GET`        | 公开下载随机存储路径下的生成文件                     |

文件任务的创建、查询和删除按 API Key 隔离；任务返回的 `/files/...` 链接与生成图片一样无需鉴权，持有链接即可下载。公开下载会校验路径及文件类型，拒绝路径穿越。

<details>
<summary>Chat Completions 示例</summary>

```bash
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{"model":"gpt-5","messages":[{"role":"user","content":"介绍一下这个项目"}],"stream":true}'
```

</details>

<details>
<summary>图片生成示例</summary>

```bash
curl http://localhost:3000/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{"model":"gpt-image-2","prompt":"一只漂浮在太空里的猫，电影感光影","n":1,"response_format":"b64_json"}'
```

</details>

实际可用模型以上游账号和 `/v1/models` 返回值为准。

## 关键配置

| 配置                             | 默认值       | 用途                                                                                     |
| :------------------------------- | :----------- | :--------------------------------------------------------------------------------------- |
| `CHATGPT2API_AUTH_KEY`           | 必填         | 管理员和默认 API Key，环境变量优先于 `config.json`                                       |
| `DATABASE_URL`                   | SQLite       | Application Database 连接；未设置时使用 `data/chatgpt2api.db`                            |
| `CHATGPT2API_BASE_URL`           | 当前服务地址 | 生成对外可访问的图片和文件 URL                                                           |
| `CHATGPT2API_THREAD_TOKENS`      | `120`        | 后端同步工作线程并发容量，只要求正整数且不设固定最高值；账号、代理和上游仍有各自并发限制 |
| `account_processing_concurrency` | `30`         | 账号导入、刷新、同步和批量处理容量                                                       |
| `image_account_concurrency`      | `1`          | 单账号图片并发上限，可设置为 1–3                                                         |
| `image_stream_timeout_secs`      | `80`         | 图片上游 SSE / HTTP 流最长等待时间                                                       |
| `image_poll_timeout_secs`        | `60`         | 图片结果解析与轮询最长等待时间                                                           |
| `log_retention_hours`            | `24`         | 调用日志自动保留小时数                                                                   |

其余设置通过控制台维护。配置项的权威默认值与约束以当前接口投影为准。

## 效果展示

<table width="100%">
  <tr><td width="50%"><img src="docs/images/1.png" alt="控制台截图 1"></td><td width="50%"><img src="docs/images/2.png" alt="控制台截图 2"></td></tr>
  <tr><td width="50%"><img src="docs/images/3.png" alt="控制台截图 3"></td><td width="50%"><img src="docs/images/4.png" alt="控制台截图 4"></td></tr>
  <tr><td width="50%"><img src="docs/images/5.png" alt="控制台截图 5"></td><td width="50%"><img src="docs/images/6.png" alt="控制台截图 6"></td></tr>
</table>

## 本地开发

```bash
# 后端：Python 3.13 + uv
uv sync
uv run main.py

# 前端：Node.js + npm
cd web-vue
npm install
npm run dev
```

默认开发地址为 `http://localhost:5173`，后端接口由 Vite 开发代理转发。

## 文档

| 文档                                               | 内容                                 |
| :------------------------------------------------- | :----------------------------------- |
| [文档索引](./docs/README.md)                       | 当前架构与维护文档入口               |
| [部署与运维](./docs/deployment.md)                 | Docker、PostgreSQL、升级、备份与排障 |
| [存储架构](./docs/storage-architecture.md)         | Application Database 与文件存储边界  |
| [控制台架构](./docs/control-panel-architecture.md) | 前后端职责、业务投影与交互状态       |
| [图片失败处理](./docs/image-failure-handling.md)   | 图片失败分类、重试与账号处置         |
| [上游 SSE](./docs/upstream-sse-conversation.md)    | 会话与流式解析边界                   |

文档与实现冲突时，以当前代码、测试和公开接口契约为准。

## 许可证

本仓库当前版本以 [GNU Affero General Public License v3.0](./LICENSE)（`AGPL-3.0-only`）发布。修改后通过网络提供服务时，须按协议向服务用户提供对应源码。

源自 [basketikun/chatgpt2api](https://github.com/basketikun/chatgpt2api) 的代码继续保留原 MIT 版权与许可声明，详见 [NOTICE](./NOTICE)。此前已按 MIT 发布的版本仍适用其原许可证。

## 本项目贡献者

<a href="https://github.com/yukkcat/chatgpt2api/graphs/contributors">
  <img alt="ChatGPT2API Contributors" src="https://contrib.rocks/image?repo=yukkcat/chatgpt2api" />
</a>

## 原版项目与贡献者

本项目基于 [basketikun/chatgpt2api](https://github.com/basketikun/chatgpt2api) 演进。感谢原项目作者与所有贡献者：

<a href="https://github.com/basketikun/chatgpt2api/graphs/contributors">
  <img alt="Contributors" src="https://contrib.rocks/image?repo=basketikun/chatgpt2api" />
</a>

## 社区与友链

- QQ 交流群：[1005859624](https://qm.qq.com/q/yegwCqJisS)
- 社区：[Linux.do](https://linux.do)
