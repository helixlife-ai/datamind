const express = require('express');
const app = express();
const http = require('http').createServer(app);
const io = require('socket.io')(http);
const chokidar = require('chokidar');
const path = require('path');
const fs = require('fs');
const dotenv = require('dotenv');
const { OpenAI } = require('openai');
const crypto = require('crypto');
const fsPromises = require('fs').promises;
const { exec } = require('child_process');

// 添加全局变量定义
const activeProcesses = new Set();

// 添加任务历史记录存储
const taskOutputHistory = {};
const MAX_HISTORY_ITEMS = 1000; // 每个任务最多保存的输出条数

// 添加输出缓冲区
const outputBuffers = new Map();

// 在发送任务输出到客户端的地方，同时保存到历史记录
function emitTaskOutput(alchemy_id, output, isError = false) {
    // 获取或创建此任务的缓冲区
    if (!outputBuffers.has(alchemy_id)) {
        outputBuffers.set(alchemy_id, {
            buffer: '',
            timeout: null,
            isError: false
        });
    }
    
    const bufferInfo = outputBuffers.get(alchemy_id);
    
    // 如果新输出是错误，标记缓冲区为错误
    if (isError) {
        bufferInfo.isError = true;
    }
    
    // 添加到缓冲区
    bufferInfo.buffer += output;
    
    // 清除之前的超时
    if (bufferInfo.timeout) {
        clearTimeout(bufferInfo.timeout);
    }
    
    // 设置新的超时，延迟发送合并后的输出
    bufferInfo.timeout = setTimeout(() => {
        // 发送到所有连接的客户端
        io.emit('taskOutput', {
            alchemy_id: alchemy_id,
            output: bufferInfo.buffer,
            isError: bufferInfo.isError,
            encoding: 'utf8'
        });
        
        // 保存到历史记录
        if (alchemy_id) {
            if (!taskOutputHistory[alchemy_id]) {
                taskOutputHistory[alchemy_id] = [];
            }
            
            // 添加新的输出记录
            taskOutputHistory[alchemy_id].push({
                output: bufferInfo.buffer,
                isError: bufferInfo.isError,
                timestamp: new Date().toISOString()
            });
            
            // 限制历史记录大小
            if (taskOutputHistory[alchemy_id].length > MAX_HISTORY_ITEMS) {
                taskOutputHistory[alchemy_id] = taskOutputHistory[alchemy_id].slice(-MAX_HISTORY_ITEMS);
            }
        }
        
        // 清空缓冲区
        bufferInfo.buffer = '';
        bufferInfo.isError = false;
        bufferInfo.timeout = null;
    }, 100); // 100毫秒的延迟，可以根据需要调整
}

// 查找与数据炼丹相关的Python进程
function findPythonProcesses(callback) {
    const { exec } = require('child_process');
    
    // 根据操作系统选择不同的命令
    let cmd;
    if (process.platform === 'win32') {
        // Windows: 使用 wmic 查找 python 进程，并过滤包含 datamind 相关关键词的进程
        cmd = 'wmic process where "name=\'python.exe\'" get processid,commandline';
    } else {
        // Linux/Mac: 使用 ps 和 grep 查找 python 进程，并过滤包含 datamind 相关关键词的进程
        cmd = 'ps aux | grep python | grep -E "datamind|example_usage.py|alchemy_manager_cli.py" | grep -v grep';
    }
    
    exec(cmd, (error, stdout, stderr) => {
        if (error && error.code !== 1) {
            // 命令执行错误（但grep没有匹配项时返回1，这不是错误）
            console.error(`查找Python进程失败: ${error.message}`);
            return callback([]);
        }
        
        const pids = [];
        
        if (process.platform === 'win32') {
            // 解析Windows wmic输出
            const lines = stdout.trim().split('\n');
            
            // 如果没有找到任何进程，直接调用回调
            if (lines.length === 0) {
                return callback(pids);
            }
            
            // 跳过标题行
            for (let i = 1; i < lines.length; i++) {
                const line = lines[i].trim();
                // 只处理包含项目相关关键词的进程
                if (line && (line.includes('datamind') || 
                             line.includes('example_usage.py') || 
                             line.includes('alchemy_manager_cli.py'))) {
                    // 提取PID（最后一列）
                    const pid = line.trim().split(/\s+/).pop();
                    if (pid && /^\d+$/.test(pid)) {
                        pids.push(pid);
                    }
                }
            }
            
            callback(pids);
        } else {
            // 解析Linux/Mac ps输出
            const lines = stdout.trim().split('\n');
            for (const line of lines) {
                const parts = line.trim().split(/\s+/);
                if (parts.length > 1) {
                    pids.push(parts[1]);
                }
            }
            callback(pids);
        }
    });
}

// 从运行中的进程获取任务ID
function getTaskIdFromRunningProcess(pids) {
    // 首先检查活动进程集合
    for (const process of activeProcesses) {
        if (pids.includes(String(process.pid))) {
            return process.taskId;
        }
    }
    
    // 如果在活动进程集合中没有找到，尝试从命令行参数中提取
    try {
        const { execSync } = require('child_process');
        
        for (const pid of pids) {
            let cmdOutput;
            
            if (process.platform === 'win32') {
                // Windows
                cmdOutput = execSync(`wmic process where processid=${pid} get commandline`, { encoding: 'utf8' });
            } else {
                // Linux/Mac
                cmdOutput = execSync(`ps -p ${pid} -o command=`, { encoding: 'utf8' });
            }
            
            // 首先尝试从命令行中提取 --id= 参数
            let match = cmdOutput.match(/--id=([a-zA-Z0-9_-]+)/);
            if (match && match[1]) {
                return match[1];
            }
            
            // 然后尝试从命令行中提取 alchemy_id= 参数
            match = cmdOutput.match(/alchemy_id=([a-zA-Z0-9_-]+)/);
            if (match && match[1]) {
                return match[1];
            }
            
            // 最后尝试从路径中提取 alchemy_{id} 格式的任务ID
            match = cmdOutput.match(/alchemy_([a-zA-Z0-9_-]+)/);
            if (match && match[1]) {
                return match[1];
            }
        }
    } catch (error) {
        console.error(`从进程命令行获取任务ID失败: ${error.message}`);
    }
    
    // 如果上述方法都失败，回退到检查最近的任务
    const recentTasks = Object.keys(taskOutputHistory);
    if (recentTasks.length > 0) {
        // 返回最近的任务ID
        return recentTasks[recentTasks.length - 1];
    }
    
    // 如果所有方法都失败，返回一个占位符
    return "未知任务";
}

// 在任务完成或被取消时清理历史记录
function cleanupTaskHistory(alchemy_id) {
    // 可选：在任务完成一段时间后清理历史记录
    setTimeout(() => {
        if (taskOutputHistory[alchemy_id]) {
            delete taskOutputHistory[alchemy_id];
            console.log(`已清理任务历史记录: ${alchemy_id}`);
        }
    }, 30 * 60 * 1000); // 30分钟后清理
}

