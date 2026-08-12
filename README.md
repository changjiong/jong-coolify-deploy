# jong-coolify-deploy

把一句“部署当前项目到我的 Coolify，以后提交 GitHub 自动更新”变成完整交付：本地质量检查、必要的 Docker/Compose 改造、私有 GitHub 源码、Coolify 资源、GitHub push 自动部署、域名、健康检查、部署日志和 HTTPS 验收。

```text
本地仓库 -> GitHub push -> Coolify GitHub App webhook -> 自有 VPS -> commit/TLS 验收
```

## 适用场景

- 把当前或指定本地仓库部署到自有 Coolify VPS。
- 本地没有 remote，需要创建私有 GitHub 仓库再部署。
- 代码推送到指定 GitHub 分支后，让 Coolify 自动拉取新 commit 并重新部署。
- 验证某次 push 是否真的产生了 commit 匹配的 webhook deployment。
- 在 Application 与 Docker Compose Service 之间做正确选择。
- 要求环境变量在 Coolify UI 可编辑，并明确数据卷、健康检查和域名。
- 要求部署完成后检查状态、日志、DNS、TLS、深层路由和内部网络。

不适用于 Vercel/Cloudflare Pages、裸 VPS SSH 初始化、纯 DNS 教学、仅重启/看日志、仅转换 Compose 而不部署。

这里的“自动更新”不是 Coolify 定时重新发现仓库，而是 GitHub `push`
webhook 触发 Coolify 拉取该提交、构建并替换运行版本。

## 前置条件

- [ ] Coolify 已安装在目标 VPS，API 可访问。
- [ ] 已创建 Coolify API Token，并通过环境变量或 Codex 配置提供。
- [ ] 本机 `git` 可用；需要发布源码时，`gh auth status` 正常。
- [ ] 自动部署使用 Coolify GitHub App；该 App 已安装并获准访问目标仓库。
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
使用 jong-coolify-deploy，把当前项目部署到 Coolify，域名使用 app.example.com；以后 push main 后自动部署，并用 commit SHA 验证一次。
```

技能会从当前目录识别仓库和构建方式，复用当前 GitHub CLI 登录、Coolify API 配置和已有 DNS 通配能力，再完成源码发布、Coolify 资源创建、原生 GitHub App webhook 配置、部署与 HTTPS 验收。

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

```text
把现有 Coolify Application 的 main 分支设为 push 后自动部署；我推送下一次代码变更后，确认线上部署的就是那个 commit。
```

## 工作方式

1. 只读检查本地仓库、Git 状态、构建入口和潜在 secret 文件。
2. 检查 Coolify API、服务器、项目、环境、域名和已有资源。
3. 运行项目已有的 test/lint/typecheck/build 门禁。
4. 只补最小生产配置，保留无关工作区修改。
5. 发布必要源码，创建或精确匹配 Coolify 资源。
6. 配置环境变量、持久化、健康检查、Traefik 和域名。
7. 检查 `.github/workflows` 是否已有 Coolify deploy 触发器；不保留双触发路径。
8. GitHub-backed Application 默认开启原生 push 自动部署，并记录 deployment 历史基线。
9. 新业务提交 push 后，只接受基线之后、commit 精确匹配且 `is_webhook=true` 的成功 deployment。
10. 检查日志、DNS、TLS、健康路径和应用路由，输出部署证据与回滚边界。

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

`create-github` 默认开启后续 push 自动部署；`--instant-deploy` 只控制创建后的首次部署，两者不是同一个开关。只有明确需要手动发布时才传 `--no-auto-deploy`。

为现有 GitHub-backed Application 配置自动部署并记录验收基线：

```bash
python3 scripts/coolify_api.py configure-auto-deploy APP_UUID \
  --repository https://github.com/OWNER/REPO \
  --branch main
```

把命令返回的 `verification_baseline_id` 留在当前执行上下文。推送下一次真实业务提交后，使用完整 SHA 验证：

```bash
git push origin main

python3 scripts/coolify_api.py verify-auto-deploy APP_UUID \
  --repository https://github.com/OWNER/REPO \
  --branch main \
  --commit FULL_REMOTE_SHA \
  --after-id VERIFICATION_BASELINE_ID
