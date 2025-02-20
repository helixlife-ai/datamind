import logging
from pathlib import Path
from sentence_transformers import SentenceTransformer
from typing import Optional
import json
import numpy as np
from datetime import datetime, date
import pandas as pd


class DateTimeEncoder(json.JSONEncoder):
    """增强版JSON编码器，处理datetime和numpy类型"""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

def setup_logging():
    """配置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)

def download_model(model_name: str, save_dir: Optional[Path] = None) -> bool:
    """下载并保存模型到本地缓存
    
    Args:
        model_name: 要下载的模型名称
        save_dir: 保存目录，如果为None则使用默认的model_cache目录
        
    Returns:
        bool: 下载是否成功
    """
    logger = logging.getLogger(__name__)
    try:
        root_dir = Path.cwd()
        if save_dir is None:
            save_dir = root_dir / 'model_cache' / model_name
            
        save_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"开始下载模型 {model_name} ...")
        model = SentenceTransformer(model_name)
        model.save(str(save_dir))
        logger.info(f"模型已成功下载并保存到: {save_dir}")
        
        if list(save_dir.glob('*')):
            logger.info("模型文件验证成功")
            return True
        else:
            logger.warning("警告：模型目录为空")
            return False
            
    except Exception as e:
        logger.error(f"模型下载失败: {str(e)}")
        return False 