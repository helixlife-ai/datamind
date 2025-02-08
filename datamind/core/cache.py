from typing import Dict, Optional
import time
import json
from dataclasses import dataclass

@dataclass
class CacheEntry:
    result: Dict
    timestamp: float
    
class QueryCache:
    """查询结果缓存"""
    
    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        self.cache: Dict[str, CacheEntry] = {}
        self.max_size = max_size
        self.ttl = ttl  # 缓存生存时间(秒)
        
    def get(self, query: str) -> Optional[Dict]:
        """获取缓存的查询结果"""
        if query not in self.cache:
            return None
            
        entry = self.cache[query]
        if time.time() - entry.timestamp > self.ttl:
            del self.cache[query]
            return None
            
        return entry.result
        
    def store(self, query: str, result: Dict):
        """存储查询结果"""
        if len(self.cache) >= self.max_size:
            # 删除最旧的条目
            oldest = min(self.cache.items(), key=lambda x: x[1].timestamp)
            del self.cache[oldest[0]]
            
        self.cache[query] = CacheEntry(
            result=result,
            timestamp=time.time()
        ) 