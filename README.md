# jong-coolify-deploy

把一句“部署当前项目到我的 Coolify”变成完整交付：本地质量检查、必要的 Docker/Compose 改造、私有 GitHub 源码、Coolify 资源、域名、健康检查、部署日志和 HTTPS 验收。

```text
本地仓库 -> GitHub -> Coolify REST API -> 自有 VPS -> 域名/TLS -> 验收报告
```

## 适用场景

- 把当前或指定本地仓库部署到自有 Coolify VPS。
- 本地没有 remote，需要创建私有 GitHub 仓库再部署。
- 在 Application 与 Docker Compose Service 之间做正确选择。
- 要求环境变量在 Coolify UI 可编辑，并明确数据卷、健康检查和域名。
- 要求部署完成后检查状态、日志、DNS、TLS、深层路由和内部网络。

不适用于 Vercel/Cloudflare Pages、裸 VPS SSH 初始化、纯 DNS 教学、仅重启/看日志、仅转换 Compose 而不部署。

## 前置条件

- [ ] Coolify 已安装在目标 VPS，API 可访问。
- [ ] 已创建 Coolify API Token，并通过环境变量或 Codex 配置提供。
- [ ] 本机 `git` 可用；需要发布源码时，`gh auth status` 正常。
- [ ] 自定义域名已经能管理 DNS；自动写 Cloudflare DNS 时，Token 只放环境变量。

```bash
export COOLIFY_BASE_URL=https://coolify.example.com
export COOLIFY_API_TOKEN=...
```

在 Codex 中，如果没有显式环境变量，技能会复用：

```toml
[mcp_servers.coolify.env]
COOLIFY_BASE_URL = "https://coolify.example.com"
COOLIFY_ACCESS_TOKEN = "..."
```

配置文件应保持仅当前用户可读，例如权限 `600`。技能不会复制、打印或写回这些值。

实例域名直接替换成自己的即可。Coolify MCP 是可选适配层；API 不可用时停止远程写入，不降级为 SSH 或直接操作 VPS Docker。

## 安装

只安装到 Codex：

```bash
npx skills add changjiong/jong-coolify-deploy \
  --skill jong-coolify-deploy \
  --agent codex \
  -g -y --copy
```

不要省略 `--agent codex`，否则安装器可能把技能复制到所有检测到的 Agent。

也可以从源码目录手动复制：

```bash
cp -R /path/to/jong-coolify-deploy "$CODEX_HOME/skills/jong-coolify-deploy"
```

安装后重新启动 Agent 会话，让根目录 `SKILL.md` 被重新发现。

## Codex 一句话部署

进入任意本地项目后，只需要说明目标域名：

```text
使用 jong-coolify-deploy，把当前项目部署到 Coolify，域名使用 app.example.com。
```

技能会从当前目录识别仓库和构建方式，复用当前 GitHub CLI 登录、Coolify API 配置和已有 DNS 通配能力，再完成源码发布、Coolify 资源创建、部署与 HTTPS 验收。

## 自然语言用法

你可以直接这样说：

```text
把当前项目部署到我的 Coolify，域名使用 risk.example.com。
```

```text
这个多容器项目用 Coolify Service 部署，环境变量要能在前端编辑，数据需要持久化。
```

```text
本地还没有 remote，创建私有 GitHub 仓库并部署到自有 VPS，完成后验证 HTTPS。
```

## 工作方式

1. 只读检查本地仓库、Git 状态、构建入口和潜在 secret 文件。
2. 检查 Coolify API、服务器、项目、环境、域名和已有资源。
3. 运行项目已有的 test/lint/typecheck/build 门禁。
4. 只补最小生产配置，保留无关工作区修改。
5. 发布必要源码，创建或精确匹配 Coolify 资源。
6. 配置环境变量、持久化、健康检查、Traefik 和域名。
7. 等待部署终态，检查日志、DNS、TLS、健康路径和应用路由。
8. 输出部署证据和回滚边界。

## 内置脚本

检查本地项目，不读取 secret 内容：

```bash
python3 scripts/inspect_project.py /path/to/project --pretty
```

检查自有 Coolify API：

```bash
python3 scripts/coolify_api.py health
python3 scripts/coolify_api.py list-servers
python3 scripts/coolify_api.py list-projects
```

从私有 GitHub 仓库创建 Application：

```bash
python3 scripts/coolify_api.py create-github \
  --project-uuid PROJECT_UUID \
  --server-uuid SERVER_UUID \
  --github-app-uuid GITHUB_APP_UUID \
  --name app-name \
  --repository https://github.com/OWNER/REPO \
  --branch main \
  --build-pack dockerfile \
  --dockerfile-location /Dockerfile \
  --port 80 \
  --domain https://app.example.com
```

