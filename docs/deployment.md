# 部署与升级

状态：当前

本项目的发布镜像默认是 `ghcr.io/yukkcat/chatgpt2api:latest`。标准 Compose 将服务暴露在 `3000` 端口，并挂载本地 `data/` 和 `config.json`。运行时配置和数据不应提交到 Git。

## Docker 部署

```bash
git clone https://github.com/yukkcat/chatgpt2api.git
cd chatgpt2api
cp .env.example .env
# 将 .env 中的 CHATGPT2API_AUTH_KEY=your_secret_key_here 替换为私有密钥。
test -f config.json || printf '{}\n' > config.json
docker compose up -d
```

### 本地 PostgreSQL 18

需要由 Compose 一并运行 PostgreSQL 时，在 `.env` 中设置数据库密码：

```dotenv
POSTGRES_PASSWORD=replace_with_a_strong_password
```

然后同时加载基础 Compose 和 PostgreSQL overlay：

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d
```

`docker-compose.postgres.yml` 使用官方 `postgres:18-alpine` 镜像，等待数据库健康后再启动应用，并将数据持久化到 `chatgpt2api-postgres-data` 命名卷。数据库端口默认不暴露到宿主机。

`POSTGRES_PASSWORD` 会同时用于初始化数据库和构造 `DATABASE_URL`，因此请仅使用 URL 安全字符（字母、数字、下划线或连字符），不要在两个位置分别编码密码。
启用该模式后，后续启动、升级、查看状态和停止服务都应同时指定这两个 Compose 文件。

查看状态与日志：

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml ps
docker compose -f docker-compose.yml -f docker-compose.postgres.yml logs -f postgres app
```

`.env` 中的 `CHATGPT2API_AUTH_KEY` 优先于 `config.json` 的 `auth-key`。若要使用 `config.json`，先删除或注释 `.env` 中的该值，再填写 `auth-key`。

默认地址：

- 控制台：`http://localhost:3000`
- API：`http://localhost:3000/v1`

也可以使用仓库安装脚本：

```bash
curl -fsSL https://raw.githubusercontent.com/yukkcat/chatgpt2api/main/deploy/install.sh | sudo bash
```

安装脚本会明确询问 Application Database：

- SQLite 本地文件（默认）
- PostgreSQL 18 本地容器（Docker 模式）
- 已有 PostgreSQL URL

选择本地 PostgreSQL 时，脚本会自动生成并保存数据库密码，下载 `docker-compose.postgres.yml`，再与主 Compose 一起启动。重复运行安装脚本会复用已有密码。`CHATGPT2API_THREAD_TOKENS` 默认是 `120`，表示后端同步工作线程的并发容量，只要求正整数且不设置人为最高值；账号、代理和上游服务仍分别执行自己的并发限制。

## 本地开发

后端：

```bash
git clone https://github.com/yukkcat/chatgpt2api.git
cd chatgpt2api
uv sync
uv run main.py
```

Vue 控制台：

```bash
cd web-vue
npm install
npm run dev
```

前端开发服务器默认使用 Vite 端口；后端仍读取项目根目录的 `config.json` 和 `data/`。

## 存储边界

`DATABASE_URL` 选择 Application Database；未设置时使用
`data/chatgpt2api.db`。支持 SQLite 与 PostgreSQL 18，不再通过
`STORAGE_BACKEND` 选择 JSON、Git 或账号专用数据库。

选择数据库不是旧数据迁移操作，不会自动导入 JSON、JSONL、Git 或旧账号
SQLite 文件。图片文件及其相关索引仍按图片存储边界管理。完整边界见
[`storage-architecture.md`](storage-architecture.md)。

## 升级

升级前先在系统设置中执行一次 R2 备份，并确认状态为成功。备份归档始终包含
Application Database：SQLite 使用 `data/application-database.sqlite3`，PostgreSQL
使用 `data/application-database.pgdump`。图片任务记录、PPT / PSD 文件和图片目录
按备份设置选择；外部 WebDAV 仍需独立备份。

未配置 R2 时，应先停止服务再备份。SQLite 可以在停服后复制 `data/chatgpt2api.db`；
PostgreSQL 必须使用 `pg_dump --format=custom`，不能用 `tar data/` 代替数据库备份。
`config.json` 只保留 `auth-key` 等启动配置，也应单独保存：

```bash
pg_dump --format=custom --no-owner --no-privileges "$DATABASE_URL" \
  > backups/chatgpt2api-$(date +%Y%m%d-%H%M%S).pgdump
```

本地 PostgreSQL Compose 可直接在数据库容器内导出：

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml exec -T postgres \
  sh -c 'pg_dump --format=custom --no-owner --no-privileges \
  -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  > backups/chatgpt2api-$(date +%Y%m%d-%H%M%S).pgdump
```

镜像部署升级：

```bash
docker compose pull
docker compose up -d
```

本地 PostgreSQL Compose 部署升级：

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml pull
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d
```

镜像部署固定或回退版本时，在 `.env` 设置 `CHATGPT2API_IMAGE=ghcr.io/yukkcat/chatgpt2api:<tag>`，再执行对应的 `pull` 与 `up`。Git 检出标签只影响源码运行，不会改变 Compose 使用的镜像版本。升级后检查：

```bash
docker compose ps
docker logs -f chatgpt2api
```

## 回滚与维护

先停止对应 Compose，再恢复经过验证的代码 / 镜像和备份数据；不要在运行时直接覆盖 `data/`。常用命令：

```bash
docker compose restart
docker compose down
```

`docker image prune` 只清理未使用镜像，不会替代数据备份。
