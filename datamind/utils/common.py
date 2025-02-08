import logging
from pathlib import Path
from sentence_transformers import SentenceTransformer
from ..config.settings import DEFAULT_EMBEDDING_MODEL

def setup_logging():
    """配置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)

def download_model():
    """下载并保存模型到本地缓存"""
    logger = logging.getLogger(__name__)
    try:
        root_dir = Path.cwd()
        model_cache_dir = root_dir / 'model_cache' / DEFAULT_EMBEDDING_MODEL
        model_cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"开始下载模型 {DEFAULT_EMBEDDING_MODEL} ...")
        model = SentenceTransformer(DEFAULT_EMBEDDING_MODEL)
        model.save(str(model_cache_dir))
        logger.info(f"模型已成功下载并保存到: {model_cache_dir}")
        
        if list(model_cache_dir.glob('*')):
            logger.info("模型文件验证成功")
            return True
        else:
            logger.warning("警告：模型目录为空")
            return False
            
    except Exception as e:
        logger.error(f"模型下载失败: {str(e)}")
        return False 