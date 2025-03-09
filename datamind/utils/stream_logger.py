import logging
import os
from typing import Optional

class StreamLineHandler(logging.FileHandler):
    """流式日志处理器，专门用于处理流式输出的日志
    
    这个处理器会将每行日志写入到单独的文件中，避免在流式输出时
    产生大量重复的日志记录。它只记录新的内容，而不是整个累积的内容。
    """
    
    def __init__(self, filename, mode='a', encoding=None, delay=False):
        """初始化流式日志处理器
        
        Args:
            filename: 日志文件路径
            mode: 文件打开模式，默认为'a'（追加）
            encoding: 文件编码
            delay: 是否延迟打开文件
        """
        super().__init__(filename, mode, encoding, delay)
        self.last_record = ""
        
    def emit(self, record):
        """发出日志记录
        
        重写emit方法，只记录新的内容，避免重复
        
        Args:
            record: 日志记录
        """
        try:
            # 获取格式化后的消息
            msg = self.format(record)
            
            # 如果消息与上一条相同，跳过
            if msg == self.last_record:
                return
                
            # 如果消息是上一条的子串，只记录新增部分
            if self.last_record and msg.startswith(self.last_record):
                # 只写入新增的部分
                new_content = msg[len(self.last_record):]
                if new_content:
                    stream = self.stream
                    stream.write(new_content + self.terminator)
                    self.flush()
            else:
                # 完全不同的消息，正常记录
                stream = self.stream
                stream.write(msg + self.terminator)
                self.flush()
                
            # 更新上一条记录
            self.last_record = msg
            
        except Exception:
            self.handleError(record) 