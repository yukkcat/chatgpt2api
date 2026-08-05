# 稳定代理与 Cloudflare Clearance

状态：当前

默认出口和 clearance 是两套职责明确的配置。顶层 `proxy` 是唯一默认出口，只支持直连、代理组或自定义代理；`proxy_runtime` 只保存资源专用代理、TLS 和 clearance 会话能力，不会偷偷替代默认出口。

## WARP Compose

`docker-compose.warp.yml` 组合了以下服务：

| 服务 | 责任 | Compose 内地址 |
| --- | --- | --- |
| `warp-proxy` | WARP SOCKS5 出口 | `socks5://warp-proxy:1080` |
| `privoxy` | 将 SOCKS5 转为 HTTP 代理 | `http://privoxy:8118` |
| `flaresolverr` | 获取 Cloudflare clearance bundle | `http://flaresolverr:8191` |
| `init-config` | 在适用时写入 WARP 默认出口和代理会话默认值 | - |
| `app` | ChatGPT2API 主服务 | `http://localhost:3000` |

启动：

```bash
docker compose -f docker-compose.warp.yml up -d
docker compose -f docker-compose.warp.yml ps
```

`warp-proxy`、`privoxy` 和 `flaresolverr` 的辅助端口默认只绑定到 `127.0.0.1`。主服务 `app` 使用 `${CHATGPT2API_PORT:-3000}:80`，默认遵循 Compose 的全网卡端口绑定行为；远程访问前应配置防火墙、反向代理或显式绑定地址，且不要直接暴露内部代理服务。

## 配置模型

默认出口在代理管理页维护。`proxy_runtime` 的关键字段是：

| 字段 | 作用 |
| --- | --- |
| `enabled` | 是否启用代理会话能力 |
| `resource_proxy_url` | 明确标记为资源请求时可选的专用代理 |
| `clearance.enabled` | 是否启用 clearance bundle |
| `clearance.mode` | `none`、`manual` 或 `flaresolverr` |
| `clearance.flaresolverr_url` | FlareSolverr 服务地址 |
| `clearance.timeout_sec` | 单次 FlareSolverr 获取超时 |
| `clearance.refresh_interval` | 缓存 bundle 的有效期 |

在 Compose 内，FlareSolverr 地址通常是 `http://flaresolverr:8191`；主服务直接在宿主机运行时，地址通常是 `http://127.0.0.1:8191`。

后台设置页通过 `GET /api/proxy/runtime` 读取代理会话状态，通过 `PATCH /api/settings` 保存配置。默认出口由代理管理页单独维护；测试代理和测试 clearance 也由后端执行，敏感 cookie 不会回显到控制台。

## Clearance 的实际行为

FlareSolverr mode 的 bundle 以 **规范化代理 URL + 目标 host** 作为缓存键。同一个键在并发刷新时只会有一个实际刷新请求，其他请求复用该次结果。请求发送时只会附带已经缓存且适用于当前 host / 代理的 cookie 与 User-Agent。

当前实现的显式刷新入口是 clearance 测试：`POST /api/proxy/clearance/test`。普通上游请求会使用已有缓存，但不会因为每一次 403 自动向 FlareSolverr 重新获取 clearance。因此在更新或排查 clearance 后，应主动运行一次测试，确认 bundle 已生成；不要把“已启动 FlareSolverr 容器”理解为每个请求都会自动绕过拦截。

## 排查顺序

1. 检查 `warp-proxy`、`privoxy`、`flaresolverr` 和 `app` 都在运行。
2. 在代理管理页确认默认出口可用，再在设置页确认代理会话和 clearance 配置。
3. 先测试默认出口，再测试 clearance。
4. 查看主服务和 FlareSolverr 日志，确认目标 host、代理和返回状态。
5. 若 clearance 失败，检查出口 IP、目标站策略、FlareSolverr 浏览器启动和代理连通性。

常用日志：

```bash
docker logs -f chatgpt2api-warp
docker logs -f chatgpt2api-flaresolverr
```

不要把 `cf_clearance`、完整 Cookie、代理密码或 User Key 写进截图、Issue 或版本库。
