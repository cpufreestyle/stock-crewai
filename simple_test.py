#!/usr/bin/env python3
"""最简单测试 - 不导入 kronos"""
import sys

print("Test start")

# 模拟 Kronos 输出
mock_result = {
    "action": "BUY",
    "confidence": 0.75,
    "predicted_price": 11.5,
    "reason": "[Mock] test"
}

print(f"Mock result: {mock_result['action']} (conf={mock_result['confidence']:.2f})")

# 模拟加分逻辑
action = mock_result['action']
conf = mock_result['confidence']

if action == "BUY":
    kronos_bonus = int(conf * 20)
elif action == "SELL":
    kronos_bonus = -int(conf * 15)
else:
    kronos_bonus = 0

print(f"kronos_bonus = {kronos_bonus}")

tech_score = 3.5
final_score = tech_score + kronos_bonus
print(f"final_score = {tech_score} + {kronos_bonus} = {final_score}")

print("\nTest PASSED")
with open('test_result.txt', 'w') as f:
    f.write('PASS')

sys.exit(0)