环境变量通过本地 JSON 文件批量写入，值不会进入命令行：

```bash
python3 scripts/coolify_api.py apply-env-file APP_UUID --file /secure/path/env.json
```

通过 `/tmp` 创建、部署、验证并清理最小应用：

```bash
python3 scripts/smoke_deploy.py \
  --project-uuid PROJECT_UUID \
  --server-uuid SERVER_UUID \
  --domain https://smoke.example.com
```

验证公网 URL：

```bash
python3 scripts/verify_deployment.py \
  --url https://risk.example.com \
  --health-path /healthz \
  --expect-health-body ok \
  --path / \
  --path /dashboard \
  --check-http-redirect
```

## 输出

- 公网 URL、Coolify 最终状态和部署状态
- GitHub 仓库、分支和部署 commit
- Coolify 项目、环境、资源名称与短 UUID
- 修改过的环境变量键名，值始终遮蔽
- 持久化和备份影响
- DNS/TLS、健康检查、日志、路由和内部网络证据
- 回滚边界、风险和 `missing evidence`

## 风险边界

- 不自动删除应用、服务、数据库、卷、DNS 记录或 Git 历史。
- 不把 Token、密码、私钥、DSN 写入仓库或报告。
- 不因名称相似复用现有资源，必须匹配 repo、域名和环境。
- 修改生产环境已有变量、替换冲突 DNS、覆盖 Compose 或删除资源前必须明确确认。
- 新资源部署失败时默认保留现场用于诊断，不自动删除数据。

## 验证

```bash
python3 /path/to/qiaomu-meta-skill/scripts/validate_skill.py .
python3 /path/to/qiaomu-meta-skill/scripts/trigger_eval.py . \
  --cases evals/trigger_cases.json \
  --output reports/trigger-eval.json
python3 -m unittest discover -s tests -v
python3 /path/to/qiaomu-meta-skill/scripts/release_check.py . \
  --phase local --run-tests
```

当前证据覆盖本地包验证、触发评测、脚本测试，以及 Coolify REST Dockerfile 路径的 provider 冒烟。私有 GitHub App、Docker Compose Service、人工盲评和生产采用量仍为 `missing evidence`。

## Troubleshooting

- Coolify API 返回 `401`：检查 Token 是否属于目标团队，以及环境变量是否为 `COOLIFY_API_TOKEN` 或 `COOLIFY_ACCESS_TOKEN`。
- Codex 未读取到凭证：检查 `~/.codex/config.toml` 的 `mcp_servers.coolify.env` 节点和文件权限。
- Coolify API 无法连接：核对 `COOLIFY_BASE_URL` 只包含实例 origin；脚本会自动追加 `/api/v1`。
- Coolify MCP 不可用：直接使用健康的 Coolify REST API；MCP 不是部署前置条件。
- `gh auth status` 失败：先完成 GitHub CLI 登录，不要把 Token 写进仓库或聊天记录。
- 域名未生效：保留已部署资源，报告应配置的 DNS 记录，等待解析后只重跑公网验证。
- 部署状态失败：保留容器和日志现场，先定位构建、环境变量、健康检查或内部网络问题，不自动删除卷。
- 本地测试提示无法绑定回环端口：这是受限沙箱问题，在允许本地 socket 的环境中重跑单元测试。

## 参考与取舍

设计研究了 `qiaomu-website-develop`、Coolify 官方 API、本机 `coolify-deploy`、`StuMason/coolify-mcp`、`joshuadavidthomas/agent-skills` 的 `coolify-compose`，并审阅了 `Coolify-Manager`。保留端到端交付、资源判定、Compose/Coolify 变量和证据门禁；Coolify REST API 是默认通道，MCP 仅作可选适配，不复制 WordPress 专项、CLI 安装器或破坏性 DNS 替换。

上游参考：

- https://github.com/joeseesun/qiaomu-website-develop
- `local:coolify-deploy`
- https://coolify.io/docs/api-reference/api
- https://github.com/StuMason/coolify-mcp
- https://github.com/joshuadavidthomas/agent-skills/tree/main/coolify-compose

机器可读上游声明：`['https://github.com/joeseesun/qiaomu-website-develop', 'local:coolify-deploy', 'https://coolify.io/docs/api-reference/api', 'https://github.com/StuMason/coolify-mcp', 'https://github.com/joshuadavidthomas/agent-skills/tree/main/coolify-compose']`

## License

MIT
