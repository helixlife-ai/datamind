import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime


def prepare_context_files(context_files: List[str], 
                          context_dir: Path, 
                          work_base: Path,
                          logger: Optional[logging.Logger] = None) -> Tuple[Dict[str, str], Dict[str, Dict]]:
    """准备上下文文件，复制文件并收集内容与元数据
    
    Args:
        context_files: 上下文文件路径列表
        context_dir: 上下文文件目标目录
        work_base: 工作目录基础路径
        logger: 可选，日志记录器实例
        
    Returns:
        Tuple[Dict[str, str], Dict[str, Dict]]: (context_contents, context_files_info)
    """
    # 使用提供的logger或创建一个新的
    if logger is None:
        logger = logging.getLogger(__name__)
    
    context_contents = {}
    context_files_info = {}
    all_file_paths = set()  # 用于存储去重后的文件路径
    
    # 1. 从搜索结果文件中提取所有文件路径
    for file_path in context_files:
        # 将搜索结果文件本身也添加到文件路径集合中
        all_file_paths.add(file_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                results_data = json.load(f)
            
            # 处理structured类型的结果
            if "structured" in results_data:
                for item in results_data["structured"]:
                    if "_file_path" in item:
                        all_file_paths.add(item["_file_path"])
            
            # 处理vector类型的结果
            if "vector" in results_data:
                for item in results_data["vector"]:
                    if "file_path" in item:
                        all_file_paths.add(item["file_path"])
        except Exception as e:
            logger.error(f"提取文件路径时出错: {str(e)}")
    
    # 2. 保存去重后的文件路径列表到JSON文件
    file_paths_list = list(all_file_paths)
    file_paths_json = {
        "file_paths": file_paths_list,
        "total_count": len(file_paths_list),
        "generated_at": datetime.now().isoformat()
    }
    
    paths_json_file = context_dir / "file_paths.json"
    try:
        with open(paths_json_file, 'w', encoding='utf-8') as f:
            json.dump(file_paths_json, f, ensure_ascii=False, indent=2)
        logger.info(f"已保存文件路径列表到 {paths_json_file}")
    except Exception as e:
        logger.error(f"保存文件路径列表时出错: {str(e)}")
    
    # 3. 加载所有文件路径中的文件内容
    for file_path in all_file_paths:
        path_obj = Path(file_path)
        if not path_obj.exists():
            continue
            
        rel_path = str(path_obj.relative_to(work_base)) if work_base in path_obj.parents else path_obj.name
        
        # 读取文件内容
        file_content = read_file_content(file_path, logger=logger)
        if file_content:
            context_contents[rel_path] = file_content
            
            # 收集文件元数据
            file_stat = path_obj.stat()
            context_files_info[rel_path] = {
                "file_name": path_obj.name,
                "file_size": file_stat.st_size,
                "last_modified": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                "absolute_path": str(path_obj.absolute()),
                "relative_path": rel_path
            }
    
    return context_contents, context_files_info


def read_file_content(file_path: str, encoding: str = 'utf-8', logger: Optional[logging.Logger] = None) -> Optional[str]:
    """读取文件内容
    
    Args:
        file_path: 文件路径
        encoding: 编码方式，默认utf-8
        logger: 可选，日志记录器实例
        
    Returns:
        Optional[str]: 文件内容，如果读取失败则返回None
    """
    # 使用提供的logger或创建一个新的
    if logger is None:
        logger = logging.getLogger(__name__)
        
    try:
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"文件不存在: {file_path}")
            return None
        
        with path.open('r', encoding=encoding) as f:
            content = f.read()
        
        logger.info(f"成功读取文件: {file_path}")
        return content
    
    except UnicodeDecodeError:
        # 如果UTF-8解码失败，尝试使用latin-1
        try:
            logger.warning(f"UTF-8解码失败，尝试使用latin-1解码: {file_path}")
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()
        except Exception as e:
            logger.error(f"读取文件 {file_path} 时发生错误: {str(e)}")
            return None
            
    except Exception as e:
        logger.error(f"读取文件 {file_path} 时发生错误: {str(e)}")
        return None 