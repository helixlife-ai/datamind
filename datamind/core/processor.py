import os
import json
import magic
import xmltodict
import pandas as pd
import duckdb
from pathlib import Path
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Optional, Set
from sentence_transformers import SentenceTransformer
from ..config.settings import DEFAULT_EMBEDDING_MODEL, DEFAULT_DB_PATH
from ..utils.common import download_model
import pickle
from ..models.model_manager import ModelManager, ModelConfig

class FileCache:
    """文件缓存管理器"""
    
    def __init__(self, cache_file: str = None, max_age_days: int = 30):
        self.logger = logging.getLogger(__name__)
        self.cache_file = cache_file or Path(DEFAULT_DB_PATH).parent / 'file_cache.pkl'
        self.max_age = timedelta(days=max_age_days)
        self.cache: Dict[str, Dict] = {}
        self.modified: Set[str] = set()
        self._load_cache()
    
    def _load_cache(self):
        """从文件加载缓存"""
        if Path(self.cache_file).exists():
            try:
                with open(self.cache_file, 'rb') as f:
                    self.cache = pickle.load(f)
                self.logger.info(f"已加载 {len(self.cache)} 个文件的缓存记录")
                self._cleanup_expired()
            except Exception as e:
                self.logger.error(f"加载缓存文件失败: {str(e)}")
                self.cache = {}
    
    def _save_cache(self):
        """保存缓存到文件"""
        if not self.modified:
            return
            
        try:
            cache_dir = Path(self.cache_file).parent
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.cache, f)
            self.modified.clear()
            self.logger.debug("缓存已保存到文件")
        except Exception as e:
            self.logger.error(f"保存缓存文件失败: {str(e)}")
    
    def _cleanup_expired(self):
        """清理过期缓存"""
        now = datetime.now()
        expired = []
        
        for path, info in self.cache.items():
            age = now - info['processed_at']
            if age > self.max_age:
                expired.append(path)
                
        for path in expired:
            del self.cache[path]
            
        if expired:
            self.modified.add('cleanup')
            self.logger.info(f"已清理 {len(expired)} 个过期缓存记录")
    
    def get(self, file_path: str) -> Optional[Dict]:
        """获取文件缓存信息"""
        return self.cache.get(str(file_path))
    
    def update(self, file_path: str, info: Dict):
        """更新文件缓存信息"""
        self.cache[str(file_path)] = info
        self.modified.add(str(file_path))
    
    def remove(self, file_paths: List[str]):
        """删除文件缓存信息"""
        for path in file_paths:
            self.cache.pop(str(path), None)
        if file_paths:
            self.modified.add('remove')
    
    def batch_update(self, updates: Dict[str, Dict]):
        """批量更新缓存"""
        self.cache.update(updates)
        self.modified.update(updates.keys())
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._save_cache()