// 读取环境变量
dotenv.config();

// 打印环境变量加载路径
console.log(`dotenv配置路径: ${path.resolve('.env')}`);
console.log(`当前工作目录: ${process.cwd()}`);

// 读取配置文件
let config;
try {
    config = JSON.parse(fs.readFileSync(path.join(__dirname, 'config.json'), 'utf8'));
} catch (err) {
    console.error('Error reading config file:', err);
    config = {
        watchDirs: [{ path: 'watchdir', name: 'Default Watch Directory' }],
        port: 3000,
        excludePatterns: ['node_modules', '.git', '*.log']
    };
}

// 解析API密钥列表
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

// 获取下一个API客户端
function getNextApiClient(provider) {
    if (!OPENAI_CLIENTS[provider] || OPENAI_CLIENTS[provider].length === 0) {
        console.error(`没有可用的 ${provider} API 客户端`);
        return null;
    }
    
    const index = API_CONFIGS[provider].currentIndex;
    API_CONFIGS[provider].currentIndex = (index + 1) % OPENAI_CLIENTS[provider].length;
    return OPENAI_CLIENTS[provider][index];
}

// 聊天会话管理
class ChatSessionManager {
    constructor(config) {
        // 尝试从顶级配置中查找聊天记录目录
        if (config.chatRecordDir && config.chatRecordDir.path) {
            this.chatRecordDir = config.chatRecordDir.path;
            this.chatRecordName = config.chatRecordDir.name || "聊天记录";
            this.fullChatRecordDir = path.join(__dirname, this.chatRecordDir);
            console.log(`使用顶级配置的聊天记录目录: ${this.chatRecordDir}`);
        } 
        // 向后兼容：从watchDirs中查找
        else {
            const chatDir = config.watchDirs.find(dir => dir.name === "聊天记录");
            
            if (chatDir) {
                this.chatRecordDir = chatDir.path;
                this.chatRecordName = chatDir.name;
                this.fullChatRecordDir = path.join(__dirname, this.chatRecordDir);
                console.log(`从watchDirs中使用聊天记录目录: ${this.chatRecordDir}`);
            } else {
                // 如果配置中没有找到，使用默认目录
                this.chatRecordDir = "../work_dir/data_alchemy/chat_records";
                this.chatRecordName = "聊天记录";
                this.fullChatRecordDir = path.join(__dirname, this.chatRecordDir);
                console.warn(`配置中未找到聊天记录目录，使用默认路径: ${this.chatRecordDir}`);
            }
        }
        
        this.sessions = new Map();
        this.initDirectory();
    }

    // 初始化聊天记录目录
    async initDirectory() {
        try {
            // 确保目录存在
            await fsPromises.mkdir(this.fullChatRecordDir, { recursive: true });
            console.log(`聊天记录目录已初始化: ${this.fullChatRecordDir}`);
            
            // 创建一个README文件，解释目录用途
            const readmePath = path.join(this.fullChatRecordDir, 'README.md');
            const readmeContent = `# 聊天记录\n\n此目录包含与AI助手的聊天历史记录。\n\n- *.json 文件包含原始对话数据\n- *.txt 文件是可读的对话文本版本\n\n创建时间: ${new Date().toLocaleString('zh-CN')}\n`;
            
            try {
                // 如果README不存在，创建它
                if (!fs.existsSync(readmePath)) {
                    await fsPromises.writeFile(readmePath, readmeContent, 'utf8');
                    console.log('已创建聊天记录README文件');
                }
            } catch (readmeErr) {
                console.warn('创建README文件失败:', readmeErr);
            }
        } catch (err) {
            console.error('初始化聊天记录目录失败:', err);
        }
    }

    // 生成会话ID
    generateSessionId() {
        return crypto.randomBytes(16).toString('hex');
    }

    // 获取或创建会话
    async getOrCreateSession(sessionId) {
        if (!sessionId) {
            sessionId = this.generateSessionId();
        }

        if (!this.sessions.has(sessionId)) {
            const messages = await this.loadChatHistory(sessionId);
            this.sessions.set(sessionId, {
                id: sessionId,
                messages: messages || [],
                lastActivity: Date.now()
            });
        }

        return {
            sessionId,
            session: this.sessions.get(sessionId)
        };
    }

    // 加载聊天历史
    async loadChatHistory(sessionId) {
        const filePath = path.join(this.fullChatRecordDir, `${sessionId}.json`);
        
        try {
            const data = await fsPromises.readFile(filePath, 'utf8');
            return JSON.parse(data);
        } catch (err) {
            // 文件不存在或其他错误，返回空数组
            if (err.code !== 'ENOENT') {
                console.error(`加载聊天历史失败 ${sessionId}:`, err);
            }
            return [];
        }
    }

    // 保存聊天历史 - 添加验证和错误处理
    async saveChatHistory(sessionId, messages) {
        if (!sessionId) return;
        
        // 验证保存路径是否在指定的聊天记录目录内
        const jsonFilePath = path.join(this.fullChatRecordDir, `${sessionId}.json`);
        const txtFilePath = path.join(this.fullChatRecordDir, `${sessionId}.txt`);
        
        // 确保文件路径在聊天记录目录内，防止路径遍历攻击
        if (!jsonFilePath.startsWith(this.fullChatRecordDir) || !txtFilePath.startsWith(this.fullChatRecordDir)) {
            console.error(`安全警告: 尝试在聊天记录目录外保存文件: ${jsonFilePath}`);
            return;
        }
        
        const session = this.sessions.get(sessionId);
        if (session) {
            session.messages = messages;
            session.lastActivity = Date.now();
        }
        
        try {
            // 创建带有日期和时间的消息格式
            const currentTimestamp = new Date().toLocaleString('zh-CN');
            
            // 保存JSON格式记录
            await fsPromises.writeFile(jsonFilePath, JSON.stringify(messages, null, 2), 'utf8');
            
            // 创建可读性更好的文本版本
            const textContent = messages.map(msg => {
                const isUser = msg.role === 'user';
                const roleLabel = isUser ? '👤 用户' : '🤖 AI助手';
                return `${roleLabel} [${currentTimestamp}]\n${msg.content}\n\n`;
            }).join('---\n\n');
            
            await fsPromises.writeFile(txtFilePath, textContent, 'utf8');
            console.log(`已保存聊天记录: ${sessionId}`);
        } catch (err) {
            console.error(`保存聊天历史失败 ${sessionId}:`, err);
        }
    }

    // 清理不活跃的会话
    cleanupSessions(maxAgeMs = 24 * 60 * 60 * 1000) {
        const now = Date.now();
        for (const [sessionId, session] of this.sessions.entries()) {
            if (now - session.lastActivity > maxAgeMs) {
                this.sessions.delete(sessionId);
            }
        }
    }
}

