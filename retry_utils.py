"""API 重试装饰器 - 指数退避 + 抖动"""
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type
import requests
import socket


# 网络相关异常，值得重试
NETWORK_EXCEPTIONS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
    socket.timeout,
    ConnectionResetError,
    OSError,
)


# 通用重试：3次，指数退避 1-10秒
api_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
    retry=retry_if_exception_type(NETWORK_EXCEPTIONS),
    reraise=True,
)


# 关键操作重试：5次，指数退避 2-30秒
api_retry_important = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(initial=2, max=30, jitter=5),
    retry=retry_if_exception_type(NETWORK_EXCEPTIONS),
    reraise=True,
)
