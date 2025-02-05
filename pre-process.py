# %% [markdown]
"""
# 数据预处理脚本
此脚本用于扫描用户指定的一个或多个文件目录，解析文件内容，进行向量化，并将结果存储到统一的数据库表中。
"""

# %% [1. 环境准备]
import os
import json
import magic
import xmltodict
import numpy as np
from pathlib import Path
from datetime import datetime
import pandas as pd
import duckdb
from sentence_transformers import SentenceTransformer
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# %% [2. 智能路径扫描]
def smart_scanner(source, max_depth=3):
    """支持多路径和深度控制的扫描器"""
    logger.info(f"开始扫描路径: {source}")
    found = []
    for path in [source] if isinstance(source, (str, Path)) else source:
        path = Path(path)
        if path.is_file():
            found.append(path)
            logger.debug(f"添加文件: {path}")
        elif path.is_dir():
            logger.info(f"扫描目录: {path}")
            for root, dirs, files in os.walk(path):
                depth = len(Path(root).relative_to(path).parts)
                if depth > max_depth:
                    logger.debug(f"跳过深度 {depth} 的目录: {root}")
                    del dirs[:]
                    continue
                for f in files:
                    if not f.startswith('.'):
                        found.append(Path(root)/f)
                        logger.debug(f"添加文件: {f}")
    
    logger.info(f"扫描完成，共找到 {len(found)} 个文件")
    return sorted(found)