// 创建聊天会话管理器实例
const chatSessionManager = new ChatSessionManager(config);

// 定期清理不活跃的会话(每小时)
setInterval(() => {
    chatSessionManager.cleanupSessions();
}, 60 * 60 * 1000);

// 设置Express应用
app.use(express.static('public'));
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// 设置响应头，确保正确的字符编码
app.use((req, res, next) => {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    next();
});

// 处理监控目录的路径
const watchDirs = config.watchDirs.map(dir => ({
    ...dir,
    fullPath: path.join(__dirname, dir.path)
}));

// 确保所有监控目录都存在
watchDirs.forEach(dir => {
    if (!fs.existsSync(dir.fullPath)) {
        fs.mkdirSync(dir.fullPath, { recursive: true });
        console.log(`Created directory: ${dir.fullPath}`);
    }
});

// 设置文件监控函数
function setupFileWatcher(dir, dirKey) {
    const watcher = chokidar.watch(dir.fullPath, {
        ignored: config.excludePatterns,
        persistent: true,
        ignoreInitial: true, // 忽略初始扫描事件
        awaitWriteFinish: {
            stabilityThreshold: 1000, // 等待文件写入完成
            pollInterval: 100
        }
    });
    
    // 监听文件变化事件
    watcher.on('all', (event, path) => {
        const relativePath = path.replace(dir.fullPath, '').replace(/^[\/\\]/, '');
        const time = new Date().toLocaleTimeString();
        
        // 记录到服务器日志，但不发送到客户端终端
        console.log(`[文件变化] ${event}: ${dirKey}/${relativePath} (${time})`);
        
        // 仅发送文件变化事件，不包含在终端输出中
        io.emit('fileChange', {
            type: event,
            dir: dirKey,
            path: relativePath,
            time: time,
            shouldDisplay: false // 添加标志，表示不应在终端显示
        });
        
        // 更新文件结构
        updateFileStructure();
    });
    
    return watcher;
}

// 更新文件结构函数
function updateFileStructure() {
    const structure = {};
    
    watchDirs.forEach(dir => {
        const dirKey = dir.path;
        structure[dirKey] = {
            name: dir.name || dirKey,
            description: dir.description || '',
            files: buildFileSystemStructure(dir.fullPath)
        };
    });
    
    io.emit('initialStructure', structure);
}

// 初始化文件监控
let watchers = [];
watchDirs.forEach(dir => {
    const dirKey = dir.path;
    const watcher = setupFileWatcher(dir, dirKey);
    watchers.push(watcher);
});

// 初始化时发送文件结构
updateFileStructure();

// 构建文件系统结构的函数
function buildFileSystemStructure(dirPath, baseDir = dirPath) {
    const structure = {};
    try {
        const items = fs.readdirSync(dirPath);
        items.forEach(item => {
            const fullPath = path.join(dirPath, item);
            const stat = fs.statSync(fullPath);

            if (stat.isDirectory()) {
                structure[item] = buildFileSystemStructure(fullPath, baseDir);
            } else {
                structure[item] = true;
            }
        });
    } catch (err) {
        console.error(`Error reading directory ${dirPath}:`, err);
    }
    return structure;
}

// 获取相对路径的函数
function getRelativePath(fullPath) {
    for (const dir of watchDirs) {
        if (fullPath.startsWith(dir.fullPath)) {
            return {
                dirId: dir.path,
                relativePath: path.relative(dir.fullPath, fullPath).replace(/\\/g, '/')
            };
        }
    }
    return null;
}

// 添加配置API
app.get('/api/config', (req, res) => {
    res.json({
        watchDirs: config.watchDirs,
        excludePatterns: config.excludePatterns
    });
});

// 添加获取配置文件API
app.get('/api/get-config', (req, res) => {
    try {
        const configPath = path.join(__dirname, '..', 'work_dir', 'config.json');
        if (fs.existsSync(configPath)) {
            const configData = JSON.parse(fs.readFileSync(configPath, 'utf8'));
            res.json(configData);
        } else {
            res.json({ message: '配置文件不存在' });
        }
    } catch (error) {
        console.error('读取配置文件失败:', error);
        res.status(500).json({ error: `读取配置文件失败: ${error.message}` });
    }
});

// 添加浏览文件夹API
app.get('/api/browse-folders', (req, res) => {
    try {
        // 首先尝试使用Electron的对话框
        let electronAvailable = false;
        try {
            // 检查是否在Electron环境中
            const electron = require('electron');
            electronAvailable = !!electron.dialog;
        } catch (e) {
            console.log('不在Electron环境中，将使用备用方法');
            electronAvailable = false;
        }
        
        if (electronAvailable) {
            // 使用Electron对话框
            const { dialog } = require('electron');
            const BrowserWindow = require('electron').BrowserWindow;
            const win = BrowserWindow.getFocusedWindow();
            
            dialog.showOpenDialog(win, {
                properties: ['openDirectory'],
                defaultPath: path.join(__dirname, '..', 'work_dir')
            }).then(result => {
                if (result.canceled || result.filePaths.length === 0) {
                    return res.json({ success: false, message: '用户取消选择' });
                }
                
                const selectedPath = result.filePaths[0];
                res.json({ success: true, path: selectedPath });
            }).catch(err => {
                console.error('打开文件夹对话框失败:', err);
                useBackupMethod();
            });
        } else {
            // 使用备用方法
            useBackupMethod();
        }
        
        // 备用方法：返回work_dir目录下的文件夹列表
        function useBackupMethod() {
            try {
                // 获取请求中的当前路径参数
                const currentPath = req.query.path || path.join(__dirname, '..', 'work_dir');
                
                // 确保路径存在
                if (!fs.existsSync(currentPath)) {
                    return res.json({ 
                        success: false, 
                        error: `路径不存在: ${currentPath}` 
                    });
                }
                
                // 确保路径是目录
                const stats = fs.statSync(currentPath);
                if (!stats.isDirectory()) {
                    return res.json({ 
                        success: false, 
                        error: `不是目录: ${currentPath}` 
                    });
                }
                
                // 读取目录内容
                const items = fs.readdirSync(currentPath, { withFileTypes: true });
                
                // 过滤出目录
                const dirs = items
                    .filter(item => item.isDirectory())
                    .map(item => {
                        const fullPath = path.join(currentPath, item.name);
                        return {
                            name: item.name,
                            path: fullPath,
                            isParent: false
                        };
                    });
                
                // 添加父目录（如果不是根目录）
                const parentDir = path.dirname(currentPath);
                if (parentDir !== currentPath) {
                    dirs.unshift({
                        name: '..',
                        path: parentDir,
                        isParent: true
                    });
                }
                
                // 如果是直接选择路径的请求
                if (req.query.select === 'true') {
                    return res.json({ 
                        success: true, 
                        path: currentPath 
                    });
                }
                
                // 返回目录列表和当前路径
                res.json({ 
                    success: true, 
                    current_path: currentPath,
                    directories: dirs,
                    is_backup_method: true
                });
            } catch (error) {
                console.error('备用方法失败:', error);
                res.status(500).json({ 
                    success: false, 
                    error: `浏览文件夹失败: ${error.message}` 
                });
            }
        }
    } catch (error) {
        console.error('浏览文件夹失败:', error);
        res.status(500).json({ 
            success: false, 
            error: `浏览文件夹失败: ${error.message}` 
        });
    }
});

