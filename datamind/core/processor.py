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
import random
import uuid
import numpy as np
from docling.document_converter import DocumentConverter
from ..core.search import SearchEngine

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
        self.db = duckdb.connect(db_path)
        self.init_storage()
        self.parser = FileParser()
        self.search_engine = SearchEngine(db_path)  # 创建SearchEngine实例
        self.storage = StorageSystem(self.db, search_engine=self.search_engine)  # 传入SearchEngine实例
        self.file_cache = FileCache()

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
        
        # 添加文档分块配置
        self.chunk_size = 1000  # 文档分块大小
        self.chunk_overlap = 200  # 块之间的重叠大小

    def parse(self, file_path: Path) -> Optional[pd.DataFrame]:
        """统一的文件解析入口"""
        suffix = file_path.suffix.lower()
        
        try:
            self.logger.info(f"开始解析文件: {file_path}")
            
            # 解析文件内容
            records = self._parse_file(file_path, suffix)
            if not isinstance(records, list):
                records = [records]
            
            # 处理每条记录
            processed_records = []
            for idx, record in enumerate(records, 1):
                # 基础元数据
                record_data = {
                    '_file_path': str(file_path),
                    '_file_name': file_path.name,
                    '_file_type': suffix.lstrip('.'),
                    '_processed_at': pd.Timestamp.now(),
                    '_record_id': str(uuid.uuid4()),
                    '_sub_id': idx - 1
                }
                
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
        elif suffix == '.md':
            return self._parse_markdown(path)
        elif suffix in ['.txt', '.log']:
            return self._parse_text(path)
        elif suffix in ['.xlsx', '.xls']:
            return self._parse_excel(path)
        elif suffix in ['.xml']:
            return self._parse_xml(path)
        elif suffix in ['.pdf']:
            return self._parse_pdf(path)
        elif suffix in ['.doc', '.docx']:
            return self._parse_word(path)
        else:
            return self._parse_binary(path)
            
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
        
        # 获取文档的基本信息
        base_info = {
            'char_count': len(content),
            'line_count': len(lines)
        }
        
        # 分块处理
        chunks = self._split_text_into_chunks(content)
        
        # 为每个块创建记录
        records = []
        for i, chunk in enumerate(chunks):
            record = base_info.copy()
            record.update({
                'chunk_id': i,
                'total_chunks': len(chunks),
                'content': chunk,
                'chunk_char_count': len(chunk)
            })
            
            records.append(record)
        
        return records
    
    def _parse_markdown(self, path: Path) -> List[Dict]:
        """Markdown文件解析"""
        content = path.read_text(encoding='utf-8')
        
        # 提取标题结构
        headers = []
        current_level = 0
        current_header = ""
        
        for line in content.splitlines():
            if line.startswith('#'):
                level = len(line.split()[0])  # 计算#的数量
                header = line.lstrip('#').strip()
                headers.append({
                    'level': level,
                    'text': header
                })
                current_level = level
                current_header = header
        
        # 分块处理
        chunks = self._split_text_into_chunks(content)
        
        # 为每个块创建记录
        records = []
        for i, chunk in enumerate(chunks):
            record = {
                'chunk_id': i,
                'total_chunks': len(chunks),
                'content': chunk,
                'chunk_char_count': len(chunk),
                'document_structure': headers
            }
            records.append(record)
            
        return records
        
    def _parse_excel(self, path: Path) -> List[Dict]:
        """Excel文件解析"""
        df = pd.read_excel(path)
        return df.to_dict('records')
        
    def _parse_xml(self, path: Path) -> List[Dict]:
        """XML文件解析"""
        with path.open('r', encoding='utf-8') as f:
            data = xmltodict.parse(f.read())
        return [data]
        
    def _parse_pdf(self, path: Path) -> List[Dict]:
        """PDF文件解析"""
        try:
            converter = DocumentConverter()
            result = converter.convert(str(path))
            content = result.document.export_to_markdown()
            
            # 获取文档的基本信息
            base_info = {
                'char_count': len(content),
                'content_type': 'pdf',
                'original_content': content
            }
            
            # 分块处理
            chunks = self._split_text_into_chunks(content)
            
            # 为每个块创建记录
            records = []
            for i, chunk in enumerate(chunks):
                record = base_info.copy()
                record.update({
                    'chunk_id': i,
                    'total_chunks': len(chunks),
                    'content': chunk,
                    'chunk_char_count': len(chunk)
                })
                records.append(record)
            
            return records
            
        except Exception as e:
            self.logger.error(f"PDF解析失败: {str(e)}")
            return [{'error': f"PDF解析失败: {str(e)}"}]

    def _parse_word(self, path: Path) -> List[Dict]:
        """Word文档解析"""
        try:
            converter = DocumentConverter()
            result = converter.convert(str(path))
            content = result.document.export_to_markdown()
            
            # 获取文档的基本信息
            base_info = {
                'char_count': len(content),
                'content_type': 'word',
                'original_content': content
            }
            
            # 分块处理
            chunks = self._split_text_into_chunks(content)
            
            # 为每个块创建记录
            records = []
            for i, chunk in enumerate(chunks):
                record = base_info.copy()
                record.update({
                    'chunk_id': i,
                    'total_chunks': len(chunks),
                    'content': chunk,
                    'chunk_char_count': len(chunk)
                })
                records.append(record)
            
            return records
            
        except Exception as e:
            self.logger.error(f"Word文档解析失败: {str(e)}")
            return [{'error': f"Word文档解析失败: {str(e)}"}]
        
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

        # 将数据扁平化
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

    def _split_text_into_chunks(self, text: str) -> List[str]:
        """将文本分割成重叠的块，使用迭代器方式处理以减少内存使用
        
        Args:
            text: 输入文本
            
        Returns:
            List[str]: 文本块列表
        """
        chunks = []
        text_len = len(text)
        
        # 动态调整块大小，根据文本总长度
        if text_len > 10_000_000:  # 10MB
            self.chunk_size = 5000
            self.chunk_overlap = 500
        elif text_len > 1_000_000:  # 1MB
            self.chunk_size = 2000
            self.chunk_overlap = 400
        
        # 使用生成器逐步读取文本
        def text_generator():
            start = 0
            while start < text_len:
                # 计算当前块的结束位置
                end = min(start + self.chunk_size, text_len)
                
                # 如果不是最后一块，在句子边界处截断
                if end < text_len:
                    # 在chunk_size范围内找最后一个句子结束标记
                    found_boundary = False
                    search_window = 200  # 限制向前查找的窗口大小
                    
                    for boundary_pos in range(end, max(start, end - search_window), -1):
                        if text[boundary_pos-1:boundary_pos+1] in ['. ', '\n', '。', '！', '？']:
                            end = boundary_pos
                            found_boundary = True
                            break
                    
                    # 如果找不到合适的分割点，就强制分割
                    if not found_boundary:
                        end = min(start + self.chunk_size, text_len)
                
                # 提取当前块
                current_chunk = text[start:end].strip()
                if current_chunk:  # 只返回非空块
                    yield current_chunk
                
                # 更新起始位置，确保有重叠但不会产生太小的块
                next_start = end - self.chunk_overlap
                if next_start <= start:  # 防止死循环
                    start = end
                else:
                    start = next_start
        
        # 使用生成器逐步构建chunks列表
        for chunk in text_generator():
            chunks.append(chunk)
            # 添加内存使用检查
            if len(chunks) * self.chunk_size > 100_000_000:  # 100MB警戒线
                self.logger.warning("文本块数量过多，可能导致内存问题")
                break
        
        return chunks