# %% [3. 文件解析引擎]
class FileParser:
    def __init__(self):
        logger.info("初始化文件解析器")
        logger.info("加载文本向量化模型...")
        self.text_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        logger.info("文本向量化模型加载完成")
    
    def parse(self, file_path):
        """统一的文件解析入口"""
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()
        
        try:
            logger.info(f"开始解析文件: {file_path}")
            logger.debug(f"文件类型: {suffix}")
            
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
            
            logger.info(f"成功解析记录数: {len(records)}")

            # 处理每条记录
            processed_records = []
            for idx, record in enumerate(records, 1):
                logger.info(f"处理第 {idx}/{len(records)} 条记录")
                start_time = datetime.now()
                
                record_data = base_metadata.copy()
                record_data['_sub_id'] = idx - 1
                record_data['_record_id'] = f"{record_data['_record_id']}_{idx-1}"
                
                # 扁平化记录
                logger.debug(f"扁平化记录 {idx}")
                flat_data = self._flatten_record(record)
                record_data.update(flat_data)
                
                # 生成向量
                logger.info(f"为记录 {idx} 生成向量表示")
                vector = self._generate_vector(flat_data)
                if vector:
                    record_data['vector'] = vector
                    logger.debug(f"记录 {idx} 向量维度: {len(vector)}")
                
                process_time = (datetime.now() - start_time).total_seconds()
                logger.info(f"记录 {idx} 处理完成，耗时: {process_time:.2f}秒")
                
                processed_records.append(record_data)

            logger.info(f"文件 {file_path.name} 所有记录处理完成")
            return pd.DataFrame(processed_records)

        except Exception as e:
            logger.error(f"解析文件 {file_path} 时出错: {str(e)}", exc_info=True)
            return None

    def _parse_file(self, file_path, suffix):
        """根据文件类型选择解析方法"""
        logger.info(f"开始解析文件: {file_path}")
        logger.info(f"文件类型: {suffix}")
        
        try:
            if suffix == '.json':
                logger.info("使用JSON解析器")
                return self._parse_json(file_path)
            elif suffix in ['.csv', '.tsv']:
                logger.info("使用CSV解析器")
                return self._parse_csv(file_path)
            elif suffix in ['.txt', '.md', '.log']:
                logger.info("使用文本解析器")
                return self._parse_text(file_path)
            elif suffix in ['.xlsx', '.xls']:
                logger.info("使用Excel解析器")
                return self._parse_excel(file_path)
            elif suffix in ['.xml']:
                logger.info("使用XML解析器")
                return self._parse_xml(file_path)
            else:
                logger.info("使用二进制文件解析器")
                return self._parse_binary(file_path)
        except Exception as e:
            logger.error(f"解析失败: {str(e)}", exc_info=True)
            raise
    def _parse_json(self, path):
        """JSON文件解析"""
        logger.info(f"读取JSON文件: {path}")
        try:
            with path.open('r', encoding='utf-8') as f:
                data = json.load(f)
            result = data if isinstance(data, list) else [data]
            logger.info(f"JSON解析完成，获取 {len(result)} 条记录")
            return result
        except Exception as e:
            logger.error(f"JSON解析错误: {str(e)}")
            raise

    def _parse_csv(self, path):
        """CSV文件解析"""
        logger.info(f"读取CSV文件: {path}")
        try:
            df = pd.read_csv(path)
            result = df.to_dict('records')
            logger.info(f"CSV解析完成，获取 {len(result)} 行数据")
            return result
        except Exception as e:
            logger.error(f"CSV解析错误: {str(e)}")
            raise

    def _parse_text(self, path):
        """文本文件解析"""
        logger.info(f"读取文本文件: {path}")
        try:
            content = path.read_text(encoding='utf-8')
            lines = content.splitlines()
            result = [{
                'content': content,
                'char_count': len(content),
                'line_count': len(lines)
            }]
            logger.info(f"文本解析完成，共 {len(lines)} 行，{len(content)} 字符")
            return result
        except Exception as e:
            logger.error(f"文本解析错误: {str(e)}")
            raise

    def _parse_excel(self, path):
        """Excel文件解析"""
        logger.info(f"读取Excel文件: {path}")
        try:
            df = pd.read_excel(path)
            result = df.to_dict('records')
            logger.info(f"Excel解析完成，获取 {len(result)} 行数据")
            return result
        except Exception as e:
            logger.error(f"Excel解析错误: {str(e)}")
            raise

    def _parse_xml(self, path):
        """XML文件解析"""
        logger.info(f"读取XML文件: {path}")
        try:
            with path.open('r', encoding='utf-8') as f:
                data = xmltodict.parse(f.read())
            logger.info("XML解析完成")
            return [data]
        except Exception as e:
            logger.error(f"XML解析错误: {str(e)}")
            raise

    def _parse_binary(self, path):
        """二进制文件解析"""
        logger.info(f"读取二进制文件: {path}")
        try:
            mime = magic.Magic(mime=True)
            file_stat = path.stat()
            result = [{
                'size': file_stat.st_size,
                'mime_type': mime.from_file(str(path)),
                'modified_time': datetime.fromtimestamp(file_stat.st_mtime)
            }]
            logger.info(f"二进制文件解析完成，大小: {file_stat.st_size} 字节")
            return result
        except Exception as e:
            logger.error(f"二进制文件解析错误: {str(e)}")
            raise

    def _flatten_record(self, data):
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

    def _generate_vector(self, data):
        """生成向量表示"""
        logger.info("开始生成向量表示")
        text_parts = []
        
        # 提取所有文本内容
        for k, v in data.items():
            if isinstance(v, str):
                text_parts.append(f"{k}: {v}")
            elif isinstance(v, (int, float, bool)):
                text_parts.append(f"{k}: {str(v)}")
        
        # 组合文本并生成向量
        text = " ".join(text_parts)[:512]  # 限制长度
        logger.debug(f"生成的文本长度: {len(text)} 字符")
        
        try:
            vector = self.text_model.encode(text)
            logger.info(f"向量生成完成，维度: {len(vector)}")
            return vector.tolist()
        except Exception as e:
            logger.error(f"向量化失败: {str(e)}")
            return None