```

验证命令不会调用手动 `/deploy` 接口。旧记录、手动部署、API 部署或 commit 不匹配都不能通过。没有新的真实提交时，只能报告“已配置，真实 push 验证为 `missing evidence`”；技能不会擅自创建空提交。

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
- 自动部署开关、GitHub App 来源、验收基线、webhook deployment UUID、`is_webhook` 和 commit 精确匹配结果
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
- 原生 GitHub App 自动部署启用后，不再添加 GitHub Actions `/deploy` 触发器，避免一次 push 重复部署。
- 不用手动部署冒充自动部署证据，不用基线之前的旧记录冒充本次验证。

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

当前证据覆盖本地包验证、触发评测、自动部署 API/匹配逻辑单测，以及 Coolify REST Dockerfile 路径的 provider 冒烟。真实 GitHub push -> Coolify webhook -> commit 匹配部署、Docker Compose Service、人工盲评和生产采用量仍为 `missing evidence`。

## Troubleshooting

- Coolify API 返回 `401`：检查 Token 是否属于目标团队，以及环境变量是否为 `COOLIFY_API_TOKEN` 或 `COOLIFY_ACCESS_TOKEN`。
- Codex 未读取到凭证：检查 `~/.codex/config.toml` 的 `mcp_servers.coolify.env` 节点和文件权限。
- Coolify API 无法连接：核对 `COOLIFY_BASE_URL` 只包含实例 origin；脚本会自动追加 `/api/v1`。
- Coolify MCP 不可用：直接使用健康的 Coolify REST API；MCP 不是部署前置条件。
- `gh auth status` 失败：先完成 GitHub CLI 登录，不要把 Token 写进仓库或聊天记录。
- 域名未生效：保留已部署资源，报告应配置的 DNS 记录，等待解析后只重跑公网验证。
- 部署状态失败：保留容器和日志现场，先定位构建、环境变量、健康检查或内部网络问题，不自动删除卷。
- `configure-auto-deploy` 提示没有 GitHub App：先在 Coolify 连接并安装 GitHub App 到目标仓库；技能不降级为第二套 token-bearing GitHub Actions。
- 自动部署超时：核对 App 仓库权限、目标分支、GitHub webhook delivery、Coolify `watch_paths`，以及提交消息是否含 `[skip ci]` 或 `[skip cd]`。
- 找到同 commit 但 `is_webhook=false`：这是手动/API 部署，不是自动部署证据。
- 本地测试提示无法绑定回环端口：这是受限沙箱问题，在允许本地 socket 的环境中重跑单元测试。

## 参考与取舍

设计研究了 `qiaomu-website-develop`、Coolify 官方 API/CLI、TerminalSkills `coolify`、`jonmumm/deploy-verify`，并审阅了 Hookdeck `github-webhooks`。保留端到端交付、部署历史和“预期版本必须对账”的机制；采用 Coolify 原生 GitHub App webhook，不自建 webhook handler，也不叠加 GitHub Actions `/deploy` 触发器。

上游参考：

- https://github.com/joeseesun/qiaomu-website-develop
- `local:coolify-deploy`
- https://coolify.io/docs/api-reference/api
- https://github.com/StuMason/coolify-mcp
- https://github.com/joshuadavidthomas/agent-skills/tree/main/coolify-compose
- https://github.com/TerminalSkills/skills/tree/main/skills/coolify
- https://github.com/jonmumm/skills/tree/main/deploy-verify

机器可读上游声明：`['https://github.com/joeseesun/qiaomu-website-develop', 'local:coolify-deploy', 'https://coolify.io/docs/api-reference/api', 'https://github.com/StuMason/coolify-mcp', 'https://github.com/joshuadavidthomas/agent-skills/tree/main/coolify-compose', 'https://github.com/TerminalSkills/skills/tree/main/skills/coolify', 'https://github.com/jonmumm/skills/tree/main/deploy-verify']`

<!-- qiaomu-profile:start -->
## 关于向阳乔木

向阳乔木（乔向阳 / Joe）是一位实践型 AI 产品与内容创作者，长期把前沿 AI 变化转译成可复用的工作流、产品判断、AI 编程实践、AI 搜索实践和 GEO/AI 营销方法。

- 个人网站: https://qiaomu.ai
- 博客: https://blog.qiaomu.ai
- X: https://x.com/vista8
- GitHub: https://github.com/joeseesun/
- 微信公众号: 向阳乔木推荐看

### 支持与关注

| 打赏支持 | 微信公众号 |
|---|---|
| <img src="assets/qiaomu-profile/qiaomu_reward_qr.png" alt="向阳乔木打赏二维码" width="180" /> | <img src="assets/qiaomu-profile/qiaomu_wechat_public_account_qr.jpg" alt="向阳乔木推荐看公众号二维码" width="180" /> |
| 感谢支持乔木持续分享 AI 实践 | 扫码关注「向阳乔木推荐看」 |

<!-- qiaomu-profile:end -->

## License

MIT
