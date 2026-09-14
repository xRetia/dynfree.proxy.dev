#!/usr/bin/env python3
"""
dynfree.proxy.dev - 从 proxy.scdn.io 拉取免费 HTTP 代理并生成 Clash/mihomo 配置。

输出:
  proxies.yaml  代理节点列表（proxy-providers content 格式，CI 每 6 小时自动刷新）
  config.yaml   Clash Verge 主配置（静态文件，仅初始或改模板时手动生成）

用法:
  python generate.py            # 拉取代理，刷新 proxies.yaml（CI 使用）
  python generate.py --config   # 同时重新生成 config.yaml（改模板后手动执行）

环境变量:
  PROVIDER_URL  覆盖 config.yaml 中 proxy-providers 的默认 URL
"""

import json
import os
import sys
import time
import urllib.request

API_URL = "https://proxy.scdn.io/api/get_proxy.php"
TOTAL_COUNT = 30    # 每次拉取的代理总数
PER_REQUEST = 15    # API 单次上限 20，分两批
MAX_RETRY = 3       # 单批拉取重试次数
REPO = "xRetia/dynfree.proxy.dev"
DEFAULT_PROVIDER_URL = f"https://raw.githubusercontent.com/{REPO}/main/proxies.yaml"

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", ".")
PROXIES_FILE = os.path.join(OUTPUT_DIR, "proxies.yaml")
CONFIG_FILE = os.path.join(OUTPUT_DIR, "config.yaml")


def fetch_proxies(count):
    """从 API 拉取一批代理（不带 country_code，显式传 all 会返回空）"""
    url = f"{API_URL}?protocol=http&count={count}"
    print(f"[fetch] {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "proxy2clash/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    if data.get("code") != 200:
        raise RuntimeError(f"API error: {data}")
    proxies = data["data"]["proxies"]
    print(f"[fetch] got {len(proxies)} proxies")
    return proxies


def fetch_with_retry(count):
    """带重试的拉取，全部失败返回空列表"""
    for attempt in range(1, MAX_RETRY + 1):
        try:
            result = fetch_proxies(count)
            if result:
                return result
            print(f"[warn] empty result (attempt {attempt}/{MAX_RETRY})")
        except Exception as e:
            print(f"[warn] fetch error (attempt {attempt}/{MAX_RETRY}): {e}")
        if attempt < MAX_RETRY:
            time.sleep(3)
    return []


def parse_proxy(addr):
    """将 ip:port 解析为 (server, port)"""
    parts = addr.rsplit(":", 1)
    return parts[0], int(parts[1])


def build_proxies_yaml(nodes):
    """生成 proxy-providers content 格式的 YAML"""
    lines = ["proxies:"]
    for server, port in nodes:
        lines.append(f'  - name: "{server}:{port}"')
        lines.append("    type: http")
        lines.append(f"    server: {server}")
        lines.append(f"    port: {port}")
    return "\n".join(lines) + "\n"


def build_config_yaml(provider_url):
    """生成 Clash Verge 主配置（静态模板）"""
    return f"""\
# Clash Verge 配置 - dynfree.proxy.dev
# 代理来源: proxy.scdn.io (GitHub Actions 每 6 小时更新)
# 健康检查目标: https://www.gstatic.com/generate_204

mixed-port: 7890
allow-lan: false
mode: rule
log-level: info
unified-delay: true
external-controller: 127.0.0.1:9090

# 域名嗅探
sniffer:
  enable: true
  force-dns-mapping: true
  parse-pure-ip: true
  override-destination: false
  sniff:
    HTTP:
      ports: [80, 8080-8880]
      override-destination: true
    TLS:
      ports: [443, 8443]
    QUIC:
      ports: [443, 8443]

# DNS: 系统_dns + 国内公共 UDP，公司内网环境下最稳
dns:
  enable: true
  listen: 0.0.0.0:1053
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  nameserver:
    - system
    - 223.5.5.5
    - 119.29.29.29

# 代理集合 - 从 GitHub raw 拉取，每 6 小时自动刷新
# proxy 字段: 通过代理组自身刷新订阅（防火墙环境下也能更新）
proxy-providers:
  proxy-pool:
    type: http
    url: "{provider_url}"
    interval: 21600
    proxy: 代理选择
    health-check:
      enable: true
      url: https://www.gstatic.com/generate_204
      interval: 300
      timeout: 5000
      lazy: true
      expected-status: 204

# 代理组
proxy-groups:
  - name: "代理选择"
    type: url-test
    use:
      - proxy-pool
    url: https://www.gstatic.com/generate_204
    interval: 300
    tolerance: 50
    timeout: 5000
    expected-status: 204

  - name: "手动选择"
    type: select
    use:
      - proxy-pool
    proxies:
      - DIRECT

# 路由规则
rules:
  # 微信网页版走代理
  - DOMAIN-SUFFIX,wx.qq.com,代理选择
  - DOMAIN-SUFFIX,weixin.qq.com,代理选择
  - DOMAIN-SUFFIX,qq.com,代理选择
  # 钉钉相关域名直连（防火墙本身放行）
  - DOMAIN-SUFFIX,dingtalk.com,DIRECT
  # 其余直连
  - MATCH,DIRECT
"""


def main():
    print("=== dynfree.proxy.dev: 刷新代理池 ===")
    regenerate_config = "--config" in sys.argv[1:]

    # 分批拉取
    all_proxies = []
    for i in range(0, TOTAL_COUNT, PER_REQUEST):
        batch = min(PER_REQUEST, TOTAL_COUNT - i)
        print(f"\n[batch {i // PER_REQUEST + 1}] 拉取 {batch} 个代理...")
        all_proxies.extend(fetch_with_retry(batch))
        if i + PER_REQUEST < TOTAL_COUNT:
            time.sleep(1)

    # 去重（保持顺序）
    seen = set()
    nodes = []
    for addr in all_proxies:
        if addr not in seen:
            seen.add(addr)
            nodes.append(parse_proxy(addr))

    print(f"\n总计可用代理 {len(nodes)} 个")
    if not nodes:
        print("ERROR: 未拉取到任何代理", file=sys.stderr)
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 刷新 proxies.yaml
    with open(PROXIES_FILE, "w", encoding="utf-8") as f:
        f.write(build_proxies_yaml(nodes))
    print(f"[output] {PROXIES_FILE}")

    # 按需重新生成 config.yaml（静态文件，CI 不覆盖）
    if regenerate_config:
        provider_url = os.environ.get("PROVIDER_URL", DEFAULT_PROVIDER_URL)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(build_config_yaml(provider_url))
        print(f"[output] {CONFIG_FILE} (provider: {provider_url})")

    print("=== 完成 ===")


if __name__ == "__main__":
    main()