# %% [4. 存储系统]
class StorageSystem:
    def __init__(self, db_path="unified_storage.duckdb"):
        self.db_path = db_path
        logger.info(f"初始化存储系统，数据库路径: {self.db_path}")
        self.db = duckdb.connect(self.db_path)
        self.init_storage()
    
    def init_storage(self):
        """初始化存储表"""
        logger.info("初始化数据库表结构")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS unified_data (
                _record_id VARCHAR PRIMARY KEY,  -- 唯一标识符
                _file_path VARCHAR,             -- 文件路径
                _file_name VARCHAR,             -- 文件名
                _file_type VARCHAR,             -- 文件类型
                _processed_at TIMESTAMP,        -- 处理时间
                _sub_id INTEGER,                -- 子记录ID
                data JSON,                      -- 原始数据
                vector DOUBLE[]                 -- 向量表示
            )
        """)
        logger.info("存储表初始化完成")
    
    def save(self, df):
        """统一的数据存储方法"""
        if df is None or df.empty:
            logger.warning("收到空数据，跳过存储")
            return

        start_time = datetime.now()
        logger.info(f"准备存储 {len(df)} 条记录到数据库")
        
        try:
            # 提取核心元数据字段
            logger.info("处理元数据字段")
            meta_columns = ['_record_id', '_file_path', '_file_name', 
                          '_file_type', '_processed_at', '_sub_id']
            
            # 处理向量数据
            logger.info("序列化向量数据")
            vector_data = df['vector'].apply(json.dumps)
            
            # 将其他列打包为JSON
            logger.info("打包其他字段为JSON格式")
            other_columns = [col for col in df.columns 
                           if col not in meta_columns + ['vector']]
            logger.debug(f"额外字段数量: {len(other_columns)}")
            
            df['data'] = df[other_columns].apply(lambda x: json.dumps(x.dropna().to_dict()), axis=1)
            
            # 准备存储数据
            logger.info("准备最终存储数据")
            df_to_save = df[meta_columns].copy()
            df_to_save['data'] = df['data']
            df_to_save['vector'] = vector_data
            
            # 存储数据
            logger.info("开始写入数据库")
            self.db.register('temp_view', df_to_save)
            
            # 记录插入前的记录数
            pre_count = self.db.execute("SELECT COUNT(*) FROM unified_data").fetchone()[0]
            logger.info(f"当前数据库记录数: {pre_count}")
            
            # 执行插入操作
            self.db.execute("""
                INSERT INTO unified_data 
                SELECT * FROM temp_view
                ON CONFLICT (_record_id) DO UPDATE 
                SET data = EXCLUDED.data,
                    vector = EXCLUDED.vector
            """)
            
            # 记录插入后的记录数
            post_count = self.db.execute("SELECT COUNT(*) FROM unified_data").fetchone()[0]
            new_records = post_count - pre_count
            
            self.db.unregister('temp_view')
            
            # 计算处理时间
            process_time = (datetime.now() - start_time).total_seconds()
            
            # 输出详细的存储统计
            logger.info("="*40)
            logger.info("数据存储完成")
            logger.info(f"总处理时间: {process_time:.2f}秒")
            logger.info(f"新增记录数: {new_records}")
            logger.info(f"当前总记录数: {post_count}")
            logger.info("="*40)

        except Exception as e:
            logger.error(f"数据存储过程出错: {str(e)}", exc_info=True)
            raise

# %% [5. 主流程]
def main():
    logger.info("="*50)
    logger.info("开始数据预处理任务")
    logger.info("="*50)
    
    start_time = datetime.now()
    
    # 指定输入目录
    input_dirs = [r"D:\github\Helixlife\datamind\source\test_data"]
    input_dirs = [Path(d.strip()) for d in input_dirs]
    logger.info(f"输入目录: {input_dirs}")
    
    # 扫描文件
    logger.info("-"*50)
    logger.info("开始扫描文件...")
    scanned_files = smart_scanner(input_dirs)
    logger.info(f"扫描完成，共发现 {len(scanned_files)} 个文件")
    
    # 初始化解析器和存储系统
    logger.info("-"*50)
    logger.info("初始化解析器和存储系统...")
    parser = FileParser()
    storage = StorageSystem()
    
    # 处理文件
    logger.info("-"*50)
    logger.info("开始处理文件...")
    total_files = len(scanned_files)
    successful_files = 0
    failed_files = 0
    total_records = 0
    
    for i, file_path in enumerate(scanned_files, 1):
        logger.info("="*50)
        logger.info(f"处理文件 [{i}/{total_files}]: {file_path}")
        file_start_time = datetime.now()
        
        try:
            df = parser.parse(file_path)
            if df is not None:
                records_count = len(df)
                logger.info(f"文件解析成功，获得 {records_count} 条记录")
                
                logger.info("开始存储数据...")
                storage.save(df)
                
                successful_files += 1
                total_records += records_count
                
                file_process_time = (datetime.now() - file_start_time).total_seconds()
                logger.info(f"文件处理成功，耗时: {file_process_time:.2f}秒")
            else:
                failed_files += 1
                logger.warning(f"文件处理失败: {file_path}")
        except Exception as e:
            failed_files += 1
            logger.error(f"文件处理异常: {file_path}", exc_info=True)
    
    # 输出最终统计信息
    total_time = (datetime.now() - start_time).total_seconds()
    
    logger.info("="*50)
    logger.info("数据预处理任务完成")
    logger.info(f"总耗时: {total_time:.2f}秒")
    logger.info(f"总文件数: {total_files}")
    logger.info(f"成功处理: {successful_files}")
    logger.info(f"处理失败: {failed_files}")
    logger.info(f"总记录数: {total_records}")
    logger.info(f"平均处理时间: {total_time/total_files:.2f}秒/文件")
    logger.info("="*50)

# %% [6. 运行主流程]
if __name__ == "__main__":
    main()