#!/usr/bin/env python
r"""Tavily 网页搜索脚本 —— 任意目录可用，不依赖项目 .env。

用法:
  python search.py "关键词"
  python search.py "关键词" --max 5

配置方式（任选其一）:
  1. 环境变量: set TAVILY_API_KEY=xxx     (一次性)
  2. 环境变量: 写入系统环境变量            (永久)
  3. 密钥文件: echo xxx > %USERPROFILE%\.tavily_key  (推荐)
"""

import json
import os
import sys

# Windows Git Bash / cmd 终端默认 GBK，强制 UTF-8 避免中文乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _load_api_key():
    """从环境变量或 ~/.tavily_key 读取 API key。"""
    key = os.getenv("TAVILY_API_KEY")
    if key:
        return key

    key_file = os.path.join(os.path.expanduser("~"), ".tavily_key")
    try:
        with open(key_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        pass

    return None


API_KEY = _load_api_key()


def search(query, max_results=3):
    import urllib.request

    data = json.dumps({"api_key": API_KEY, "query": query, "max_results": max_results}).encode()
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def main():
    if not API_KEY:
        print("[ERROR] 未找到 TAVILY_API_KEY")
        print("配置方法:")
        print("  1. set TAVILY_API_KEY=xxx")
        print("  2. 或 echo xxx > %USERPROFILE%\\.tavily_key")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("用法: python search.py <关键词> [--max N]")
        sys.exit(1)

    query = sys.argv[1]
    max_results = 3

    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--max" and i + 1 < len(sys.argv):
            max_results = int(sys.argv[i + 1])
            i += 2
        else:
            i += 1

    try:
        data = search(query, max_results)
    except Exception as e:
        print(f"[ERROR] 搜索失败: {e}")
        sys.exit(1)

    print(f"\n>>> {data['query']}  ({data.get('response_time', 0):.1f}s)\n")
    for i, r in enumerate(data["results"], 1):
        print(f"{i}. {r['title']}")
        print(f"   {r['url']}")
        print(f"   {r['content'][:200]}...")
        print()


if __name__ == "__main__":
    main()
