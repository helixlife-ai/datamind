def load_prompt(prompt):
    import os
    # 获取当前模块的绝对路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 构建提示词文件的绝对路径
    prompt_path = os.path.join(current_dir, f"{prompt}.txt")
    
    with open(prompt_path, "r", encoding="utf-8") as file:
        return file.read()

def format_prompt(prompt, **kwargs):
    """加载提示词并替换其中的{{}}占位符
    
    Args:
        prompt: 提示词名称或提示词内容
        **kwargs: 要替换的占位符及其值
        
    Returns:
        str: 替换占位符后的提示词内容
    """
    # 检查是否是提示词名称还是已加载的提示词内容
    if not prompt.endswith('.txt') and '\n' not in prompt and len(prompt) < 100:
        # 可能是提示词名称，尝试加载
        prompt_content = load_prompt(prompt)
    else:
        # 已经是提示词内容
        prompt_content = prompt
    
    # 替换所有{{key}}格式的占位符
    for key, value in kwargs.items():
        placeholder = '{{' + key + '}}'
        prompt_content = prompt_content.replace(placeholder, str(value))
    
    return prompt_content