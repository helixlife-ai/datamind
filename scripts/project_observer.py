import os
import json
import ast
from typing import Dict, List, Optional
from pathlib import Path
import sys


class ProjectObserver:
    """观察项目目录，提取信息并保存到目标目录"""
    def __init__(self, source_dir: str, target_dir: str, 
                 exclude_dirs: Optional[List[str]] = None, 
                 exclude_files: Optional[List[str]] = None, 
                 key_files: Optional[List[str]] = None):
        self.source_dir = source_dir  # 源目录
        self.target_dir = target_dir  # 目标目录
        self.exclude_dirs = exclude_dirs or ["__pycache__","node_modules",".git"]  # 要排除的文件夹
        self.exclude_files = exclude_files or [".DS_Store", "Thumbs.db",".env"]  # 要排除的文件
        self.key_files = key_files or ["README.md", "config.yaml"]  # 默认关键文件列表

        # 确保目标目录存在
        os.makedirs(self.target_dir, exist_ok=True)

    def observe_project(self) -> Dict:
        """
        提取项目的观察信息。
        :return: 提取的信息字典
        """
        try:
            project_info = {
                "directory_structure": self._get_directory_structure(),
                "key_files": self._extract_key_files(),
                "meta": self._get_project_meta(),
                "log_summary": self._summarize_logs(),
                "code_analysis": self._analyze_code()
            }
            return project_info
        except Exception as e:
            print(f"Failed to observe project: {e}")
            return {}

    def _get_directory_structure(self) -> List[str]:
        """
        获取项目目录的结构。
        :return: 目录结构列表
        """
        structure = []
        for root, dirs, files in os.walk(self.source_dir):
            # 过滤掉排除的文件夹
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            for name in files:
                # 过滤掉排除的文件
                if name not in self.exclude_files:
                    structure.append(os.path.relpath(os.path.join(root, name), self.source_dir))
        return structure

    def _extract_key_files(self) -> Dict[str, Optional[str]]:
        """
        提取关键文件的内容。
        :return: 关键文件内容字典
        """
        extracted_files = {}
        for key_file in self.key_files:
            file_path = os.path.join(self.source_dir, key_file)
            if os.path.exists(file_path) and key_file not in self.exclude_files:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        extracted_files[key_file] = f.read()
                except Exception as e:
                    print(f"Failed to read key file {key_file}: {e}")
                    extracted_files[key_file] = None
            else:
                extracted_files[key_file] = None
        return extracted_files

    def _get_project_meta(self) -> Dict:
        """
        获取项目的元信息（如文件数量、总大小等）。
        :return: 元信息字典
        """
        total_size = 0
        file_count = 0
        dir_count = 0
        for root, dirs, files in os.walk(self.source_dir):
            # 过滤掉排除的文件夹
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            dir_count += len(dirs)
            for name in files:
                # 过滤掉排除的文件
                if name not in self.exclude_files:
                    file_count += 1
                    file_path = os.path.join(root, name)
                    total_size += os.path.getsize(file_path)
        return {
            "file_count": file_count,
            "dir_count": dir_count,
            "total_size": total_size
        }

    def _summarize_logs(self) -> List[str]:
        """
        提取日志文件的摘要。
        :return: 日志摘要列表
        """
        log_dir = os.path.join(self.source_dir, "logs")
        summaries = []
        if os.path.exists(log_dir) and "logs" not in self.exclude_dirs:
            for log_file in os.listdir(log_dir):
                if log_file not in self.exclude_files:
                    log_path = os.path.join(log_dir, log_file)
                    if os.path.isfile(log_path):
                        try:
                            with open(log_path, "r", encoding="utf-8") as f:
                                lines = f.readlines()
                                summaries.append(f"{log_file}: {lines[:5]}")  # 提取前 5 行作为摘要
                        except Exception as e:
                            print(f"Failed to read log file {log_file}: {e}")
        return summaries

    def _analyze_code(self) -> Dict:
        """
        分析代码文件，进行静态分析、文档分析和依赖分析。
        :return: 代码分析结果字典
        """
        code_analysis = {
            "modules": [],
            "classes": {},
            "functions": {},
            "dependencies": self._analyze_dependencies(),
            "readme_summary": self._analyze_readme()
        }

        for root, dirs, files in os.walk(self.source_dir):
            # 过滤掉排除的文件夹
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            for file in files:
                # 过滤掉排除的文件
                if file not in self.exclude_files and file.endswith(".py"):  # 仅分析 Python 文件
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            code = f.read()
                            self._analyze_python_file(file_path, code, code_analysis)
                    except Exception as e:
                        print(f"Failed to analyze Python file {file}: {e}")

        return code_analysis

    def _analyze_python_file(self, file_path: str, code: str, analysis: Dict):
        """
        使用 AST 模块对 Python 文件进行静态分析。
        :param file_path: 文件路径
        :param code: 文件内容
        :param analysis: 分析结果字典
        """
        try:
            tree = ast.parse(code, filename=file_path)
            module_name = os.path.relpath(file_path, self.source_dir).replace(os.sep, ".").rstrip(".py")
            analysis["modules"].append(module_name)

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_name = node.name
                    methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                    analysis["classes"][class_name] = {"methods": methods}
                elif isinstance(node, ast.FunctionDef):
                    func_name = node.name
                    args = [arg.arg for arg in node.args.args]
                    docstring = ast.get_docstring(node)
                    analysis["functions"][func_name] = {
                        "args": args,
                        "doc": docstring or "No documentation available."
                    }
        except Exception as e:
            print(f"Failed to parse Python file {file_path}: {e}")

    def _analyze_readme(self) -> str:
        """
        分析 README 文件，提取项目的功能描述。
        :return: README 文件的摘要
        """
        readme_path = os.path.join(self.source_dir, "README.md")
        if os.path.exists(readme_path):
            try:
                with open(readme_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    # 提取前几行作为摘要
                    return "\n".join(content.splitlines()[:10])
            except Exception as e:
                print(f"Failed to read README file: {e}")
        return "No README file found."

    def _analyze_dependencies(self) -> List[str]:
        """
        分析项目的依赖项。
        :return: 依赖项列表
        """
        dependencies = []
        requirements_path = os.path.join(self.source_dir, "requirements.txt")
        pyproject_path = os.path.join(self.source_dir, "pyproject.toml")

        if os.path.exists(requirements_path):
            try:
                with open(requirements_path, "r", encoding="utf-8") as f:
                    dependencies.extend([line.strip() for line in f if line.strip() and not line.startswith("#")])
            except Exception as e:
                print(f"Failed to read requirements.txt: {e}")

        if os.path.exists(pyproject_path):
            try:
                with open(pyproject_path, "r", encoding="utf-8") as f:
                    # 简单解析 pyproject.toml 的依赖部分
                    for line in f:
                        if "dependencies" in line or "requires" in line:
                            dependencies.append(line.strip())
            except Exception as e:
                print(f"Failed to read pyproject.toml: {e}")

        return dependencies

    def save_observation(self, observation: Dict):
        """
        保存观察信息到目标目录。
        :param observation: 观察信息字典
        """
        try:
            file_path = os.path.join(self.target_dir, "project_observation.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(observation, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save observation: {e}")


# 执行样例
if __name__ == "__main__":
    # 获取脚本目录和项目根目录
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    # 添加项目根目录到Python路径
    sys.path.insert(0, str(project_root))
    
    # 创建工作目录
    work_dir = project_root / "work_dir"
    work_dir.mkdir(exist_ok=True, parents=True)
    
    # 创建观察结果目录
    observations_dir = work_dir / "observations"
    observations_dir.mkdir(exist_ok=True, parents=True)
    
    # 定义源目录和目标目录
    source_directory = str(project_root)  # 项目根目录作为源目录
    target_directory = str(observations_dir)  # 使用observations子目录作为目标目录
    
    # 定义要排除的目录和文件
    exclude_dirs = ["__pycache__", "node_modules", ".git", ".venv", "work_dir"]
    exclude_files = [".DS_Store", "Thumbs.db", ".env", ".gitignore"]
    
    # 定义关键文件
    key_files = ["README.md", "requirements.txt", "pyproject.toml", "config.yaml"]
    
    print(f"源目录: {source_directory}")
    print(f"目标目录: {target_directory}")
    
    # 创建ProjectObserver实例
    observer = ProjectObserver(
        source_dir=source_directory,
        target_dir=target_directory,
        exclude_dirs=exclude_dirs,
        exclude_files=exclude_files,
        key_files=key_files
    )
    
    # 执行项目观察
    print("开始观察项目...")
    project_info = observer.observe_project()
    
    # 保存观察结果
    observer.save_observation(project_info)
    print(f"项目观察完成，结果已保存到 {os.path.join(target_directory, 'project_observation.json')}")
    
    # 显示一些基本信息
    print("\n项目基本信息:")
    print(f"文件总数: {project_info['meta']['file_count']}")
    print(f"目录总数: {project_info['meta']['dir_count']}")
    print(f"项目总大小: {project_info['meta']['total_size'] / 1024:.2f} KB")
    
    # 显示发现的模块数量
    if 'code_analysis' in project_info and 'modules' in project_info['code_analysis']:
        print(f"发现的Python模块数量: {len(project_info['code_analysis']['modules'])}")