"""并发安全模块 - 文件锁保护 JSON 读写"""
import json
import os
from filelock import FileLock


def _lock_path(filepath: str) -> str:
    """根据文件路径生成锁文件路径"""
    return filepath + ".lock"


def safe_load_json(filepath: str, default=None, encoding="utf-8"):
    """带锁读取 JSON 文件"""
    lock = FileLock(_lock_path(filepath), timeout=30)
    with lock:
        if not os.path.exists(filepath):
            return default if default is not None else {}
        with open(filepath, "r", encoding=encoding) as f:
            return json.load(f)


def safe_save_json(filepath: str, data, encoding="utf-8", indent=2):
    """带锁写入 JSON 文件"""
    lock = FileLock(_lock_path(filepath), timeout=30)
    with lock:
        with open(filepath, "w", encoding=encoding) as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)


def safe_update_json(filepath: str, update_fn, default=None, encoding="utf-8"):
    """带锁读取-修改-写入 JSON 文件（原子操作）
    
    Args:
        update_fn: 接收当前数据，返回修改后数据的函数
    """
    lock = FileLock(_lock_path(filepath), timeout=30)
    with lock:
        if not os.path.exists(filepath):
            data = default if default is not None else {}
        else:
            with open(filepath, "r", encoding=encoding) as f:
                data = json.load(f)
        
        data = update_fn(data)
        
        with open(filepath, "w", encoding=encoding) as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    return data
