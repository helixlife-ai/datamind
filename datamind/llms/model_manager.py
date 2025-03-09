from pathlib import Path
import logging
from typing import Optional, Dict, Any, Union, Literal, AsyncGenerator
from sentence_transformers import SentenceTransformer
from openai import AsyncOpenAI
from ..config.settings import DEFAULT_EMBEDDING_MODEL, DEFAULT_GENERATOR_MODEL, DEFAULT_LLM_API_BASE, DEFAULT_REASONING_MODEL
from ..utils.common import download_model
import asyncio

ModelType = Literal["local", "api"]

class ModelConfig:
    """模型配置类"""
    def __init__(self, 
                 name: str,
                 model_type: ModelType,
                 model_path: Optional[str] = None,
                 api_base: Optional[str] = None,
                 api_key: Optional[Union[str, list]] = None,
                 **kwargs):
        self.name = name
        self.model_type = model_type
        self.model_path = model_path
        self.api_base = api_base or DEFAULT_LLM_API_BASE
        # 确保api_key始终是列表格式
        self.api_keys = api_key if isinstance(api_key, list) else [api_key] if api_key else []
        self.extra_config = kwargs

class ModelManager:
    """模型管理器，支持本地模型和API调用"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """初始化模型管理器
        
        Args:
            logger: 可选，日志记录器实例
        """
        # 使用提供的日志记录器或创建一个新的
        self.logger = logger or logging.getLogger(__name__)
        
        # 不再设置日志级别，使用传入的记录器的级别
        # 不再添加处理器，依赖外部配置
        
        self.embedding_models: Dict[str, SentenceTransformer] = {}
        self.llm_clients: Dict[str, Dict[str, AsyncOpenAI]] = {}  # 修改为嵌套字典
        self.model_configs: Dict[str, ModelConfig] = {}
        self.current_key_index: Dict[str, int] = {}  # 记录每个模型当前使用的密钥索引
        
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
            if not download_model(config.name, model_path):
                raise RuntimeError(f"下载模型 {config.name} 失败")
        else:
            self.logger.info(f"从本地加载模型: {model_path}")
            
        model = SentenceTransformer(str(model_path))
        return model
    
    def _init_api_embedding_model(self, config: ModelConfig) -> Any:
        """初始化API形式的embedding模型客户端"""
        # 这里可以根据不同的API服务实现相应的客户端
        # 例如OpenAI的ada embedding等
        raise NotImplementedError("API形式的Embedding模型尚未实现")
    
    def _get_next_api_key(self, model_name: str) -> Optional[str]:
        """获取下一个可用的API密钥"""
        config = self.model_configs.get(model_name)
        if not config or not config.api_keys:
            return None
            
        if model_name not in self.current_key_index:
            self.current_key_index[model_name] = 0
        else:
            self.current_key_index[model_name] = (self.current_key_index[model_name] + 1) % len(config.api_keys)
            
        return config.api_keys[self.current_key_index[model_name]]

    def _get_llm_client(self, model_name: str) -> Optional[AsyncOpenAI]:
        """获取或创建LLM客户端"""
        config = self.model_configs.get(model_name)
        if not config:
            self.logger.error(f"未找到模型 {model_name} 的配置")
            return None
            
        if config.model_type == "api":
            api_key = self._get_next_api_key(model_name)
            if not api_key:
                self.logger.error(f"模型 {model_name} 没有可用的API密钥")
                return None
                
            # 初始化该密钥对应的客户端（如果不存在）
            if model_name not in self.llm_clients:
                self.llm_clients[model_name] = {}
                
            if api_key not in self.llm_clients[model_name]:
                try:
                    self.llm_clients[model_name][api_key] = AsyncOpenAI(
                        api_key=api_key,
                        base_url=config.api_base
                    )
                    self.logger.info(f"成功初始化LLM客户端: {model_name}")
                except Exception as e:
                    self.logger.error(f"初始化LLM客户端失败: {str(e)}")
                    return None
                    
            return self.llm_clients[model_name][api_key]
        else:
            self.logger.error(f"本地LLM模型尚未实现: {model_name}")
            return None
    
    async def generate_llm_response(self, 
                                  messages: list,
                                  model_name: str = DEFAULT_GENERATOR_MODEL,
                                  **kwargs) -> Optional[Union[Dict[str, Any], AsyncGenerator]]:
        """生成LLM响应，支持本地和API两种方式
        
        Args:
            messages: 对话消息列表
            model_name: 模型名称，默认使用DEFAULT_LLM_MODEL
            **kwargs: 其他参数传递给API
            
        Returns:
            Optional[Union[Dict[str, Any], AsyncGenerator]]: 
            - 如果stream=True，返回异步生成器
            - 如果stream=False，返回完整的API响应
            如果调用失败则返回None
        """
        try:
            config = self.model_configs.get(model_name)
            if not config:
                self.logger.error(f"未找到模型 {model_name} 的配置")
                return None
                
            if config.model_type == "api":
                client = self._get_llm_client(model_name)
                if not client:
                    return None
                    
                self.logger.debug(f"发送请求到API，模型: {model_name}")
                self.logger.debug(f"请求消息: {messages}")
                self.logger.debug(f"额外参数: {kwargs}")
                
                is_stream = kwargs.get('stream', False)
                max_retries = 3 if not is_stream else 1  # 流式模式下不重试
                retry_count = 0
                
                while retry_count < max_retries:
                    try:
                        response = await client.chat.completions.create(
                            model=model_name,
                            messages=messages,
                            **kwargs
                        )
                        
                        if not response:
                            raise ValueError("API返回空响应")
                            
                        if is_stream:
                            return response  # 返回流式响应
                        else:
                            self.logger.debug(f"API原始响应内容: {response}")
                            return response
                        
                    except Exception as e:
                        retry_count += 1
                        if retry_count < max_retries:
                            self.logger.warning(f"API调用失败，正在进行第{retry_count}次重试: {str(e)}")
                            await asyncio.sleep(1)
                        else:
                            raise
                    
            else:  # local
                return await self._generate_local_llm_response(config, messages, **kwargs)
                
        except Exception as e:
            self.logger.error(f"LLM调用失败: {str(e)}")
            self.logger.exception("详细错误信息:")
            return None
            
    async def _generate_local_llm_response(self, 
                                         config: ModelConfig,
                                         messages: list,
                                         **kwargs) -> Optional[Dict[str, Any]]:
        """使用本地LLM模型生成响应"""
        # 这里可以实现本地模型的调用，比如llama.cpp等
        raise NotImplementedError("本地LLM模型尚未实现")

    async def generate_reasoned_response(self,
                                       messages: list,
                                       model_name: str = DEFAULT_REASONING_MODEL,
                                       **kwargs) -> Optional[Union[Dict[str, Any], AsyncGenerator]]:
        """生成带推理过程的LLM响应
        
        Args:
            messages: 对话消息列表
            model_name: 模型名称，默认使用DEFAULT_REASONING_MODEL
            **kwargs: 其他参数传递给API
            
        Returns:
            Optional[Union[Dict[str, Any], AsyncGenerator]]: 
            - 如果stream=True，返回异步生成器
            - 如果stream=False，返回完整的API响应
            如果调用失败则返回None
        """
        try:
            config = self.model_configs.get(model_name)
            if not config:
                self.logger.error(f"未找到模型 {model_name} 的配置")
                return None
                
            if config.model_type != "api":
                self.logger.error(f"推理模型目前仅支持API调用: {model_name}")
                return None
                
            client = self._get_llm_client(model_name)
            if not client:
                return None
                
            self.logger.debug(f"发送请求到API，模型: {model_name}")
            self.logger.debug(f"请求消息: {messages}")
            self.logger.debug(f"额外参数: {kwargs}")
            
            is_stream = kwargs.get('stream', False)
            max_retries = 3 if not is_stream else 1  # 流式模式下不重试
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    response = await client.chat.completions.create(
                        model=model_name,
                        messages=messages,
                        **kwargs
                    )
                    
                    if not response:
                        raise ValueError("API返回空响应")
                        
                    if is_stream:
                        return response  # 返回流式响应
                    else:
                        self.logger.debug(f"API原始响应内容: {response}")
                        return response
                    
                except Exception as e:
                    retry_count += 1
                    if retry_count < max_retries:
                        self.logger.warning(f"API调用失败，正在进行第{retry_count}次重试: {str(e)}")
                        await asyncio.sleep(1)
                    else:
                        raise
                
        except Exception as e:
            self.logger.error(f"推理模型调用失败: {str(e)}")
            self.logger.exception("详细错误信息:")
            return None 