// 添加获取任务信息API
app.get('/api/task-info', async (req, res) => {
    try {
        const taskId = req.query.id;
        if (!taskId) {
            return res.status(400).json({ error: '缺少任务ID参数' });
        }
        
        console.log(`获取任务信息: ${taskId}`);
        
        // 构建任务目录路径
        const workDir = path.join(__dirname, '..');
        const alchemyDir = path.join(workDir, 'work_dir', 'data_alchemy');
        const runsDir = path.join(alchemyDir, 'alchemy_runs');
        const taskDir = path.join(runsDir, `alchemy_${taskId}`);
        
        // 检查任务目录是否存在
        if (!fs.existsSync(taskDir)) {
            return res.status(404).json({ error: `任务 ${taskId} 不存在` });
        }
        
        // 读取恢复信息
        const resumeInfoPath = path.join(taskDir, 'resume_info.json');
        let resumeInfo = null;
        if (fs.existsSync(resumeInfoPath)) {
            try {
                resumeInfo = JSON.parse(fs.readFileSync(resumeInfoPath, 'utf8'));
            } catch (e) {
                console.warn(`读取恢复信息失败: ${e.message}`);
            }
        }
        
        // 读取下一轮迭代配置
        const nextConfigPath = path.join(taskDir, 'next_iteration_config.json');
        let nextIterationConfig = null;
        if (fs.existsSync(nextConfigPath)) {
            try {
                nextIterationConfig = JSON.parse(fs.readFileSync(nextConfigPath, 'utf8'));
            } catch (e) {
                console.warn(`读取下一轮迭代配置失败: ${e.message}`);
            }
        }
        
        // 读取状态信息
        const statusPath = path.join(taskDir, 'status.json');
        let statusInfo = null;
        if (fs.existsSync(statusPath)) {
            try {
                statusInfo = JSON.parse(fs.readFileSync(statusPath, 'utf8'));
            } catch (e) {
                console.warn(`读取状态信息失败: ${e.message}`);
            }
        }
        
        // 构建任务信息对象
        const taskInfo = {
            id: taskId,
            task_dir: taskDir,
            resume_info: resumeInfo,
            next_iteration_config: nextIterationConfig,
            status: statusInfo
        };
        
        res.json(taskInfo);
    } catch (error) {
        console.error('获取任务信息失败:', error);
        res.status(500).json({ error: `获取任务信息失败: ${error.message}` });
    }
});

// 修改文件读取API
app.get('/api/file', (req, res) => {
    const dirPath = req.query.dir;
    const filePath = req.query.path;
    
    // 增加调试日志
    console.log('Received directory path:', dirPath);
    console.log('Received file path:', filePath);
    console.log('Available watch directories:', watchDirs.map(d => d.path));

    // 修改目录匹配逻辑
    const watchDir = watchDirs.find(d => {
        // 使用路径解析来确保格式一致
        const configPath = path.resolve(d.path);
        const requestPath = path.resolve(dirPath);
        return configPath === requestPath;
    });

    if (!watchDir) {
        console.error('Directory not found:', dirPath);
        return res.status(404).json({ error: 'Directory not found' });
    }

    // 修改路径构建方式
    const fullPath = path.join(watchDir.fullPath, filePath);
    console.log('Constructed full path:', fullPath);

    // 验证文件路径是否在监控目录下
    if (!fullPath.startsWith(path.resolve(watchDir.fullPath))) {
        return res.status(403).json({ error: 'Access denied' });
    }

    try {
        // 检查文件是否存在
        if (!fs.existsSync(fullPath)) {
            return res.status(404).json({ 
                error: `File not found: ${filePath}`
            });
        }

        // 检查是否是文件而不是目录
        const stats = fs.statSync(fullPath);
        if (!stats.isFile()) {
            return res.status(400).json({ error: 'Not a file' });
        }

        // 明确指定UTF-8编码读取文件
        const content = fs.readFileSync(fullPath, 'utf8');
        res.json({ content });
    } catch (err) {
        console.error('Error reading file:', err);
        res.status(500).json({ 
            error: 'Failed to read file: ' + err.message
        });
    }
});

// 添加聊天API
app.post('/api/chat', async (req, res) => {
    const { messages, provider = 'siliconflow', stream = true, sessionId } = req.body;
    
    if (!messages || !Array.isArray(messages) || messages.length === 0) {
        return res.status(400).json({ error: '无效的消息格式' });
    }
    
    try {
        // 获取或创建会话
        const { sessionId: activeSessionId, session } = await chatSessionManager.getOrCreateSession(sessionId);
        
        // 如果没有提供消息历史，使用会话中的历史
        const chatMessages = messages.length > 1 ? messages : [...session.messages, ...messages];
        
        const client = getNextApiClient(provider);
        if (!client) {
            return res.status(503).json({ error: 'API服务不可用' });
        }
        
        const modelName = API_CONFIGS[provider].defaultModel;
        
        if (stream) {
            // 流式响应
            res.setHeader('Content-Type', 'text/event-stream');
            res.setHeader('Cache-Control', 'no-cache');
            res.setHeader('Connection', 'keep-alive');
            
            // 用于记录完整响应
            let fullResponse = '';
            
            const stream = await client.chat.completions.create({
                model: modelName,
                messages: chatMessages,
                stream: true
            });
            
            // 发送会话ID
            res.write(`data: ${JSON.stringify({ sessionId: activeSessionId })}\n\n`);
            
            for await (const chunk of stream) {
                const content = chunk.choices[0]?.delta?.content || '';
                if (content) {
                    fullResponse += content;
                    res.write(`data: ${JSON.stringify({ content })}\n\n`);
                }
            }
            
            // 保存完整的对话历史
            if (fullResponse) {
                const updatedMessages = [
                    ...chatMessages,
                    { role: 'assistant', content: fullResponse }
                ];
                await chatSessionManager.saveChatHistory(activeSessionId, updatedMessages);
            }
            
            res.write('data: [DONE]\n\n');
            res.end();
        } else {
            // 非流式响应
            const response = await client.chat.completions.create({
                model: modelName,
                messages: chatMessages,
                stream: false
            });
            
            const responseContent = response.choices[0]?.message?.content || '';
            
            // 保存完整的对话历史
            if (responseContent) {
                const updatedMessages = [
                    ...chatMessages,
                    { role: 'assistant', content: responseContent }
                ];
                await chatSessionManager.saveChatHistory(activeSessionId, updatedMessages);
            }
            
            res.json({
                sessionId: activeSessionId,
                content: responseContent,
                usage: response.usage
            });
        }
    } catch (error) {
        console.error('聊天API调用失败:', error);
        // 如果流已经开始，发送错误事件
        if (res.headersSent) {
            res.write(`data: ${JSON.stringify({ error: error.message })}\n\n`);
            res.end();
        } else {
            res.status(500).json({ error: error.message });
        }
    }
});

