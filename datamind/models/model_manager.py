from pathlib import Path
import logging
from typing import Optional, Dict, Any, Union, Literal
from sentence_transformers import SentenceTransformer
from openai import AsyncOpenAI
from ..config.settings import DEFAULT_EMBEDDING_MODEL, DEFAULT_LLM_MODEL

ModelType = Literal["local", "api"]

class ModelConfig:
    """模型配置类"""
    def __init__(self, 
                 name: str,
                 model_type: ModelType,
                 model_path: Optional[str] = None,
                 api_base: Optional[str] = None,
                 api_key: Optional[str] = None,
                 **kwargs):
        self.name = name
        self.model_type = model_type
        self.model_path = model_path
        self.api_base = api_base or "https://api.deepseek.com"
        self.api_key = api_key
        self.extra_config = kwargs

class ModelManager:
    """模型管理器，支持本地模型和API调用"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.embedding_models: Dict[str, SentenceTransformer] = {}
        self.llm_clients: Dict[str, AsyncOpenAI] = {}
        self.model_configs: Dict[str, ModelConfig] = {}
        
    def register_model(self, config: ModelConfig):
        """注册模型配置"""
        self.model_configs[config.name] = config
        self.logger.info(f"注册模型配置: {config.name} ({config.model_type})")
        
    def get_embedding_model(self, model_name: str = DEFAULT_EMBEDDING_MODEL) -> Optional[SentenceTransformer]:
        """获取文本嵌入模型，支持本地和API两种方式"""
        if model_name not in self.embedding_models:
            config = self.model_configs.get(model_name)
            if not config:
                self.logger.error(f"未找到模型 {model_name} 的配置，请先调用register_model注册模型")
                return None
                
            try:
                if config.model_type == "local":
                    self.embedding_models[model_name] = self._load_local_embedding_model(config)
                else:  # api
                    self.embedding_models[model_name] = self._init_api_embedding_model(config)
                    
            except Exception as e:
                self.logger.error(f"加载模型 {model_name} 失败: {str(e)}")
                return None
        
        model = self.embedding_models.get(model_name)
        if not model:
            self.logger.warning(f"模型 {model_name} 加载失败或未找到")
        return model
    
    def _load_local_embedding_model(self, config: ModelConfig) -> SentenceTransformer:
        """加载本地embedding模型"""
        root_dir = Path.cwd()
        model_path = config.model_path or root_dir / 'model_cache' / config.name
        model_path = Path(model_path)
        
        if not model_path.exists() or not list(model_path.glob('*')):
            self.logger.info(f"模型文件不存在，开始下载到本地: {model_path}")
            model = SentenceTransformer(config.name)
            model.save(str(model_path))
        else:
            self.logger.info(f"从本地加载模型: {model_path}")
            model = SentenceTransformer(str(model_path))
            
        return model
    
    def _init_api_embedding_model(self, config: ModelConfig) -> Any:
        """初始化API形式的embedding模型客户端"""
        # 这里可以根据不同的API服务实现相应的客户端
        # 例如OpenAI的ada embedding等
        raise NotImplementedError("API形式的Embedding模型尚未实现")
    
    def _get_llm_client(self, model_name: str) -> Optional[AsyncOpenAI]:
        """获取或创建LLM客户端"""
        if model_name not in self.llm_clients:
            config = self.model_configs.get(model_name)
            if not config:
                self.logger.error(f"未找到模型 {model_name} 的配置")
                return None
                
            if config.model_type == "api":
                if not config.api_key:
                    self.logger.error(f"模型 {model_name} 缺少API密钥")
                    return None
                    
                try:
                    self.llm_clients[model_name] = AsyncOpenAI(
                        api_key=config.api_key,
                        base_url=config.api_base
                    )
                    self.logger.info(f"成功初始化LLM客户端: {model_name}")
                except Exception as e:
                    self.logger.error(f"初始化LLM客户端失败: {str(e)}")
                    return None
            else:
                self.logger.error(f"本地LLM模型尚未实现: {model_name}")
                return None
                
        return self.llm_clients.get(model_name)
    
    async def generate_llm_response(self, 
                                  messages: list,
                                  model_name: str = DEFAULT_LLM_MODEL,
                                  **kwargs) -> Optional[Dict[str, Any]]:
        """生成LLM响应，支持本地和API两种方式"""
        config = self.model_configs.get(model_name)
        if not config:
            self.logger.error(f"未找到模型 {model_name} 的配置")
            return None
            
        try:
            if config.model_type == "api":
                client = self._get_llm_client(model_name)
                if not client:
                    return None
                    
                response = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    stream=False,
                    **kwargs
                )
                
                return response
                
            else:  # local
                return await self._generate_local_llm_response(config, messages, **kwargs)
                
        except Exception as e:
            self.logger.error(f"LLM调用失败: {str(e)}")
            return None
            
    async def _generate_local_llm_response(self, 
                                         config: ModelConfig,
                                         messages: list,
                                         **kwargs) -> Optional[Dict[str, Any]]:
        """使用本地LLM模型生成响应"""
        # 这里可以实现本地模型的调用，比如llama.cpp等
        raise NotImplementedError("本地LLM模型尚未实现") 