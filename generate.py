#!/usr/bin/env python3
"""
dynfree.proxy.dev - 从 proxy.scdn.io 拉取免费代理并生成 Clash/mihomo 配置。

混合拉取 socks5 和 http 两种协议的代理，socks5 原生支持 CONNECT 隧道，
http 代理用 HTTP 明文健康检查（不依赖 CONNECT 方法）。

输出:
  proxies.yaml  代理节点列表（proxy-providers content 格式，CI 定时刷新）
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
MAX_RETRY = 3
REPO = "xRetia/dynfree.proxy.dev"
DEFAULT_PROVIDER_URL = f"https://raw.githubusercontent.com/{REPO}/main/proxies.yaml"

# 混合协议配置：socks5 支持 CONNECT 隧道（能代理 HTTPS），http 只做明文转发
# socks5 成功率高但数量少，http 数量多但多数不支持 CONNECT
SOCKS5_COUNT = 15
HTTP_COUNT = 15
PER_REQUEST = 15  # API 单次上限 20

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", ".")
PROXIES_FILE = os.path.join(OUTPUT_DIR, "proxies.yaml")
CONFIG_FILE = os.path.join(OUTPUT_DIR, "config.yaml")


def fetch_proxies(protocol, count):
    """从 API 拉取一批代理（不带 country_code，显式传 all 会返回空）"""
    url = f"{API_URL}?protocol={protocol}&count={count}"
    print(f"[fetch] {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "proxy2clash/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    if data.get("code") != 200:
        raise RuntimeError(f"API error: {data}")
    proxies = data["data"]["proxies"]
    print(f"[fetch] got {len(proxies)} {protocol} proxies")
    return proxies


def fetch_with_retry(protocol, count):
    """带重试的拉取，全部失败返回空列表"""
    for attempt in range(1, MAX_RETRY + 1):
        try:
            result = fetch_proxies(protocol, count)
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


def build_proxies_yaml(socks5_nodes, http_nodes):
    """生成 proxy-providers content 格式的 YAML"""
    lines = ["proxies:"]
    # socks5 节点：支持 CONNECT 隧道，可代理 HTTPS
    for server, port in socks5_nodes:
        lines.append(f'  - name: "socks5-{server}:{port}"')
        lines.append("    type: socks5")
        lines.append(f"    server: {server}")
        lines.append(f"    port: {port}")
        lines.append("    udp: true")
    # http 节点：仅明文 HTTP 转发，不支持 CONNECT
    for server, port in http_nodes:
        lines.append(f'  - name: "http-{server}:{port}"')
        lines.append("    type: http")
        lines.append(f"    server: {server}")
        lines.append(f"    port: {port}")
    return "\n".join(lines) + "\n"


def build_config_yaml(provider_url):
    """生成 Clash Verge 主配置（静态模板）"""
    return f"""\
# Clash Verge 配置 - dynfree.proxy.dev
# 代理来源: proxy.scdn.io (GitHub Actions 每天 08:00/14:00/20:00 更新)
# 混合 socks5 + http 代理，健康检查用 HTTP（兼容不支持 CONNECT 的 HTTP 代理）

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

# DNS
dns:
  enable: true
  listen: 0.0.0.0:1053
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  nameserver:
    - system
    - 223.5.5.5
    - 119.29.29.29

# 代理集合 - 从 GitHub raw 拉取
proxy-providers:
  proxy-pool:
    type: http
    url: "{provider_url}"
    interval: 21600
    health-check:
      enable: true
      url: http://www.gstatic.com/generate_204
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
    url: http://www.gstatic.com/generate_204
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
  - MATCH,代理选择
"""


def main():
    print("=== dynfree.proxy.dev: 刷新代理池 ===")
    regenerate_config = "--config" in sys.argv[1:]

    # 拉取 socks5 代理
    print(f"\n--- socks5 ({SOCKS5_COUNT} 个) ---")
    socks5_raw = []
    for i in range(0, SOCKS5_COUNT, PER_REQUEST):
        batch = min(PER_REQUEST, SOCKS5_COUNT - i)
        socks5_raw.extend(fetch_with_retry("socks5", batch))
        if i + PER_REQUEST < SOCKS5_COUNT:
            time.sleep(1)

    # 拉取 http 代理
    print(f"\n--- http ({HTTP_COUNT} 个) ---")
    http_raw = []
    for i in range(0, HTTP_COUNT, PER_REQUEST):
        batch = min(PER_REQUEST, HTTP_COUNT - i)
        http_raw.extend(fetch_with_retry("http", batch))
        if i + PER_REQUEST < HTTP_COUNT:
            time.sleep(1)

    # 去重
    def dedup(raw_list):
        seen = set()
        nodes = []
        for addr in raw_list:
            if addr not in seen:
                seen.add(addr)
                nodes.append(parse_proxy(addr))
        return nodes

    socks5_nodes = dedup(socks5_raw)
    http_nodes = dedup(http_raw)

    total = len(socks5_nodes) + len(http_nodes)
    print(f"\nsocks5: {len(socks5_nodes)} 个, http: {len(http_nodes)} 个, 共 {total} 个")
    if total == 0:
        print("ERROR: 未拉取到任何代理", file=sys.stderr)
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 刷新 proxies.yaml
    with open(PROXIES_FILE, "w", encoding="utf-8") as f:
        f.write(build_proxies_yaml(socks5_nodes, http_nodes))
    print(f"[output] {PROXIES_FILE}")

    # 按需重新生成 config.yaml
    if regenerate_config:
        provider_url = os.environ.get("PROVIDER_URL", DEFAULT_PROVIDER_URL)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(build_config_yaml(provider_url))
        print(f"[output] {CONFIG_FILE}")

    print("=== 完成 ===")


if __name__ == "__main__":
    main()
