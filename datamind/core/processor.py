import os
import json
import magic
import xmltodict
import pandas as pd
import duckdb
from pathlib import Path
from datetime import datetime
import logging
from typing import List, Dict, Optional
from sentence_transformers import SentenceTransformer
from ..config.settings import DEFAULT_MODEL, DEFAULT_DB_PATH
from ..utils.common import download_model

class DataProcessor:
    """数据预处理器"""
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.logger = logging.getLogger(__name__)
        self.db_path = db_path
        self.parser = FileParser()
        self.storage = StorageSystem(db_path)
        
    def process_directory(self, input_dirs: List[str], max_depth: int = 3) -> Dict:
        """处理指定目录
        
        Args:
            input_dirs: 输入目录列表
            max_depth: 最大扫描深度
            
        Returns:
            Dict: 处理结果统计
        """
        start_time = datetime.now()
        self.logger.info("="*50)
        self.logger.info("开始数据预处理任务")
        
        try:
            # 扫描文件
            scanned_files = self._scan_directories(input_dirs, max_depth)
            self.logger.info(f"扫描完成，共发现 {len(scanned_files)} 个文件")
            
            # 处理文件
            stats = self._process_files(scanned_files)
            
            # 计算总耗时
            total_time = (datetime.now() - start_time).total_seconds()
            stats['total_time'] = total_time
            stats['avg_time_per_file'] = total_time / len(scanned_files) if scanned_files else 0
            
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
        
        for i, file_path in enumerate(files, 1):
            self.logger.info(f"处理文件 [{i}/{stats['total_files']}]: {file_path}")
            file_start_time = datetime.now()
            
            try:
                df = self.parser.parse(file_path)
                if df is not None and not df.empty:
                    records_count = len(df)
                    self.logger.info(f"文件解析成功，获得 {records_count} 条记录")
                    
                    self.storage.save(df)
                    
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
                
        return stats

class FileParser:
    """文件解析器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.text_model = self._init_model()
        
    def _init_model(self) -> Optional[SentenceTransformer]:
        """初始化模型"""
        root_dir = Path.cwd()
        model_path = root_dir / 'model_cache' / DEFAULT_MODEL
        
        try:
            if not model_path.exists() or not list(model_path.glob('*')):
                self.logger.info("模型文件不存在，开始下载...")
                if not download_model():
                    raise RuntimeError("模型下载失败")
            
            self.logger.info(f"从 {model_path} 加载模型...")
            model = SentenceTransformer(str(model_path))
            self.logger.info("模型加载成功")
            return model
        except Exception as e:
            self.logger.error(f"模型加载失败: {str(e)}")
            return None
            
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