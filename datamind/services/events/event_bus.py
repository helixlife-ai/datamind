import asyncio
from typing import Callable, Any
from .event_types import AlchemyEventType

class EventBus:
    """事件总线，用于事件发布和订阅"""
    
    def __init__(self):
        self.subscribers = {}
        
    def subscribe(self, event_type: AlchemyEventType, callback: Callable):
        """订阅事件"""
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)
        
    def unsubscribe(self, event_type: AlchemyEventType, callback: Callable):
        """取消订阅事件"""
        if event_type in self.subscribers and callback in self.subscribers[event_type]:
            self.subscribers[event_type].remove(callback)
            
    async def publish(self, event_type: AlchemyEventType, data: Any = None):
        """发布事件"""
        if event_type in self.subscribers:
            for callback in self.subscribers[event_type]:
                if asyncio.iscoroutinefunction(callback):
                    # 创建任务而不是等待，避免阻塞事件发布
                    asyncio.create_task(callback(data))
                else:
                    callback(data) 