"""
集成缓存层到 data_fetcher.py
运行此脚本自动修改 data_fetcher.py，添加缓存支持
"""

import os
import re

def integrate_cache():
    """将缓存支持集成到 data_fetcher.py"""
    
    df_path = "data_fetcher.py"
    backup_path = "data_fetcher.py.backup"
    
    # 1. 备份原文件
    print("📦 备份原文件...")
    with open(df_path, 'r', encoding='utf-8') as f:
        original_content = f.read()
    
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(original_content)
    
    print(f"✅ 已备份到 {backup_path}")
    
    # 2. 在文件开头添加导入
    print("\n📝 添加缓存导入...")
    
    import_line = "\nfrom api_cache import (\n    TTLCache,\n    cached,\n    realtime_cache,\n    market_cache,\n    kline_cache,\n    clear_all_caches,\n    get_all_cache_stats\n)\n"
    
    # 在第一个 import 语句后插入
    lines = original_content.split('\n')
    insert_pos = 0
    
    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            insert_pos = i + 1
            break
    
    lines.insert(insert_pos, import_line)
    content = '\n'.join(lines)
    
    print("✅ 已添加导入语句")
    
    # 3. 为关键函数添加缓存装饰器
    print("\n🔧 为函数添加缓存装饰器...")
    
    # 缓存配置：函数名 -> (ttl, cache_instance)
    cache_configs = {
        'get_realtime_quotes': (10, 'realtime_cache'),
        'get_market_regime': (300, 'market_cache'),
        'get_kline_data': (60, 'kline_cache'),
        'get_sina_realtime': (10, 'realtime_cache'),
        'get_simple_market_regime': (300, 'market_cache'),
    }
    
    for func_name, (ttl, cache_inst) in cache_configs.items():
        # 查找函数定义
        pattern = rf'(def {func_name}\()'
        replacement = rf'@cached(ttl={ttl}, cache_instance={cache_inst})\n\1'
        
        new_content = re.sub(pattern, replacement, content)
        
        if new_content != content:
            content = new_content
            print(f"  ✅ {func_name} (TTL={ttl}s, cache={cache_inst})")
        else:
            print(f"  ⚠️  未找到 {func_name}")
    
    # 4. 保存修改后的文件
    print("\n💾 保存修改...")
    with open(df_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ 已更新 {df_path}")
    
    # 5. 生成测试脚本
    print("\n🧪 生成测试脚本...")
    
    test_script = '''"""
测试 API 缓存层
"""

import time
from data_fetcher import get_realtime_quotes, get_market_regime
from api_cache import get_all_cache_stats, clear_all_caches

def test_cache():
    """测试缓存效果"""
    
    print("=" * 60)
    print("测试 1: 实时行情缓存")
    print("=" * 60)
    
    # 第一次调用
    print("\\n第一次调用（应慢）...")
    start = time.time()
    result1 = get_realtime_quotes(['sh600519', 'sz000333'])
    elapsed1 = time.time() - start
    print(f"耗时: {elapsed1:.2f}s")
    print(f"结果数量: {len(result1)}")
    
    # 第二次调用（应使用缓存）
    print("\\n第二次调用（应快）...")
    start = time.time()
    result2 = get_realtime_quotes(['sh600519', 'sz000333'])
    elapsed2 = time.time() - start
    print(f"耗时: {elapsed2:.2f}s")
    
    if elapsed2 < elapsed1:
        print("✅ 缓存生效！第二次调用更快")
    else:
        print("⚠️  缓存可能未生效")
    
    # 查看缓存统计
    print("\\n缓存统计:")
    stats = get_all_cache_stats()
    for cache_name, stat in stats.items():
        print(f"  {cache_name}: {stat}")
    
    print("\\n" + "=" * 60)
    print("测试 2: 市场状态缓存")
    print("=" * 60)
    
    # 第一次调用
    print("\\n第一次调用（应慢）...")
    start = time.time()
    regime1 = get_market_regime()
    elapsed1 = time.time() - start
    print(f"耗时: {elapsed1:.2f}s")
    print(f"市场状态: {regime1}")
    
    # 第二次调用（应使用缓存）
    print("\\n第二次调用（应快）...")
    start = time.time()
    regime2 = get_market_regime()
    elapsed2 = time.time() - start
    print(f"耗时: {elapsed2:.2f}s")
    
    if elapsed2 < elapsed1:
        print("✅ 缓存生效！")
    else:
        print("⚠️  缓存可能未生效")
    
    print("\\n" + "=" * 60)
    print("测试 3: 缓存自动过期")
    print("=" * 60)
    
    print("\\n等待 15 秒（实时行情缓存 TTL=10s）...")
    time.sleep(15)
    
    print("第三次调用（缓存应已过期）...")
    start = time.time()
    result3 = get_realtime_quotes(['sh600519', 'sz000333'])
    elapsed3 = time.time() - start
    print(f"耗时: {elapsed3:.2f}s")
    
    if elapsed3 >= elapsed2:
        print("✅ 缓存已过期，重新获取")
    else:
        print("⚠️  缓存可能未过期")
    
    # 最终统计
    print("\\n" + "=" * 60)
    print("最终缓存统计:")
    print("=" * 60)
    stats = get_all_cache_stats()
    for cache_name, stat in stats.items():
        print(f"\\n{cache_name}:")
        for k, v in stat.items():
            print(f"  {k}: {v}")

if __name__ == '__main__':
    test_cache()
'''
    
    with open('test_cache.py', 'w', encoding='utf-8') as f:
        f.write(test_script)
    
    print("✅ 已生成 test_cache.py")
    
    # 6. 输出使用说明
    print("\n" + "=" * 60)
    print("✅ 集成完成！")
    print("=" * 60)
    print("\n📖 使用说明:")
    print("\n1. 测试缓存效果:")
    print("   python test_cache.py")
    print("\n2. 在 run_virtual_v4.py 中使用（无需修改）:")
    print("   from data_fetcher import get_realtime_quotes")
    print("   data = get_realtime_quotes(codes)  # 自动使用缓存")
    print("\n3. 清理缓存:")
    print("   from api_cache import clear_all_caches")
    print("   clear_all_caches()")
    print("\n4. 查看缓存统计:")
    print("   from api_cache import get_all_cache_stats")
    print("   stats = get_all_cache_stats()")
    print("\n5. 回滚修改:")
    print(f"   copy {backup_path} {df_path}")


if __name__ == '__main__':
    integrate_cache()
