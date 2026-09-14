---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'dd32d34d-02a4-4b33-8ba2-695eb5899023'
  PropagateID: 'dd32d34d-02a4-4b33-8ba2-695eb5899023'
  ReservedCode1: 'c6e5693b-7201-4257-bbe2-617ef0ec4ef3'
  ReservedCode2: 'c6e5693b-7201-4257-bbe2-617ef0ec4ef3'
---

# dynfree.proxy.dev

Auto-refreshing free HTTP proxy pool for Clash Verge / mihomo, with domain-fronting `Host` header to survive restrictive corporate firewalls.

- **Proxy source**: [proxy.scdn.io](https://proxy.scdn.io/api_docs.php) free API
- **Refresh**: 30 proxies every 6 hours via GitHub Actions
- **Health check**: `https://wx.qq.com/` — only proxies that can actually reach the web WeChat client are selected
- **Firewall bypass**: every proxy sends `Host: tls-desktop.dingtalk.com` in its `CONNECT` request (domain fronting), for networks where only DingTalk domains are allowed
- **Client**: [Clash Verge](https://github.com/clash-verge-rev/clash-verge-rev) (any mihomo-core client works)

## Quick Start (Clash Verge)

1. In Clash Verge: **Profiles → New → Remote**, paste:

   ```
   https://raw.githubusercontent.com/xRetia/dynfree.proxy.dev/main/config.yaml
   ```

2. Import and activate the profile. Done.

- The `proxy-pool` provider auto-refreshes every 6 hours (same cadence as the GitHub Actions cron).
- The "代理选择" group is `url-test`: it automatically picks the fastest proxy that passes the `wx.qq.com` health check.
- The provider refreshes **through the proxy group itself**, so subscription updates also work behind the corporate firewall. On first import, make sure `raw.githubusercontent.com` is reachable once (use any available network) so the initial provider file can download.

## How it works

```
proxy.scdn.io API ──(GitHub Actions, every 6h)──> proxies.yaml ──> raw.githubusercontent.com
                                                                          │
Clash Verge ── config.yaml (import once) ── proxy-providers ─────────────┘
```

Every proxy node is generated as:

```yaml
- name: "1.2.3.4:8080"
  type: http
  server: 1.2.3.4
  port: 8080
  headers:
    Host: tls-desktop.dingtalk.com   # domain fronting
```

mihomo's HTTP outbound `headers` field overrides the headers of the `CONNECT` request sent **to the proxy server**, so the firewall sees a DingTalk Host and lets it through, while the tunnel actually carries your traffic.

## Files

| File | Description |
|---|---|
| `config.yaml` | Clash Verge profile (static, import once) |
| `proxies.yaml` | Proxy node list (auto-refreshed by CI) |
| `generate.py` | Generator script |
| `.github/workflows/update-proxy.yml` | Refresh workflow |

## Regenerate config manually

```bash
python generate.py           # refresh proxies.yaml only
python generate.py --config  # also regenerate config.yaml (uses DEFAULT_PROVIDER_URL)
PROVIDER_URL=https://... python generate.py --config  # custom provider URL
```

## Notes

- Free public proxies are unstable. 30 candidates are pulled per refresh and the `url-test` group keeps switching to whatever currently works. Expect a handful of usable nodes at any time.
- `expected-status: 200` + health-check URL `https://wx.qq.com/` filters out proxies that connect but can't actually browse.
- Private repos' raw URLs need a token; this repo is public so no token is required.

---

## 中文说明

免费 HTTP 代理池，自动刷新，适配 Clash Verge / mihomo，通过 domain fronting 绕过只放行钉钉域名的公司防火墙。

- **代理来源**：[proxy.scdn.io](https://proxy.scdn.io/api_docs.php) 免费 API
- **刷新频率**：GitHub Actions 每 6 小时拉取 30 个代理
- **健康检查**：`https://wx.qq.com/`，只有真正能打开微信网页版的代理会被选用
- **绕过防火墙**：每个代理的 `CONNECT` 请求携带 `Host: tls-desktop.dingtalk.com`（域名前置），公司防火墙只放行钉钉域名时可穿透
- **客户端**：Clash Verge（任何 mihomo 内核客户端均可）

### 使用方法（Clash Verge）

1. Clash Verge 中 **订阅 → 新建 → 远程**，填入：

   ```
   https://raw.githubusercontent.com/xRetia/dynfree.proxy.dev/main/config.yaml
   ```

2. 导入并启用即可。

- `proxy-pool` 每 6 小时自动刷新（与 GitHub Actions 定时任务同步）。
- "代理选择" 策略组为 `url-test` 类型，自动切换到通过微信健康检查的最快节点。
- 订阅刷新走代理组自身隧道，防火墙环境下同样可以更新；仅首次导入时需要在能访问 GitHub 的网络下完成一次。

### 原理

mihomo HTTP 出站的 `headers` 字段会覆盖发往代理服务器的 `CONNECT` 请求头，因此防火墙看到的 Host 是钉钉域名，放行建立隧道，隧道内承载实际流量。

### 手动重新生成

```bash
python generate.py           # 仅刷新 proxies.yaml
python generate.py --config  # 同时重新生成 config.yaml
```

### 注意事项

- 免费公共代理不稳定，每次刷新 30 个候选，`url-test` 组会持续切换到当前可用的节点。
- 免费代理池偶有返回空列表的时段（上游池子暂时枯竭），脚本内置重试，下一轮定时任务会自动恢复。

## License

MIT

> AI生成