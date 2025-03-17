#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
将指定文件夹中的HTML文件部署到GitHub仓库并生成GitHub Pages
"""

import os
import sys
import shutil
import subprocess
import argparse
from datetime import datetime
from dotenv import load_dotenv
import time
import requests
import json

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='将Artifacts部署到GitHub Pages')
    parser.add_argument('source_dir', nargs='?', default='work_dir/gh_page', help='包含Artifacts的源目录')
    parser.add_argument('--repo', default='https://github.com/imjszhang/datamind-gallery.git', help='GitHub仓库URL')
    parser.add_argument('--branch', default='gh-pages', help='GitHub Pages分支名称（默认：gh-pages）')
    parser.add_argument('--commit-message', default=None, help='自定义提交信息')
    parser.add_argument('--temp-dir', default='work_dir/temp_deploy', help='临时目录路径（默认：work_dir/temp_deploy）')
    parser.add_argument('--token', help='GitHub个人访问令牌(PAT)，如不提供将尝试从.env文件读取GITHUB_TOKEN')
    parser.add_argument('--env-file', default='.env', help='.env文件路径（默认：.env）')
    return parser.parse_args()

def run_command(command, cwd=None):
    """执行shell命令并打印输出"""
    # 隐藏包含令牌的命令
    safe_command = command.copy()
    
    # 更全面地检查和隐藏所有可能包含token的命令
    for i, arg in enumerate(safe_command):
        if isinstance(arg, str):
            # 检查URL中的token
            if '@github.com' in arg:
                parts = arg.split('@')
                protocol_token = parts[0].split('://')
                if len(protocol_token) > 1:
                    safe_command[i] = f"{protocol_token[0]}://****@{parts[1]}"
            # 检查Authorization头中的token
            elif 'token ' in arg:
                safe_command[i] = arg.replace(arg.split('token ')[1], '****')
    
    print(f"执行: {' '.join(safe_command)}")
    
    # 添加超时参数，防止命令长时间挂起
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding='utf-8', timeout=60)
        if result.returncode != 0:
            # 确保错误输出中也不会暴露token
            safe_stderr = result.stderr
            if token and token in safe_stderr:
                safe_stderr = safe_stderr.replace(token, '****')
            print(f"错误: {safe_stderr}")
            # 不立即退出，而是抛出异常，让调用者处理
            raise subprocess.CalledProcessError(result.returncode, command, result.stdout, result.stderr)
        
        # 确保返回的输出中也不会暴露token
        safe_stdout = result.stdout
        if token and token in safe_stdout:
            safe_stdout = safe_stdout.replace(token, '****')
        return safe_stdout.strip()
    except subprocess.TimeoutExpired:
        print(f"错误: 命令执行超时")
        raise

def create_github_repo(repo_name, token):
    """使用GitHub API创建新仓库"""
    # 从repo_url中提取仓库名称和用户名
    parts = repo_name.split('/')
    if len(parts) >= 2:
        user_name = parts[-2]
        repo_name = parts[-1].replace('.git', '')
    else:
        repo_name = repo_name.split('/')[-1].replace('.git', '')
    
    # GitHub API端点
    api_url = "https://api.github.com/user/repos"
    
    # 设置请求头
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # 设置仓库数据
    data = {
        "name": repo_name,
        "description": "GitHub Pages Repository",
        "private": False,
        "has_issues": True,
        "has_projects": True,
        "has_wiki": True
    }
    
    try:
        # 发送POST请求创建仓库
        response = requests.post(api_url, headers=headers, data=json.dumps(data))
        
        # 检查响应
        if response.status_code == 201:
            print(f"成功创建仓库: {repo_name}")
            return True
        else:
            # 确保错误信息中不包含token
            error_info = response.json()
            print(f"创建仓库失败: {response.status_code}")
            print(error_info)
            return False
    except Exception as e:
        # 确保异常信息中不包含token
        error_msg = str(e)
        if token and token in error_msg:
            error_msg = error_msg.replace(token, '****')
        print(f"创建仓库时发生错误: {error_msg}")
        return False

def deploy_to_github(source_dir, repo_url, branch, commit_message, temp_dir, token=None):
    """将源目录中的文件部署到GitHub Pages"""
    # 确保源目录存在
    if not os.path.isdir(source_dir):
        print(f"错误: 源目录 '{source_dir}' 不存在")
        sys.exit(1)
    
    # 确保 work_dir 目录存在（如果临时目录在 work_dir 中）
    if 'work_dir' in temp_dir and not os.path.exists('work_dir'):
        os.makedirs('work_dir', exist_ok=True)
        print(f"创建 work_dir 目录")
    
    # 如果提供了token，修改repo_url以包含token
    original_repo_url = repo_url
    if token and repo_url.startswith('https://'):
        # 将https://github.com/user/repo.git转换为https://token@github.com/user/repo.git
        repo_parts = repo_url.split('://')
        repo_url = f"{repo_parts[0]}://{token}@{repo_parts[1]}"
    
    # 创建临时目录
    if os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
        except PermissionError:
            print(f"警告: 无法删除已存在的临时目录，尝试使用不同的临时目录")
            temp_dir = f"{temp_dir}_{int(time.time())}"
            print(f"使用新的临时目录: {temp_dir}")
    
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        # 验证仓库是否存在
        try:
            # 使用 git ls-remote 检查仓库是否可访问
            run_command(['git', 'ls-remote', repo_url, '--quiet'])
            print("仓库验证成功")
        except subprocess.CalledProcessError:
            print(f"错误: 无法访问仓库 '{original_repo_url}'")
            
            # 检查是否有token，如果有则尝试创建仓库
            if token:
                print("尝试创建新仓库...")
                if create_github_repo(original_repo_url, token):
                    print("仓库创建成功，继续部署流程")
                else:
                    print("无法创建仓库，请检查令牌权限或手动创建仓库")
                    sys.exit(1)
            else:
                print("未提供GitHub令牌，无法自动创建仓库")
                print("请检查仓库URL是否正确，或提供有效的GitHub令牌")
                sys.exit(1)
        
        # 克隆仓库的指定分支（如果存在）
        clone_command = ['git', 'clone', repo_url, '--branch', branch, '--single-branch', temp_dir]
        try:
            run_command(clone_command)
            # 清空临时目录中的所有文件（保留.git目录）
            for item in os.listdir(temp_dir):
                if item != '.git':
                    item_path = os.path.join(temp_dir, item)
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
        except subprocess.CalledProcessError:
            # 如果分支不存在，则创建一个新的空仓库
            print(f"分支 '{branch}' 不存在，创建新分支...")
            os.makedirs(os.path.join(temp_dir, '.git'), exist_ok=True)
            run_command(['git', 'init'], cwd=temp_dir)
            # 配置用户信息，避免提交失败
            run_command(['git', 'config', 'user.email', 'github-pages-deploy@example.com'], cwd=temp_dir)
            run_command(['git', 'config', 'user.name', 'GitHub Pages Deploy Script'], cwd=temp_dir)
            run_command(['git', 'remote', 'add', 'origin', repo_url], cwd=temp_dir)
            run_command(['git', 'checkout', '-b', branch], cwd=temp_dir)
        
        # 复制源目录中的所有文件到临时目录
        for item in os.listdir(source_dir):
            source_path = os.path.join(source_dir, item)
            dest_path = os.path.join(temp_dir, item)
            if os.path.isdir(source_path):
                shutil.copytree(source_path, dest_path)
            else:
                shutil.copy2(source_path, dest_path)
        
        # 创建.nojekyll文件（防止GitHub Pages使用Jekyll处理）
        with open(os.path.join(temp_dir, '.nojekyll'), 'w') as f:
            pass
        
        # 添加所有文件到Git
        run_command(['git', 'add', '--all'], cwd=temp_dir)
        
        # 设置默认提交信息
        if not commit_message:
            commit_message = f"更新网站内容 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # 提交更改前检查是否有变更
        status = run_command(['git', 'status', '--porcelain'], cwd=temp_dir)
        if not status:
            print("没有文件变更，跳过提交")
        else:
            # 提交更改
            run_command(['git', 'commit', '-m', commit_message], cwd=temp_dir)
            
            # 推送到GitHub
            run_command(['git', 'push', '-u', 'origin', branch], cwd=temp_dir)
        
        print(f"部署成功！GitHub Pages将很快在以下地址可用:")
        # 从仓库URL中提取用户名和仓库名（使用原始URL，不包含token）
        repo_parts = original_repo_url.rstrip('/').split('/')
        user_repo = '/'.join(repo_parts[-2:])
        user_repo = user_repo.replace('.git', '')
        print(f"https://{user_repo.split('/')[0]}.github.io/{user_repo.split('/')[1]}/")
        
    finally:
        # 清理临时目录前先等待一下，确保所有文件操作完成
        time.sleep(1)
        
        # 清理临时目录，添加错误处理
        if os.path.exists(temp_dir):
            try:
                # 在Windows上，先修改.git目录中文件的权限
                if os.name == 'nt':
                    git_dir = os.path.join(temp_dir, '.git')
                    if os.path.exists(git_dir):
                        # 使用attrib命令移除只读属性
                        subprocess.run(['attrib', '-R', f"{git_dir}\\*.*", '/S'], shell=True)
                
                shutil.rmtree(temp_dir)
                print(f"已清理临时目录: {temp_dir}")
            except PermissionError as e:
                print(f"警告: 无法完全删除临时目录: {e}")
                print(f"请手动删除目录: {os.path.abspath(temp_dir)}")

if __name__ == "__main__":
    args = parse_arguments()
    
    # 尝试从.env文件加载环境变量
    load_dotenv(args.env_file)
    
    # 优先使用命令行参数中的token，如果没有则尝试从环境变量获取
    token = args.token or os.environ.get('GITHUB_TOKEN')

    if not token and args.repo.startswith('https://'):
        print("警告: 未提供GitHub令牌。如需使用令牌认证，请通过--token参数提供或在.env文件中设置GITHUB_TOKEN")

    repo = args.repo or os.environ.get('GITHUB_REPO')
    print(f"使用仓库: {repo}")

    deploy_to_github(
        args.source_dir,
        repo,
        args.branch,
        args.commit_message,
        args.temp_dir,
        token
    ) 