// WebSocket连接处理
io.on('connection', (socket) => {
    console.log('Client connected');
    
    // 设置WebSocket编码
    socket.setEncoding && socket.setEncoding('utf8');
    
    // 发送配置信息
    socket.emit('configUpdate', config);

    // 发送初始文件系统结构
    try {
        const structure = {};
        watchDirs.forEach(dir => {
            structure[dir.path] = {
                name: dir.name,
                description: dir.description,
                files: buildFileSystemStructure(dir.fullPath)
            };
        });
        socket.emit('initialStructure', structure);
    } catch (err) {
        console.error('Error building file system structure:', err);
    }

    // 添加文件监听状态存储
    const watchingFiles = new Set();
    
    // 添加检查运行中任务的事件处理
    socket.on('checkRunningTasks', () => {
        // 检查是否有正在运行的Python进程
        findPythonProcesses((pids) => {
            const running = pids.length > 0;
            let taskId = null;
            
            if (running) {
                // 尝试从进程信息中获取任务ID
                // 这里可能需要根据实际情况调整获取任务ID的逻辑
                taskId = getTaskIdFromRunningProcess(pids);
            }
            
            socket.emit('runningTasksResult', {
                running: running,
                taskId: taskId,
                pids: pids
            });
        });
    });
    
    // 添加开始监听文件的事件处理
    socket.on('watchFile', (data) => {
        const { dir, path: filePath } = data;
        const watchDir = watchDirs.find(d => d.path === dir);
        if (!watchDir) return;
        
        const fullPath = path.join(watchDir.fullPath, filePath);
        const watchId = `${dir}:${filePath}`;
        
        if (watchingFiles.has(watchId)) return;
        watchingFiles.add(watchId);
        
        let lastSize = 0;
        try {
            lastSize = fs.statSync(fullPath).size;
        } catch (err) {
            console.error('Error getting file size:', err);
            return;
        }
        
        // 设置文件监听间隔
        const fileWatcher = setInterval(() => {
            try {
                const stats = fs.statSync(fullPath);
                if (stats.size > lastSize) {
                    // 只读取新增的内容
                    const fd = fs.openSync(fullPath, 'r');
                    const buffer = Buffer.alloc(stats.size - lastSize);
                    fs.readSync(fd, buffer, 0, buffer.length, lastSize);
                    fs.closeSync(fd);
                    
                    const newContent = buffer.toString('utf8');
                    socket.emit('fileUpdate', {
                        dir,
                        path: filePath,
                        content: newContent,
                        append: true
                    });
                    
                    lastSize = stats.size;
                }
            } catch (err) {
                console.error('Error watching file:', err);
                clearInterval(fileWatcher);
                watchingFiles.delete(watchId);
            }
        }, 1000); // 每秒检查一次
        
        // 当连接断开时清理监听器
        socket.on('disconnect', () => {
            clearInterval(fileWatcher);
            watchingFiles.delete(watchId);
        });
        
        // 当客户端停止监听时清理
        socket.on('stopWatchFile', (stopData) => {
            if (stopData.dir === dir && stopData.path === filePath) {
                clearInterval(fileWatcher);
                watchingFiles.delete(watchId);
            }
        });
    });

    socket.on('disconnect', () => {
        console.log('Client disconnected');
    });
});