class DataProcessor:
    """数据预处理器"""
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.logger = logging.getLogger(__name__)
        self.db_path = db_path
        self.parser = FileParser()
        self.storage = StorageSystem(db_path)
        self.file_cache = FileCache()
        
    def process_directory(self, input_dirs: List[str], max_depth: int = 3, 
                         incremental: bool = True) -> Dict:
        """处理指定目录
        
        Args:
            input_dirs: 输入目录列表
            max_depth: 最大扫描深度
            incremental: 是否启用增量更新
        """
        start_time = datetime.now()
        self.logger.info("="*50)
        self.logger.info(f"开始{'增量' if incremental else '全量'}数据处理任务")
        
        with self.file_cache:  # 自动保存缓存
            try:
                # 扫描文件
                scanned_files = self._scan_directories(input_dirs, max_depth)
                self.logger.info(f"扫描完成，共发现 {len(scanned_files)} 个文件")
                
                # 确定需要处理的文件
                files_to_process = []
                for file_path in scanned_files:
                    if not incremental or self._need_update(file_path):
                        files_to_process.append(file_path)
                
                self.logger.info(f"需要处理的文件数: {len(files_to_process)}")
                
                # 批量处理文件
                stats = self._process_files(files_to_process)
                
                # 处理已删除的文件
                if incremental:
                    removed_count = self._handle_removed_files(input_dirs, scanned_files)
                    stats['removed_files'] = removed_count
                
                # 更新统计信息
                total_time = (datetime.now() - start_time).total_seconds()
                stats.update({
                    'total_time': total_time,
                    'avg_time_per_file': total_time / len(files_to_process) if files_to_process else 0,
                    'update_mode': 'incremental' if incremental else 'full'
                })
                
                self.logger.info("="*50)
                self.logger.info(f"处理完成，总耗时: {total_time:.2f}秒")
                return stats
                
            except Exception as e:
                self.logger.error(f"处理过程出错: {str(e)}", exc_info=True)
                return {
                    'status': 'error',
                    'error': str(e),
                    'total_time': (datetime.now() - start_time).total_seconds()
                }
        
    def _scan_directories(self, input_dirs: List[str], max_depth: int) -> List[Path]:
        """扫描目录获取文件列表"""
        self.logger.info(f"开始扫描目录: {input_dirs}")
        found = []
        
        for path in [Path(p) for p in input_dirs]:
            if path.is_file():
                found.append(path)
                self.logger.debug(f"添加文件: {path}")
            elif path.is_dir():
                self.logger.info(f"扫描目录: {path}")
                for root, dirs, files in os.walk(path):
                    depth = len(Path(root).relative_to(path).parts)
                    if depth > max_depth:
                        self.logger.debug(f"跳过深度 {depth} 的目录: {root}")
                        del dirs[:]
                        continue
                    for f in files:
                        if not f.startswith('.'):
                            found.append(Path(root)/f)
                            self.logger.debug(f"添加文件: {f}")
        
        return sorted(found)
        
    def _process_files(self, files: List[Path]) -> Dict:
        """处理文件列表"""
        stats = {
            'total_files': len(files),
            'successful_files': 0,
            'failed_files': 0,
            'total_records': 0,
            'errors': []
        }
        
        # 批量缓存更新
        cache_updates = {}
        
        for i, file_path in enumerate(files, 1):
            self.logger.info(f"处理文件 [{i}/{stats['total_files']}]: {file_path}")
            file_start_time = datetime.now()
            
            try:
                df = self.parser.parse(file_path)
                if df is not None and not df.empty:
                    records_count = len(df)
                    self.logger.info(f"文件解析成功，获得 {records_count} 条记录")
                    
                    self.storage.save(df)
                    
                    # 更新缓存信息
                    cache_updates[str(file_path)] = {
                        'processed_at': datetime.now(),
                        'record_count': records_count,
                        'size': file_path.stat().st_size
                    }
                    
                    stats['successful_files'] += 1
                    stats['total_records'] += records_count
                    
                    process_time = (datetime.now() - file_start_time).total_seconds()
                    self.logger.info(f"文件处理成功，耗时: {process_time:.2f}秒")
                else:
                    stats['failed_files'] += 1
                    error_msg = f"文件处理失败: {file_path}"
                    stats['errors'].append(error_msg)
                    self.logger.warning(error_msg)
                    
            except Exception as e:
                stats['failed_files'] += 1
                error_msg = f"文件处理异常: {file_path} - {str(e)}"
                stats['errors'].append(error_msg)
                self.logger.error(error_msg, exc_info=True)
        
        # 批量更新缓存
        if cache_updates:
            self.file_cache.batch_update(cache_updates)
            
        return stats

    def _need_update(self, file_path: Path) -> bool:
        """检查文件是否需要更新"""
        str_path = str(file_path)
        cache_info = self.file_cache.get(str_path)
        
        if not cache_info:
            return True
            
        try:
            # 获取文件状态
            stat = file_path.stat()
            file_mtime = datetime.fromtimestamp(stat.st_mtime)
            file_size = stat.st_size
            
            # 检查文件是否变化
            return (file_mtime > cache_info['processed_at'] or
                   file_size != cache_info.get('size', 0))
        except Exception as e:
            self.logger.error(f"检查文件状态失败: {str(e)}")
            return True
    
    def _handle_removed_files(self, input_dirs: List[str], 
                            current_files: List[Path]) -> int:
        """处理已删除的文件
        
        Returns:
            int: 删除的记录数
        """
        current_paths = {str(f) for f in current_files}
        removed_paths = []
        
        for cached_path in self.file_cache.cache.keys():
            if any(cached_path.startswith(str(Path(d).absolute())) 
                   for d in input_dirs):
                if cached_path not in current_paths:
                    removed_paths.append(cached_path)
        
        if removed_paths:
            self.logger.info(f"发现 {len(removed_paths)} 个已删除的文件")
            try:
                removed_count = self.storage.remove_by_paths(removed_paths)
                self.file_cache.remove(removed_paths)
                self.logger.info(f"已删除 {removed_count} 条相关记录")
                return removed_count
            except Exception as e:
                self.logger.error(f"删除过期数据失败: {str(e)}")
                
        return 0

