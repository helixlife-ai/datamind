from typing import List, Dict, Any, Optional
from ..models.model_manager import ModelManager
from dataclasses import dataclass, field
from datetime import datetime
import logging

@dataclass
class ChatMessage:
    """对话消息数据类"""
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

class ReasonerChat:
    """推理模型对话管理类"""
    
    def __init__(self, model_manager: ModelManager, model_name: Optional[str] = None):
        """
        初始化推理对话管理器
        
        Args:
            model_manager: ModelManager实例
            model_name: 可选，指定使用的推理模型名称
        """
        self.logger = logging.getLogger(__name__)
        self.model_manager = model_manager
        self.model_name = model_name
        self.messages: List[ChatMessage] = []
        self.system_prompt: Optional[str] = None
        
    def set_system_prompt(self, prompt: str) -> None:
        """设置系统提示词"""
        self.system_prompt = prompt
        
    def add_message(self, role: str, content: str, **metadata) -> None:
        """
        添加新的对话消息
        
        Args:
            role: 消息角色 ("user" 或 "assistant")
            content: 消息内容
            **metadata: 可选的元数据
        """
        message = ChatMessage(role=role, content=content, metadata=metadata)
        self.messages.append(message)
        
    def clear_history(self) -> None:
        """清空对话历史"""
        self.messages.clear()
        
    def get_formatted_messages(self) -> List[Dict[str, str]]:
        """
        获取格式化的消息列表，用于API调用
        
        Returns:
            List[Dict[str, str]]: 符合API格式的消息列表
        """
        formatted_messages = []
        
        if self.system_prompt:
            formatted_messages.append({
                "role": "system",
                "content": self.system_prompt
            })
            
        for msg in self.messages:
            formatted_messages.append({
                "role": msg.role,
                "content": msg.content
            })
            
        return formatted_messages
    
    async def get_response(self, 
                          temperature: float = 0.6,
                          max_tokens: Optional[int] = None,
                          **kwargs) -> Optional[str]:
        """
        获取模型响应
        
        Args:
            temperature: 采样温度
            max_tokens: 最大生成token数
            **kwargs: 传递给API的其他参数
        
        Returns:
            Optional[str]: 模型响应内容，如果调用失败返回None
        """
        try:
            formatted_messages = self.get_formatted_messages()
            if not formatted_messages:
                self.logger.warning("没有对话消息")
                return None
                
            response = await self.model_manager.generate_reasoned_response(
                messages=formatted_messages,
                model_name=self.model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            
            if not response:
                return None
                
            response_content = response.choices[0].message.content
            self.add_message("assistant", response_content)
            
            return response_content
            
        except Exception as e:
            self.logger.error(f"获取响应失败: {str(e)}")
            return None
            
    def get_chat_history(self) -> List[Dict[str, Any]]:
        """
        获取完整的对话历史，包含每条消息的角色、内容、时间戳和元数据。
        
        Returns:
            List[Dict[str, Any]]: 包含时间戳和元数据的对话历史。
            返回数据示例:
            [
                {
                    "role": "user",
                    "content": "你好，请帮我分析这段代码",
                    "timestamp": "2024-02-15T22:51:03.123456",
                    "metadata": {"source": "web_interface", "session_id": "abc123"}
                },
                {
                    "role": "assistant",
                    "content": "这段代码实现了...",
                    "timestamp": "2024-02-15T22:51:05.234567",
                    "metadata": {"model": "gpt-4", "tokens": 150}
                }
            ]
        """
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat(),
                "metadata": msg.metadata
            }
            for msg in self.messages
        ]
        
    def save_chat_history_to_json(self, filepath: str) -> bool:
        """
        将对话历史保存为JSON文件
        
        Args:
            filepath: JSON文件保存路径，例如 "chat_history.json"
            
        Returns:
            bool: 保存成功返回True，失败返回False
            
        示例:
            >>> chat.save_chat_history_to_json("conversations/chat_20240215.json")
        """
        try:
            import json
            from pathlib import Path
            
            # 确保目标目录存在
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            
            # 获取聊天历史并保存
            chat_history = self.get_chat_history()
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(chat_history, f, ensure_ascii=False, indent=2)
                
            self.logger.info(f"对话历史已保存至: {filepath}")
            return True
            
        except Exception as e:
            self.logger.error(f"保存对话历史失败: {str(e)}")
            return False

    def load_chat_history_from_json(self, filepath: str) -> bool:
        """
        从JSON文件加载对话历史
        
        Args:
            filepath: JSON文件路径，例如 "chat_history.json"
            
        Returns:
            bool: 加载成功返回True，失败返回False
            
        示例:
            >>> chat.load_chat_history_from_json("conversations/chat_20240215.json")
        """
        try:
            import json
            from datetime import datetime
            
            # 读取JSON文件
            with open(filepath, 'r', encoding='utf-8') as f:
                chat_history = json.load(f)
            
            # 清空当前历史
            self.clear_history()
            
            # 转换并添加消息
            for msg in chat_history:
                # 将ISO格式时间字符串转换回datetime对象
                timestamp = datetime.fromisoformat(msg['timestamp'])
                
                # 创建新的ChatMessage对象
                message = ChatMessage(
                    role=msg['role'],
                    content=msg['content'],
                    timestamp=timestamp,
                    metadata=msg['metadata']
                )
                self.messages.append(message)
                
            self.logger.info(f"已从 {filepath} 加载对话历史")
            return True
            
        except Exception as e:
            self.logger.error(f"加载对话历史失败: {str(e)}")
            return False 