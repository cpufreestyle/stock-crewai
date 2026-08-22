"""
API 缓存层 - 减少重复请求，提升性能
支持 TTL（Time-To-Live）+ LRU 淘汰，线程安全
"""

import time
import functools
import threading
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional
import hashlib

from config import CACHE_TTL_REALTIME, CACHE_TTL_MARKET, CACHE_TTL_KLINE

_DEFAULT_MAX_SIZE = 500


class TTLCache:
    """TTL + LRU 缓存，线程安全"""

    def __init__(self, default_ttl: int = 60, max_size: int = _DEFAULT_MAX_SIZE):
        self.default_ttl = default_ttl
        self.max_size = max_size
        self._cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    def _make_key(self, func_name: str, args: tuple, kwargs: dict) -> str:
        """生成缓存 key（list/tuple 参数排序以提升命中率）"""
        key_parts = [func_name]
        for arg in args:
            if isinstance(arg, (list, tuple)):
                key_parts.append(",".join(sorted(str(x) for x in arg)))
            else:
                key_parts.append(str(arg))
        key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return hashlib.md5("|".join(key_parts).encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if time.time() > entry['expires_at']:
                del self._cache[key]
                return None
            # LRU: 移到末尾（dict 保持插入序，末尾=最近使用）
            self._cache.move_to_end(key)
            return entry['value']

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        with self._lock:
            ttl = ttl if ttl is not None else self.default_ttl
            self._cache[key] = {
                'value': value,
                'expires_at': time.time() + ttl,
                'created_at': time.time(),
            }
            # LRU 淘汰：超容量时删除最旧条目
            while len(self._cache) > self.max_size:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def clear_expired(self) -> int:
        with self._lock:
            now = time.time()
            expired = [k for k, e in self._cache.items() if now > e['expires_at']]
            for k in expired:
                del self._cache[k]
            return len(expired)
        
        return len(expired_keys)
    
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            valid = sum(1 for e in self._cache.values() if now <= e['expires_at'])
            return {
                'total': len(self._cache),
                'valid': valid,
                'expired': len(self._cache) - valid,
                'max_size': self.max_size,
            }


# 创建全局缓存实例（TTL 统一由 config.py 管理）
realtime_cache = TTLCache(default_ttl=CACHE_TTL_REALTIME)   # 实时行情缓存
market_cache = TTLCache(default_ttl=CACHE_TTL_MARKET)       # 市场状态缓存
kline_cache = TTLCache(default_ttl=CACHE_TTL_KLINE)         # K线数据缓存
api_cache = TTLCache(default_ttl=30)                        # 通用 API 缓存 30 秒


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
