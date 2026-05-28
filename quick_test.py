#!/usr/bin/env python3
"""快速测试 Kronos Mock 模式"""
import sys

print(">" * 60)
print("Kronos Mock Mode Test")
print(">" * 60)

try:
    from kronos_predictor import predict_kronos, KRONOS_AVAILABLE
    
    print(f"\nKRONOS_AVAILABLE: {KRONOS_AVAILABLE}")
    
    # Mock 模式测试
    print("\n[测试] Mock 模式预测...")
    result = predict_kronos('600000', 10.7, None)
    
    print(f"\n预测结果:")
    print(f"  股票代码: 600000")
    print(f"  当前价格: 10.7")
    print(f"  Kronos 动作: {result['action']}")
    print(f"  置信度: {result['confidence']:.2f}")
    print(f"  预测价格: {result['predicted_price']}")
    print(f"  理由: {result['reason']}")
    
    # 验证加分逻辑
    print("\n[验证] 加分逻辑...")
    action = result['action']
    conf = result['confidence']
    
    if action == "BUY":
        kronos_bonus = int(conf * 20)
    elif action == "SELL":
        kronos_bonus = -int(conf * 15)
    else:  # HOLD
        kronos_bonus = 0
    
    print(f"  动作: {action}")
    print(f"  置信度: {conf:.2f}")
    print(f"  kronos_bonus: {kronos_bonus}")
    
    final_score = 3.5 + kronos_bonus  # 假设 tech_score = 3.5
    print(f"  final_score (tech 3.5 + bonus): {final_score:.2f}")
    
    print("\n[Result] PASS")
    with open('test_result.txt', 'w', encoding='utf-8') as f:
        f.write('PASS')
    sys.exit(0)
    
except Exception as e:
    print(f"\n[Error] FAIL: {e}")
    with open('test_result.txt', 'w', encoding='utf-8') as f:
        f.write(f'FAIL: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
