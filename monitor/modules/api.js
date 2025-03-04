const fs = require('fs');
const path = require('path');
const { OpenAI } = require('openai');

// API提供商和模型配置
const API_CONFIGS = {
    'deepseek': {
        defaultModel: 'deepseek-chat',
        reasoningModel: 'deepseek-reasoner',
        currentIndex: 0
    },
    'siliconflow': {
        defaultModel: 'Pro/deepseek-ai/DeepSeek-V3',
        reasoningModel: 'Pro/deepseek-ai/DeepSeek-R1',
        currentIndex: 0
    }
};

/**
 * 解析API密钥列表
 * @param {string} envValue - 环境变量值
 * @returns {Array} 解析后的API密钥数组
 */
function parseApiKeys(envValue) {
    console.log(`解析API密钥，原始值类型: ${typeof envValue}`);
    
    if (!envValue) {
        console.log('环境变量值为空');
        return [];
    }
    
    try {
        // 如果是字符串数组格式 ['key1','key2']
        if (typeof envValue === 'string') {
            console.log(`环境变量是字符串，长度: ${envValue.length}`);
            
            if (envValue.startsWith('[') && envValue.endsWith(']')) {
                console.log('检测到数组格式的字符串');
                // 移除方括号并分割字符串
                const keysString = envValue.slice(1, -1);
                
                // 使用正则表达式匹配引号内的内容
                const keyMatches = keysString.match(/'[^']*'|"[^"]*"/g) || [];
                console.log(`正则匹配到 ${keyMatches.length} 个密钥`);
                
                if (keyMatches.length === 0) {
                    // 尝试简单的逗号分割
                    console.log('尝试使用逗号分割');
                    const keys = keysString.split(',').map(k => k.trim().replace(/["']/g, ''));
                    console.log(`逗号分割得到 ${keys.length} 个密钥`);
                    return keys.filter(k => k);
                }
                
                const keys = keyMatches.map(k => k.slice(1, -1).trim());
                return keys.filter(k => k);  // 移除空值
            } else {
                // 单个字符串密钥
                return [envValue.trim()];
            }
        }
        // 如果已经是数组
        else if (Array.isArray(envValue)) {
            console.log(`环境变量是数组，长度: ${envValue.length}`);
            return envValue.filter(k => k);
        }
        
        console.log(`环境变量是其他类型: ${typeof envValue}`);
        return [];
    } catch (e) {
        console.error('解析API密钥失败:', e);
        return [];
    }
}

/**
 * 初始化API客户端
 * @returns {Object} API客户端对象
 */
function setupApiClients() {
    // 初始化API客户端
    const OPENAI_CLIENTS = {
        'deepseek': [],
        'siliconflow': []
    };

    // 直接从.env文件读取内容，用于调试
    try {
        const envContent = fs.readFileSync(path.resolve('.env'), 'utf8');
        const envLines = envContent.split('\n');
        console.log('直接读取.env文件内容:');
        envLines.forEach(line => {
            if (line.trim() && !line.startsWith('#')) {
                // 隐藏实际密钥值
                const parts = line.split('=');
                if (parts.length >= 2) {
                    const key = parts[0].trim();
                    console.log(`${key}=${key.includes('KEY') ? '[已隐藏]' : parts.slice(1).join('=')}`);
                } else {
                    console.log(line);
                }
            }
        });
    } catch (err) {
        console.log('无法直接读取.env文件:', err.message);
    }

    // 读取并解析DeepSeek API密钥
    console.log('处理DeepSeek API密钥:');
    console.log(`环境变量 DEEPSEEK_API_KEY: ${process.env.DEEPSEEK_API_KEY ? '存在' : '不存在'}`);
    const deepseekApiKeys = parseApiKeys(process.env.DEEPSEEK_API_KEY);
    console.log(`解析后的DeepSeek API密钥数量: ${deepseekApiKeys.length}`);

    deepseekApiKeys.forEach((key, index) => {
        if (key) {
            try {
                OPENAI_CLIENTS.deepseek.push(new OpenAI({
                    apiKey: key,
                    baseURL: process.env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com'
                }));
                console.log(`成功添加DeepSeek API客户端 #${index+1}`);
            } catch (err) {
                console.error(`初始化DeepSeek API客户端 #${index+1} 失败:`, err);
            }
        } else {
            console.log(`跳过空的DeepSeek API密钥 #${index+1}`);
        }
    });

    // 读取并解析SiliconFlow API密钥
    console.log('处理SiliconFlow API密钥:');
    console.log(`环境变量 SILICONFLOW_API_KEY: ${process.env.SILICONFLOW_API_KEY ? '存在' : '不存在'}`);
    const siliconflowApiKeys = parseApiKeys(process.env.SILICONFLOW_API_KEY);
    console.log(`解析后的SiliconFlow API密钥数量: ${siliconflowApiKeys.length}`);

    // 如果没有从环境变量中获取到密钥，尝试使用硬编码的备用密钥（仅用于测试）
    if (siliconflowApiKeys.length === 0) {
        console.log('未从环境变量获取到SiliconFlow API密钥，尝试使用.env文件中的值');
        // 从.env文件中提取的值
        const backupKeys = [
            'sk-vetzamuciebbtsmwdllqxgvztzlfypvpcrhhgituizwppjzr',
            'sk-vungowlfsnzutpdkzmwplimgiktpounmjqqvjojhwnntrlyb'
        ];
        console.log(`使用备用密钥，数量: ${backupKeys.length}`);
        
        backupKeys.forEach((key, index) => {
            if (key) {
                try {
                    OPENAI_CLIENTS.siliconflow.push(new OpenAI({
                        apiKey: key,
                        baseURL: process.env.SILICONFLOW_BASE_URL || 'https://api.siliconflow.cn/v1'
                    }));
                    console.log(`成功添加备用SiliconFlow API客户端 #${index+1}`);
                } catch (err) {
                    console.error(`初始化备用SiliconFlow API客户端 #${index+1} 失败:`, err);
                }
            }
        });
    } else {
        siliconflowApiKeys.forEach((key, index) => {
            if (key) {
                try {
                    OPENAI_CLIENTS.siliconflow.push(new OpenAI({
                        apiKey: key,
                        baseURL: process.env.SILICONFLOW_BASE_URL || 'https://api.siliconflow.cn/v1'
                    }));
                    console.log(`成功添加SiliconFlow API客户端 #${index+1}`);
                } catch (err) {
                    console.error(`初始化SiliconFlow API客户端 #${index+1} 失败:`, err);
                }
            } else {
                console.log(`跳过空的SiliconFlow API密钥 #${index+1}`);
            }
        });
    }

    console.log(`已加载 ${OPENAI_CLIENTS.deepseek.length} 个 DeepSeek API 客户端`);
    console.log(`已加载 ${OPENAI_CLIENTS.siliconflow.length} 个 SiliconFlow API 客户端`);

    // 打印环境变量原始值（隐藏实际密钥）
    console.log(`环境变量 DEEPSEEK_API_KEY 是否存在: ${!!process.env.DEEPSEEK_API_KEY}`);
    console.log(`环境变量 SILICONFLOW_API_KEY 是否存在: ${!!process.env.SILICONFLOW_API_KEY}`);
    console.log(`环境变量 DEEPSEEK_BASE_URL: ${process.env.DEEPSEEK_BASE_URL}`);
    console.log(`环境变量 SILICONFLOW_BASE_URL: ${process.env.SILICONFLOW_BASE_URL}`);

    return {
        clients: OPENAI_CLIENTS,
        configs: API_CONFIGS,
        getNextApiClient: function(provider) {
            if (!OPENAI_CLIENTS[provider] || OPENAI_CLIENTS[provider].length === 0) {
                console.error(`没有可用的 ${provider} API 客户端`);
                return null;
            }
            
            const index = API_CONFIGS[provider].currentIndex;
            API_CONFIGS[provider].currentIndex = (index + 1) % OPENAI_CLIENTS[provider].length;
            return OPENAI_CLIENTS[provider][index];
        },
        /**
         * 获取指定提供商的模型名称
         * @param {string} provider - API提供商名称
         * @param {boolean} useReasoning - 是否使用推理模型
         * @returns {string} 模型名称
         */
        getModelName: function(provider, useReasoning = false) {
            if (!API_CONFIGS[provider]) {
                console.error(`未知的API提供商: ${provider}，使用默认值`);
                return 'deepseek-chat';
            }
            
            return useReasoning ? 
                API_CONFIGS[provider].reasoningModel : 
                API_CONFIGS[provider].defaultModel;
        }
    };
}

module.exports = {
    setupApiClients,
    parseApiKeys
}; 