class FileParser:
    """文件解析器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.model_manager = ModelManager()
        
        # 注册Embedding模型配置
        self.model_manager.register_model(ModelConfig(
            name=DEFAULT_EMBEDDING_MODEL,
            model_type="local"
        ))
        
        self.text_model = self.model_manager.get_embedding_model()
        
    def parse(self, file_path: Path) -> Optional[pd.DataFrame]:
        """统一的文件解析入口"""
        suffix = file_path.suffix.lower()
        
        try:
            self.logger.info(f"开始解析文件: {file_path}")
            
            # 基础元数据
            base_metadata = {
                '_file_path': str(file_path),
                '_file_name': file_path.name,
                '_file_type': suffix.lstrip('.'),
                '_processed_at': pd.Timestamp.now(),
                '_record_id': f"{file_path.stem}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}"
            }

            # 解析文件内容
            records = self._parse_file(file_path, suffix)
            if not isinstance(records, list):
                records = [records]
            
            # 处理每条记录
            processed_records = []
            for idx, record in enumerate(records, 1):
                record_data = base_metadata.copy()
                record_data['_sub_id'] = idx - 1
                record_data['_record_id'] = f"{record_data['_record_id']}_{idx-1}"
                
                # 扁平化记录
                flat_data = self._flatten_record(record)
                record_data.update(flat_data)
                
                # 生成向量
                if self.text_model:
                    vector = self._generate_vector(flat_data)
                    if vector is not None:
                        record_data['vector'] = vector
                
                processed_records.append(record_data)

            return pd.DataFrame(processed_records)

        except Exception as e:
            self.logger.error(f"解析文件 {file_path} 时出错: {str(e)}", exc_info=True)
            return None
            
    def _parse_file(self, path: Path, suffix: str) -> List[Dict]:
        """根据文件类型选择解析方法"""
        if suffix == '.json':
            return self._parse_json(path)
        elif suffix in ['.csv', '.tsv']:
            return self._parse_csv(path)
        elif suffix in ['.txt', '.md', '.log']:
            return self._parse_text(path)
        elif suffix in ['.xlsx', '.xls']:
            return self._parse_excel(path)
        elif suffix in ['.xml']:
            return self._parse_xml(path)
        else:
            return self._parse_binary(path)
            
    # 具体的解析方法实现...
    def _parse_json(self, path: Path) -> List[Dict]:
        """JSON文件解析"""
        with path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]
        
    def _parse_csv(self, path: Path) -> List[Dict]:
        """CSV文件解析"""
        df = pd.read_csv(path)
        return df.to_dict('records')
        
    def _parse_text(self, path: Path) -> List[Dict]:
        """文本文件解析"""
        content = path.read_text(encoding='utf-8')
        lines = content.splitlines()
        return [{
            'content': content,
            'char_count': len(content),
            'line_count': len(lines)
        }]
        
    def _parse_excel(self, path: Path) -> List[Dict]:
        """Excel文件解析"""
        df = pd.read_excel(path)
        return df.to_dict('records')
        
    def _parse_xml(self, path: Path) -> List[Dict]:
        """XML文件解析"""
        with path.open('r', encoding='utf-8') as f:
            data = xmltodict.parse(f.read())
        return [data]
        
    def _parse_binary(self, path: Path) -> List[Dict]:
        """二进制文件解析"""
        mime = magic.Magic(mime=True)
        file_stat = path.stat()
        return [{
            'size': file_stat.st_size,
            'mime_type': mime.from_file(str(path)),
            'modified_time': datetime.fromtimestamp(file_stat.st_mtime)
        }]
        
    def _flatten_record(self, data: Dict) -> Dict:
        """将记录扁平化为键值对"""
        flat_data = {}
        
        def flatten(obj, prefix=''):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    key = f"{prefix}{k}" if prefix else k
                    if isinstance(v, (str, int, float, bool)) or v is None:
                        flat_data[key] = v
                    elif isinstance(v, (dict, list)):
                        flat_data[key] = json.dumps(v, ensure_ascii=False)
                        flatten(v, f"{key}_")
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    flatten(item, f"{prefix}{i}_")
            elif isinstance(obj, (str, int, float, bool)):
                flat_data[prefix.rstrip('_')] = obj
        
        flatten(data)
        return flat_data
        
    def _generate_vector(self, data: Dict) -> Optional[List[float]]:
        """生成向量表示"""
        if not self.text_model:
            return None
            
        text_parts = []
        for k, v in data.items():
            if isinstance(v, str):
                text_parts.append(f"{k}: {v}")
            elif isinstance(v, (int, float, bool)):
                text_parts.append(f"{k}: {str(v)}")
        
        text = " ".join(text_parts)[:512]
        
        try:
            vector = self.text_model.encode(text)
            return vector.tolist()
        except Exception as e:
            self.logger.error(f"向量化失败: {str(e)}")
            return None

class StorageSystem:
    """存储系统"""
    
    def __init__(self, db_path: str):
        self.logger = logging.getLogger(__name__)
        self.db_path = db_path
        self.db = duckdb.connect(db_path)
        self.init_storage()
    
    def init_storage(self):
        """初始化存储表"""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS unified_data (
                _record_id VARCHAR PRIMARY KEY,
                _file_path VARCHAR,
                _file_name VARCHAR,
                _file_type VARCHAR,
                _processed_at TIMESTAMP,
                _sub_id INTEGER,
                data JSON,
                vector DOUBLE[]
            )
        """)
        
    def save(self, df: pd.DataFrame):
        """保存数据到数据库"""
        if df is None or df.empty:
            self.logger.warning("收到空数据，跳过存储")
            return

        try:
            # 处理向量数据
            vector_data = df['vector'].apply(lambda x: json.dumps(x) if x is not None else None)
            
            # 将其他列打包为JSON
            meta_columns = ['_record_id', '_file_path', '_file_name', 
                          '_file_type', '_processed_at', '_sub_id']
            other_columns = [col for col in df.columns 
                           if col not in meta_columns + ['vector']]
            
            data_dicts = []
            for idx, row in df.iterrows():
                data_dict = {}
                for col in other_columns:
                    if pd.notna(row[col]):
                        data_dict[col] = row[col]
                data_dicts.append(json.dumps(data_dict, ensure_ascii=False))
            
            # 准备存储数据
            df_to_save = df[meta_columns].copy()
            df_to_save['data'] = data_dicts
            df_to_save['vector'] = vector_data
            
            # 存储数据
            for idx, row in df_to_save.iterrows():
                self.db.execute("""
                    INSERT INTO unified_data 
                    (_record_id, _file_path, _file_name, _file_type, _processed_at, _sub_id, data, vector)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (_record_id) DO UPDATE 
                    SET data = EXCLUDED.data,
                        vector = EXCLUDED.vector
                """, (
                    row['_record_id'],
                    row['_file_path'],
                    row['_file_name'],
                    row['_file_type'],
                    row['_processed_at'],
                    row['_sub_id'],
                    row['data'],
                    row['vector']
                ))
            
            self.logger.info(f"成功存储 {len(df)} 条记录")
            
        except Exception as e:
            self.logger.error(f"数据存储失败: {str(e)}", exc_info=True)
            raise 

    def remove_by_paths(self, file_paths: List[str]) -> int:
        """删除指定文件路径的所有记录
        
        Returns:
            int: 删除的记录数
        """
        try:
            paths_str = ", ".join([f"'{p}'" for p in file_paths])
            result = self.db.execute(f"""
                DELETE FROM unified_data 
                WHERE _file_path IN ({paths_str})
                RETURNING COUNT(*)
            """).fetchone()
            
            return result[0] if result else 0
            
        except Exception as e:
            self.logger.error(f"删除记录失败: {str(e)}")
            raise 