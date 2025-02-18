import logging
from pathlib import Path

class StreamLineHandler(logging.Handler):
    """处理流式输出的自定义日志处理器"""
    def __init__(self, filename):
        super().__init__()
        self.filename = filename
        self.last_content = ""
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
    
    def _process_stream_message(self, content):
        """处理流式消息的内部方法"""
        new_content = content[len(self.last_content):]
        self.last_content = content       
        return new_content
    
    def emit(self, record):
        try:
            msg = self.format(record)
            
            with open(self.filename, 'a', encoding='utf-8') as f:
                if record.getMessage().startswith('\r'):
                    content = record.getMessage().replace('\r', '')
                    new_content = self._process_stream_message(content)
                    f.write(new_content)
                else:
                    f.write(msg + '\n')
                    self.last_content = ""
                    
        except Exception:
            self.handleError(record) 