class StorageSystem:
    """存储系统"""
    
    def __init__(self, db=None, search_engine=None):
        self.logger = logging.getLogger(__name__)
        self.db = db
        self.search_engine = search_engine
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
            # 开始事务
            self.db.execute("BEGIN TRANSACTION")
            
            try:
                # 先计数要删除的记录
                file_paths = df['_file_path'].unique()
                paths_str = ", ".join([f"'{p}'" for p in file_paths])
                count_result = self.db.execute(f"""
                    SELECT COUNT(*) 
                    FROM unified_data 
                    WHERE _file_path IN ({paths_str})
                """).fetchone()
                
                old_count = count_result[0] if count_result else 0
                
                # 删除同一文件的所有旧记录
                if old_count > 0:
                    self.db.execute(f"""
                        DELETE FROM unified_data 
                        WHERE _file_path IN ({paths_str})
                    """)
                    self.logger.info(f"已删除 {old_count} 条旧记录")
                
                # 准备批量插入数据
                values = []
                for idx, row in df.iterrows():
                    # 处理非meta列为JSON
                    meta_columns = ['_record_id', '_file_path', '_file_name', 
                                  '_file_type', '_processed_at', '_sub_id', 'vector']
                    data_dict = {col: row[col] for col in df.columns 
                                if col not in meta_columns and pd.notna(row[col])}
                    
                    # 修改向量处理逻辑
                    vector_data = None
                    if 'vector' in row and isinstance(row['vector'], (list, np.ndarray)) and len(row['vector']) > 0:
                        vector_data = json.dumps(row['vector'].tolist() if isinstance(row['vector'], np.ndarray) else row['vector'])
                    
                    values.append((
                        row['_record_id'],
                        row['_file_path'],
                        row['_file_name'],
                        row['_file_type'],
                        row['_processed_at'],
                        row['_sub_id'],
                        json.dumps(data_dict, ensure_ascii=False),
                        vector_data
                    ))
                
                # 批量插入
                self.db.executemany("""
                    INSERT INTO unified_data 
                    (_record_id, _file_path, _file_name, _file_type, 
                     _processed_at, _sub_id, data, vector)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, values)
                
                # 提交事务
                self.db.execute("COMMIT")
                self.logger.info(f"成功批量存储 {len(df)} 条记录")
                
            except Exception as e:
                # 回滚事务
                self.db.execute("ROLLBACK")
                raise e
            
        except Exception as e:
            self.logger.error(f"数据存储失败: {str(e)}", exc_info=True)
            raise 

    def remove_by_paths(self, file_paths: List[str]) -> int:
        """删除指定文件路径的所有记录
        
        Returns:
            int: 删除的记录数
        """
        try:
            # 先获取要删除的记录ID
            paths_str = ", ".join([f"'{p}'" for p in file_paths])
            record_ids = self.db.execute(f"""
                SELECT _record_id 
                FROM unified_data 
                WHERE _file_path IN ({paths_str})
            """).fetchall()
            record_ids = [r[0] for r in record_ids]
            
            # 删除数据库记录
            count = len(record_ids)
            if count > 0:
                self.db.execute(f"""
                    DELETE FROM unified_data 
                    WHERE _file_path IN ({paths_str})
                """)
                
                # 同步删除向量数据
                if self.search_engine:
                    self.search_engine.remove_records(record_ids)
                
                self.logger.info(f"已删除 {count} 条记录")
            
            return count
            
        except Exception as e:
            self.logger.error(f"删除记录失败: {str(e)}")
            raise 