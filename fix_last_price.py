"""一次性修复：为持仓添加 last_price"""
import requests
import json
import re
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 读取持仓
with open(os.path.join(BASE_DIR, "portfolio.json"), "r", encoding="utf-8") as f:
    p = json.load(f)

codes = list(p.get("positions", {}).keys())
if not codes:
    print("无持仓")
    exit()

print("持仓代码: " + str(codes))

# 构建新浪请求
sina_codes = []
for c in codes:
    prefix = "sh" if c.startswith(("6", "9")) else "sz"
    sina_codes.append(prefix + c)

url = "https://hq.sinajs.cn/list=" + ",".join(sina_codes)
r = requests.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=10)

# 解析
result = {}
for line in r.text.strip().split("\n"):
    if "=" not in line:
        continue
    eq_pos = line.find("=")
    var_part = line[:eq_pos]
    data_part = line[eq_pos + 1:].strip('"')

    m = re.search(r"hq_str_(sh|sz)(\d+)", var_part)
    if not m:
        continue
    code = m.group(2)
    fields = data_part.split(",")
    if len(fields) < 4:
        continue
    result[code] = float(fields[3])

print("获取到 " + str(len(result)) + " 个价格")

# 更新 last_price
updated = 0
for code, pos in p.get("positions", {}).items():
    if code in result:
        pos["last_price"] = result[code]
        updated += 1
        print("  " + code + " " + pos["name"] + ": " + str(result[code]))

# 保存
with open(os.path.join(BASE_DIR, "portfolio.json"), "w", encoding="utf-8") as f:
    json.dump(p, f, ensure_ascii=False, indent=2)

print("\n已更新 " + str(updated) + " 只股票的 last_price")
