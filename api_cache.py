"""
API 缓存层 - 减少重复请求，提升性能
支持 TTL（Time-To-Live）缓存，自动过期
"""

import time
import functools
from typing import Any, Callable, Dict, Optional
import hashlib
import json

class TTLCache:
    """简单的 TTL 缓存实现"""
    
    def __init__(self, default_ttl: int = 60):
        """
        Args:
            default_ttl: 默认 TTL（秒）
        """
        self.default_ttl = default_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
    
    def _make_key(self, func_name: str, args: tuple, kwargs: dict) -> str:
        """生成缓存 key"""
        # 将参数序列化为字符串
        key_parts = [func_name]
        key_parts.extend(str(arg) for arg in args)
        key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
        key_str = "|".join(key_parts)
        
        # 使用 MD5 生成固定长度的 key
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值，如果过期返回 None"""
        if key not in self._cache:
            return None
        
        entry = self._cache[key]
        if time.time() > entry['expires_at']:
            # 已过期，删除并返回 None
            del self._cache[key]
            return None
        
        return entry['value']
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存值"""
        ttl = ttl if ttl is not None else self.default_ttl
        expires_at = time.time() + ttl
        
        self._cache[key] = {
            'value': value,
            'expires_at': expires_at,
            'created_at': time.time()
        }
    
    def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()
    
    def clear_expired(self) -> int:
        """清理所有过期的缓存，返回清理数量"""
        expired_keys = []
        current_time = time.time()
        
        for key, entry in self._cache.items():
            if current_time > entry['expires_at']:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]
        
        return len(expired_keys)
    
    def stats(self) -> Dict[str, Any]:
        """返回缓存统计信息"""
        current_time = time.time()
        valid_count = 0
        expired_count = 0
        
        for key, entry in self._cache.items():
            if current_time > entry['expires_at']:
                expired_count += 1
            else:
                valid_count += 1
        
        return {
            'total': len(self._cache),
            'valid': valid_count,
            'expired': expired_count,
            'size_bytes': sum(len(json.dumps(v['value'])) for v in self._cache.values())
        }


# 创建全局缓存实例
realtime_cache = TTLCache(default_ttl=10)  # 实时行情缓存 10 秒
market_cache = TTLCache(default_ttl=300)    # 市场状态缓存 5 分钟
kline_cache = TTLCache(default_ttl=60)      # K线数据缓存 1 分钟
api_cache = TTLCache(default_ttl=30)        # 通用 API 缓存 30 秒


def cached(ttl: Optional[int] = None, cache_instance: Optional[TTLCache] = None):
    """
    装饰器：为函数添加缓存支持
    
    Args:
        ttl: TTL（秒），不指定则使用 cache_instance 的默认 TTL
        cache_instance: 缓存实例，不指定则使用全局 api_cache
    """
    def decorator(func: Callable) -> Callable:
        cache = cache_instance if cache_instance is not None else api_cache
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # 生成缓存 key
            key = cache._make_key(func.__name__, args, kwargs)
            
            # 尝试从缓存获取
            cached_value = cache.get(key)
            if cached_value is not None:
                return cached_value
            
            # 缓存未命中，调用原函数
            result = func(*args, **kwargs)
            
            # 存入缓存
            cache.set(key, result, ttl)
            
            return result
        
        # 添加缓存管理方法
        wrapper.cache_clear = lambda: cache.clear()
        wrapper.cache_stats = lambda: cache.stats()
        wrapper.cache_key = lambda *args, **kwargs: cache._make_key(func.__name__, args, kwargs)
        
        return wrapper
    
    return decorator


# 便捷函数：清理所有缓存
def clear_all_caches() -> None:
    """清理所有缓存"""
    realtime_cache.clear()
    market_cache.clear()
    kline_cache.clear()
    api_cache.clear()
    print("✅ 所有缓存已清理")


# 便捷函数：查看所有缓存统计
def get_all_cache_stats() -> Dict[str, Dict[str, Any]]:
    """获取所有缓存的统计信息"""
    return {
        'realtime': realtime_cache.stats(),
        'market': market_cache.stats(),
        'kline': kline_cache.stats(),
        'api': api_cache.stats()
    }


if __name__ == '__main__':
    # 测试代码
    import random
    
    @cached(ttl=5, cache_instance=api_cache)
    def mock_api_call(param: str) -> Dict[str, Any]:
        """模拟 API 调用"""
        time.sleep(1)  # 模拟网络延迟
        return {'param': param, 'value': random.random(), 'time': time.time()}
    
    print("第一次调用（应该慢）...")
    result1 = mock_api_call("test")
    print(f"结果: {result1}")
    
    print("\n第二次调用（应该快，命中缓存）...")
    result2 = mock_api_call("test")
    print(f"结果: {result2}")
    
    print(f"\n缓存是否命中: {result1['value'] == result2['value']}")
    print(f"缓存统计: {mock_api_call.cache_stats()}")
    
    print("\n清理缓存...")
    mock_api_call.cache_clear()
    
    print("第三次调用（应该慢，缓存已清理）...")
    result3 = mock_api_call("test")
    print(f"结果: {result3}")
    print(f"是否是新值: {result1['value'] != result3['value']}")