// 添加获取可恢复任务API
app.get('/api/resumable-tasks', async (req, res) => {
    try {
        console.log('开始获取可恢复任务...');
        
        // 确定 Python 解释器路径
        const pythonPath = process.env.PYTHON_PATH || 'python';
        
        // 构建命令
        const command = `${pythonPath} examples/alchemy_manager_cli.py resumable --json`;
        console.log(`执行命令: ${command}`);
        
        // 使用child_process执行命令
        exec(command, {
            cwd: path.join(__dirname, '..'),
            env: { ...process.env, PYTHONIOENCODING: 'utf-8' }, // 确保Python输出使用UTF-8编码
            maxBuffer: 1024 * 1024 // 增加缓冲区大小到1MB
        }, (error, stdout, stderr) => {
            if (error) {
                console.error('获取可恢复任务失败:', error);
                console.error('命令输出 (stderr):', stderr);
                
                // 如果有stderr输出，返回更详细的错误信息
                if (stderr) {
                    return res.status(500).json({
                        success: false,
                        error: `命令执行失败: ${stderr}`
                    });
                }
                
                return res.status(500).json({
                    success: false,
                    error: `命令执行失败: ${error.message}`
                });
            }
            
            // 检查stdout是否为空
            if (!stdout || stdout.trim() === '') {
                console.log('命令执行成功，但没有输出数据');
                return res.json({
                    success: true,
                    tasks: []
                });
            }
            
            console.log('命令执行成功，尝试解析JSON输出');
            console.log('原始输出前50个字符:', stdout.substring(0, 50) + '...');
            
            try {
                // 尝试清理输出中可能存在的非JSON内容
                let cleanedOutput = stdout.trim();
                // 查找第一个 [ 和最后一个 ] 之间的内容
                const startIdx = cleanedOutput.indexOf('[');
                const endIdx = cleanedOutput.lastIndexOf(']');
                
                if (startIdx >= 0 && endIdx > startIdx) {
                    cleanedOutput = cleanedOutput.substring(startIdx, endIdx + 1);
                    console.log('已清理输出，提取JSON数组');
                }
                
                // 解析JSON
                const tasks = JSON.parse(cleanedOutput);
                
                // 验证解析结果是否为数组
                if (!Array.isArray(tasks)) {
                    console.error('解析结果不是数组:', typeof tasks);
                    throw new Error('解析结果不是数组');
                }
                
                console.log(`成功解析到 ${tasks.length} 个可恢复任务`);
                
                // 验证每个任务是否有必要的字段
                const validTasks = tasks.filter(task => {
                    if (!task || typeof task !== 'object') {
                        console.warn('任务不是对象:', task);
                        return false;
                    }
                    
                    if (!task.id) {
                        console.warn('任务缺少ID:', task);
                        return false;
                    }
                    
                    return true;
                });
                
                console.log(`有效任务数量: ${validTasks.length}`);
                
                // 返回有效的任务列表
                res.json({
                    success: true,
                    tasks: validTasks,
                    original_count: tasks.length,
                    valid_count: validTasks.length
                });
            } catch (parseError) {
                console.error('解析可恢复任务失败:', parseError);
                console.error('原始输出:', stdout);
                
                // 尝试直接返回一个硬编码的示例任务，用于调试
                const fallbackTasks = [];
                
                // 尝试从stdout中提取任务ID
                const idMatches = stdout.match(/alchemy_([a-zA-Z0-9_]+)/g);
                if (idMatches && idMatches.length > 0) {
                    console.log('从输出中提取到任务ID:', idMatches);
                    
                    // 为每个匹配的ID创建一个简单的任务对象
                    idMatches.forEach((match, index) => {
                        const taskId = match.replace('alchemy_', '');
                        fallbackTasks.push({
                            id: taskId,
                            name: `恢复的任务 ${index + 1}`,
                            resume_info: {
                                query: "从错误中恢复的查询",
                                timestamp: new Date().toISOString()
                            }
                        });
                    });
                    
                    console.log(`创建了 ${fallbackTasks.length} 个备用任务`);
                    
                    // 返回备用任务
                    return res.json({
                        success: true,
                        tasks: fallbackTasks,
                        is_fallback: true,
                        parse_error: parseError.message
                    });
                }
                
                // 如果无法提取任务ID，返回错误
                res.status(500).json({
                    success: false,
                    error: `解析任务数据失败: ${parseError.message}`,
                    rawOutput: stdout.substring(0, 1000) // 只返回前1000个字符，避免响应过大
                });
            }
        });
    } catch (error) {
        console.error('获取可恢复任务失败:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// 添加直接从文件系统获取可恢复任务的API
app.get('/api/direct-resumable-tasks', async (req, res) => {
    try {
        console.log('开始直接从文件系统获取可恢复任务...');
        
        // 工作目录路径
        const workDir = path.join(__dirname, '..');
        const alchemyDir = path.join(workDir, 'work_dir', 'data_alchemy');
        const runsDir = path.join(alchemyDir, 'alchemy_runs');
        
        console.log(`查找目录: ${runsDir}`);
        
        // 检查目录是否存在
        if (!fs.existsSync(runsDir)) {
            console.log(`目录不存在: ${runsDir}`);
            return res.json({
                success: true,
                tasks: [],
                message: '任务目录不存在'
            });
        }
        
        // 读取目录内容
        const dirEntries = fs.readdirSync(runsDir, { withFileTypes: true });
        
        // 过滤出alchemy_开头的目录
        const alchemyDirs = dirEntries.filter(entry => 
            entry.isDirectory() && entry.name.startsWith('alchemy_')
        );
        
        console.log(`找到 ${alchemyDirs.length} 个可能的任务目录`);
        
        // 收集可恢复任务
        const resumableTasks = [];
        
        for (const dir of alchemyDirs) {
            const taskId = dir.name.replace('alchemy_', '');
            const taskDir = path.join(runsDir, dir.name);
            const resumeInfoPath = path.join(taskDir, 'resume_info.json');
            
            // 检查是否有恢复信息文件
            if (fs.existsSync(resumeInfoPath)) {
                try {
                    // 读取恢复信息
                    const resumeInfo = JSON.parse(fs.readFileSync(resumeInfoPath, 'utf8'));
                    
                    // 读取状态信息（如果存在）
                    let statusInfo = {};
                    const statusPath = path.join(taskDir, 'status.json');
                    if (fs.existsSync(statusPath)) {
                        try {
                            statusInfo = JSON.parse(fs.readFileSync(statusPath, 'utf8'));
                        } catch (e) {
                            console.warn(`读取状态文件失败 ${taskId}: ${e.message}`);
                        }
                    }
                    
                    // 构建任务对象
                    const task = {
                        id: taskId,
                        name: statusInfo.name || `任务 ${taskId}`,
                        description: statusInfo.description || '',
                        latest_query: resumeInfo.query || (statusInfo.latest_query || ''),
                        resume_info: resumeInfo,
                        status: statusInfo.status || 'unknown',
                        created_at: statusInfo.created_at || resumeInfo.timestamp,
                        updated_at: statusInfo.updated_at || resumeInfo.timestamp
                    };
                    
                    resumableTasks.push(task);
                    console.log(`添加可恢复任务: ${taskId}`);
                } catch (e) {
                    console.error(`处理任务 ${taskId} 失败: ${e.message}`);
                }
            }
        }
        
        // 按时间戳排序（最新的在前）
        resumableTasks.sort((a, b) => {
            const timeA = a.resume_info?.timestamp || '';
            const timeB = b.resume_info?.timestamp || '';
            return timeB.localeCompare(timeA);
        });
        
        console.log(`找到 ${resumableTasks.length} 个可恢复任务`);
        
        // 返回结果
        res.json({
            success: true,
            tasks: resumableTasks,
            count: resumableTasks.length,
            method: 'direct'
        });
        
    } catch (error) {
        console.error('直接获取可恢复任务失败:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// 添加执行任务API
app.post('/api/execute-task', async (req, res) => {
    const { mode, query, alchemy_id, resume, input_dirs } = req.body;
    
    try {
        // 验证必填参数
        if (mode === "new" && !query) {
            return res.status(400).json({
                success: false,
                error: '新建任务模式下查询文本不能为空'
            });
        }
        
        // 在continue模式下验证任务ID
        if (mode === 'continue' && !alchemy_id) {
            return res.status(400).json({
                success: false,
                error: '继续任务模式下必须提供任务ID'
            });
        }
        
        // 构建命令参数
        const args = [
            'examples/example_usage.py',
            `--mode=${mode}`
        ];
        
        // 只在新建模式下添加查询参数
        if (mode === 'new' && query) {
            args.push(`--query=${query}`);
        }
        
        // 在continue模式下添加任务ID和恢复标志
        if (mode === 'continue' && alchemy_id) {
            args.push(`--id=${alchemy_id}`);
            
            if (resume) {
                args.push('--resume');
            }
        }
        
        // 只在新建模式下添加输入目录参数
        if (mode === 'new' && input_dirs && Array.isArray(input_dirs) && input_dirs.length > 0) {
            // 将输入目录列表转换为JSON字符串并添加到命令行参数
            args.push(`--input-dirs=${JSON.stringify(input_dirs)}`);
            console.log(`添加输入目录参数: ${input_dirs.length} 个目录`);
        }
        
        // 使用child_process执行命令
        const { spawn } = require('child_process');
        const workDir = path.join(__dirname, '..');
        
        // 确定 Python 解释器路径
        const pythonPath = process.env.PYTHON_PATH || 'python';
        
        // 构建脚本的绝对路径
        const scriptPath = path.join(workDir, 'examples', 'example_usage.py');
        console.log(`工作目录: ${workDir}`);
        console.log(`脚本路径: ${scriptPath}`);
        console.log(`Python解释器路径: ${pythonPath}`);
        console.log(`检查脚本是否存在: ${fs.existsSync(scriptPath) ? '存在' : '不存在'}`);
        
        // 更新参数，使用绝对路径
        args[0] = scriptPath;
        
        console.log(`执行命令: ${pythonPath} ${args.join(' ')}`);
        
        const pythonProcess = spawn(pythonPath, args, {
            cwd: workDir,
            env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
        });
        
        // 生成任务ID - 在continue模式下使用提供的ID，否则生成新ID
        let taskId = mode === 'continue' ? alchemy_id : (alchemy_id || crypto.randomBytes(8).toString('hex'));
        
        // 添加到活动进程集合
        const processInfo = { 
            pid: pythonProcess.pid, 
            taskId: taskId,
            startTime: new Date(),
            mode: mode,
            query: query,
            resume: resume,
            input_dirs: input_dirs // 保存输入目录信息
        };
        activeProcesses.add(processInfo);
        
        // 设置输出处理
        pythonProcess.stdout.on('data', (data) => {
            const output = data.toString('utf8');
            console.log(`[Task ${taskId}] ${output}`);
            
            // 通过WebSocket发送输出
            io.emit('taskOutput', {
                alchemy_id: taskId,
                output: output,
                encoding: 'utf8' // 明确指定编码
            });
            
            // 尝试从输出中提取alchemy_id
            const idMatch = output.match(/ID: ([a-f0-9]+)/i);
            if (idMatch && idMatch[1]) {
                const newTaskId = idMatch[1];
                console.log(`任务ID已更新: ${taskId} -> ${newTaskId}`);
                
                // 更新活动进程集合中的任务ID
                for (const process of activeProcesses) {
                    if (process.pid === pythonProcess.pid) {
                        process.taskId = newTaskId;
                        break;
                    }
                }
                
                // 更新任务ID
                taskId = newTaskId;
            }
        });
        
        pythonProcess.stderr.on('data', (data) => {
            const output = data.toString('utf8');
            console.error(`[Task ${taskId} STDERR] ${output}`);
            
            // 检查是否为真正的错误信息
            const isRealError = output.includes('Error') || 
                               output.includes('错误') || 
                               output.includes('Exception') || 
                               output.includes('异常') ||
                               output.includes('Failed') ||
                               output.includes('失败');
            
            // 通过WebSocket发送错误输出，但不再自动添加[错误]前缀
            io.emit('taskOutput', {
                alchemy_id: taskId,
                output: isRealError ? `[错误] ${output}` : output,
                encoding: 'utf8', // 明确指定编码
                isError: isRealError // 添加错误标志
            });
        });
        
        pythonProcess.on('close', (code) => {
            console.log(`[Task ${taskId}] 进程退出，代码: ${code}`);
            
            // 从活动进程集合中移除
            for (const process of activeProcesses) {
                if (process.pid === pythonProcess.pid) {
                    activeProcesses.delete(process);
                    break;
                }
            }
            
            // 通过WebSocket发送完成消息
            io.emit('taskOutput', {
                alchemy_id: taskId,
                output: `\n[任务完成] 退出代码: ${code}\n`,
                encoding: 'utf8' // 明确指定编码
            });
        });
        
        res.json({
            success: true,
            alchemy_id: taskId,
            message: '任务已启动'
        });
    } catch (error) {
        console.error('执行任务失败:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// 添加停止任务API
app.post('/api/stop-task', async (req, res) => {
    const { alchemy_id, stop_type } = req.body;
    
    try {
        // 验证必填参数
        if (!alchemy_id) {
            return res.status(400).json({
                success: false,
                error: '任务ID不能为空'
            });
        }
        
        console.log(`收到停止任务请求: ID=${alchemy_id}, 类型=${stop_type || 'force'}`);
        
        // 查找与该任务ID相关的进程
        let taskProcess = null;
        for (const process of activeProcesses) {
            if (process.taskId === alchemy_id) {
                taskProcess = process;
                break;
            }
        }
        
        // 如果找到了进程，直接终止它
        if (taskProcess) {
            console.log(`找到任务进程 PID=${taskProcess.pid}, 准备终止`);
            
            // 根据操作系统选择不同的终止方法
            if (process.platform === 'win32') {
                // Windows: 使用taskkill终止进程树
                try {
                    require('child_process').execSync(`taskkill /pid ${taskProcess.pid} /T /F`, {
                        stdio: 'ignore'
                    });
                    console.log(`已使用taskkill终止进程 ${taskProcess.pid}`);
                } catch (e) {
                    console.error(`使用taskkill终止进程失败: ${e.message}`);
                }
            } else {
                // Unix: 发送SIGTERM信号
                try {
                    process.kill(taskProcess.pid, 'SIGTERM');
                    console.log(`已发送SIGTERM信号到进程 ${taskProcess.pid}`);
                    
                    // 如果进程没有在1秒内退出，发送SIGKILL
                    setTimeout(() => {
                        try {
                            process.kill(taskProcess.pid, 'SIGKILL');
                            console.log(`已发送SIGKILL信号到进程 ${taskProcess.pid}`);
                        } catch (e) {
                            // 忽略错误，可能进程已经退出
                        }
                    }, 1000);
                } catch (e) {
                    console.error(`发送信号到进程失败: ${e.message}`);
                }
            }
            
            // 从活动进程集合中移除
            activeProcesses.delete(taskProcess);
            
            // 发送任务状态更新
            io.emit('taskStatus', {
                alchemy_id: alchemy_id,
                status: 'stopped',
                message: '任务已强制终止'
            });
            
            // 通过WebSocket发送完成消息
            io.emit('taskOutput', {
                alchemy_id: alchemy_id,
                output: `\n[任务已强制终止]\n`,
                encoding: 'utf8'
            });
            
            // 刷新可恢复任务列表
            io.emit('refreshResumableTasks');
            
            // 返回成功响应
            return res.json({
                success: true,
                message: '任务已强制终止',
                alchemy_id: alchemy_id,
                method: 'direct_termination'
            });
        }
        
        // 如果没有找到进程，尝试使用cancel命令
        console.log(`未找到任务进程，尝试使用cancel命令`);
        
        // 构建命令参数
        const args = [
            'examples/example_usage.py',
            `--id=${alchemy_id}`,
            `--cancel`
        ];
        
        // 使用child_process执行命令
        const { spawn } = require('child_process');
        const workDir = path.join(__dirname, '..');
        
        // 确定 Python 解释器路径
        const pythonPath = process.env.PYTHON_PATH || 'python';
        
        // 构建脚本的绝对路径
        const scriptPath = path.join(workDir, 'examples', 'example_usage.py');
        console.log(`工作目录: ${workDir}`);
        console.log(`脚本路径: ${scriptPath}`);
        console.log(`Python解释器路径: ${pythonPath}`);
        
        // 更新参数，使用绝对路径
        args[0] = scriptPath;
        
        console.log(`执行停止命令: ${pythonPath} ${args.join(' ')}`);
        
        const pythonProcess = spawn(pythonPath, args, {
            cwd: workDir,
            env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
        });
        
        // 设置输出处理
        let output = '';
        let errorOutput = '';
        
        pythonProcess.stdout.on('data', (data) => {
            const text = data.toString('utf8');
            output += text;
            console.log(`[停止任务 ${alchemy_id}] ${text}`);
            
            // 通过WebSocket发送输出
            io.emit('taskOutput', {
                alchemy_id: alchemy_id,
                output: `[停止请求] ${text}`,
                encoding: 'utf8'
            });
        });
        
        pythonProcess.stderr.on('data', (data) => {
            const text = data.toString('utf8');
            errorOutput += text;
            console.error(`[停止任务 ${alchemy_id} STDERR] ${text}`);
            
            // 通过WebSocket发送错误输出
            io.emit('taskOutput', {
                alchemy_id: alchemy_id,
                output: `[停止请求错误] ${text}`,
                encoding: 'utf8',
                isError: true
            });
        });
        
        // 等待进程完成
        pythonProcess.on('close', (code) => {
            console.log(`[停止任务 ${alchemy_id}] 进程退出，代码: ${code}`);
            
            // 发送任务状态更新
            io.emit('taskStatus', {
                alchemy_id: alchemy_id,
                status: 'stopped',
                message: '任务已停止'
            });
            
            // 通过WebSocket发送完成消息
            io.emit('taskOutput', {
                alchemy_id: alchemy_id,
                output: `\n[停止请求完成] 退出代码: ${code}\n`,
                encoding: 'utf8'
            });
            
            // 刷新可恢复任务列表
            io.emit('refreshResumableTasks');
        });
        
        // 立即返回成功响应，不等待进程完成
        res.json({
            success: true,
            message: '已发送停止请求',
            alchemy_id: alchemy_id,
            method: 'cancel_command'
        });
        
    } catch (error) {
        console.error('停止任务失败:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// 添加保存下一轮迭代配置API
app.post('/api/save-next-iteration-config', async (req, res) => {
    try {
        const { alchemy_id, config } = req.body;
        
        if (!alchemy_id) {
            return res.status(400).json({ 
                success: false, 
                error: '缺少任务ID参数' 
            });
        }
        
        if (!config || typeof config !== 'object') {
            return res.status(400).json({ 
                success: false, 
                error: '配置数据无效' 
            });
        }
        
        // 构建任务目录路径
        const workDir = path.join(__dirname, '..');
        const alchemyDir = path.join(workDir, 'work_dir', 'data_alchemy');
        const runsDir = path.join(alchemyDir, 'alchemy_runs');
        const taskDir = path.join(runsDir, `alchemy_${alchemy_id}`);
        
        // 检查任务目录是否存在
        if (!fs.existsSync(taskDir)) {
            return res.status(404).json({ 
                success: false, 
                error: `任务 ${alchemy_id} 不存在` 
            });
        }
        
        // 保存配置文件
        const configPath = path.join(taskDir, 'next_iteration_config.json');
        await fsPromises.writeFile(configPath, JSON.stringify(config, null, 2), 'utf8');
        
        console.log(`已保存任务 ${alchemy_id} 的下一轮迭代配置`);
        
        res.json({
            success: true,
            message: `已保存任务 ${alchemy_id} 的下一轮迭代配置`
        });
    } catch (error) {
        console.error('保存下一轮迭代配置失败:', error);
        res.status(500).json({ 
            success: false, 
            error: `保存配置失败: ${error.message}` 
        });
    }
});

// 启动服务器
const PORT = config.port || 3000;
http.listen(PORT, () => {
    console.log(`服务器运行在 http://localhost:${PORT}`);
    console.log(`字符编码: ${Buffer.isEncoding('utf8') ? 'UTF-8支持正常' : 'UTF-8支持异常'}`);
    watchDirs.forEach(dir => {
        console.log(`监控目录: ${dir.fullPath}`);
    });
});

// 在应用退出时关闭所有文件监视器
process.on('SIGINT', () => {
    console.log('正在关闭服务器...');
    
    // 关闭所有文件监视器
    watchers.forEach(watcher => {
        try {
            watcher.close();
        } catch (err) {
            console.error('关闭文件监视器失败:', err);
        }
    });
    
    // 关闭所有子进程
    console.log(`正在终止 ${activeProcesses.size} 个活动子进程...`);
    for (const proc of activeProcesses) {
        try {
            // 在Windows上，需要使用特殊方法终止进程树
            if (process.platform === 'win32') {
                // 使用taskkill终止进程及其子进程
                require('child_process').execSync(`taskkill /pid ${proc.pid} /T /F`, {
                    stdio: 'ignore'
                });
            } else {
                // 在Unix系统上，发送SIGTERM信号
                proc.kill('SIGTERM');
                
                // 如果进程没有在1秒内退出，发送SIGKILL
                setTimeout(() => {
                    try {
                        if (!proc.killed) {
                            proc.kill('SIGKILL');
                        }
                    } catch (e) {
                        // 忽略错误，可能进程已经退出
                    }
                }, 1000);
            }
        } catch (err) {
            console.error(`终止子进程 ${proc.pid} 失败:`, err);
        }
    }
    
    // 等待所有子进程终止
    const waitForProcesses = new Promise((resolve) => {
        if (activeProcesses.size === 0) {
            resolve();
            return;
        }
        
        console.log('等待子进程终止...');
        const checkInterval = setInterval(() => {
            if (activeProcesses.size === 0) {
                clearInterval(checkInterval);
                resolve();
            }
        }, 100);
        
        // 最多等待3秒
        setTimeout(() => {
            clearInterval(checkInterval);
            if (activeProcesses.size > 0) {
                console.warn(`${activeProcesses.size} 个子进程未能正常终止`);
            }
            resolve();
        }, 3000);
    });
    
    // 等待子进程终止后关闭Socket.IO和HTTP服务器
    waitForProcesses.then(() => {
        // 关闭所有 Socket.IO 连接
        io.close(() => {
            console.log('Socket.IO 连接已关闭');
            
            // 关闭 HTTP 服务器
            http.close(() => {
                console.log('HTTP 服务器已关闭');
                process.exit(0);
            });
        });
    });
    
    // 添加超时机制，防止进程卡住
    setTimeout(() => {
        console.log('关闭超时，强制退出进程');
        process.exit(1);
    }, 5000); // 5秒后强制退出
});