const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const fsPromises = require('fs').promises;

/**
 * 聊天会话管理类
 */
class ChatSessionManager {
    /**
     * 构造函数
     * @param {Object} config - 配置对象
     */
    constructor(config) {
        // 尝试从顶级配置中查找聊天记录目录
        if (config.chatRecordDir && config.chatRecordDir.path) {
            this.chatRecordDir = config.chatRecordDir.path;
            this.chatRecordName = config.chatRecordDir.name || "聊天记录";
            this.fullChatRecordDir = path.join(__dirname, '..', this.chatRecordDir);
            console.log(`使用顶级配置的聊天记录目录: ${this.chatRecordDir}`);
        } 
        // 向后兼容：从watchDirs中查找
        else {
            const chatDir = config.watchDirs.find(dir => dir.name === "聊天记录");
            
            if (chatDir) {
                this.chatRecordDir = chatDir.path;
                this.chatRecordName = chatDir.name;
                this.fullChatRecordDir = path.join(__dirname, '..', this.chatRecordDir);
                console.log(`从watchDirs中使用聊天记录目录: ${this.chatRecordDir}`);
            } else {
                // 如果配置中没有找到，使用默认目录
                this.chatRecordDir = "../work_dir/data_alchemy/chat_records";
                this.chatRecordName = "聊天记录";
                this.fullChatRecordDir = path.join(__dirname, '..', this.chatRecordDir);
                console.warn(`配置中未找到聊天记录目录，使用默认路径: ${this.chatRecordDir}`);
            }
        }
        
        this.sessions = new Map();
        this.initDirectory();
    }

    /**
     * 初始化聊天记录目录
     */
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

    /**
     * 生成会话ID
     * @returns {string} 生成的会话ID
     */
    generateSessionId() {
        return crypto.randomBytes(16).toString('hex');
    }

    /**
     * 获取或创建会话
     * @param {string} sessionId - 会话ID
     * @returns {Object} 包含会话ID和会话对象的对象
     */
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

    /**
     * 加载聊天历史
     * @param {string} sessionId - 会话ID
     * @returns {Array} 聊天消息数组
     */
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

    /**
     * 保存聊天历史
     * @param {string} sessionId - 会话ID
     * @param {Array} messages - 聊天消息数组
     */
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

    /**
     * 清理不活跃的会话
     * @param {number} maxAgeMs - 最大不活跃时间（毫秒）
     */
    cleanupSessions(maxAgeMs = 24 * 60 * 60 * 1000) {
        const now = Date.now();
        for (const [sessionId, session] of this.sessions.entries()) {
            if (now - session.lastActivity > maxAgeMs) {
                this.sessions.delete(sessionId);
            }
        }
    }
}

/**
 * 设置聊天相关路由
 * @param {Object} app - Express应用实例
 * @param {ChatSessionManager} chatManager - 聊天会话管理器实例
 */
function setupChatRoutes(app, chatManager) {
    // 创建chat页面路由
    app.get('/chat', (req, res) => {
        try {
            // 读取chat.html模板
            const templatePath = path.join(__dirname, '../public/chat.html');
            let chatHtml = fs.readFileSync(templatePath, 'utf8');
            
            // 设置正确的Content-Type
            res.setHeader('Content-Type', 'text/html; charset=utf-8');
            res.send(chatHtml);
        } catch (err) {
            console.error('生成chat页面时出错:', err);
            res.status(500).send('生成chat页面时出错');
        }
    });

    // 添加API端点，用于访问聊天记录文件
    app.get('/api/chat-records/:sessionId/:format', async (req, res) => {
        try {
            const { sessionId, format } = req.params;
            
            // 安全检查：验证sessionId格式，防止路径遍历攻击
            if (!sessionId.match(/^[a-f0-9]{32}$/)) {
                return res.status(400).send('无效的会话ID格式');
            }
            
            // 验证格式参数
            if (format !== 'json' && format !== 'txt') {
                return res.status(400).send('无效的格式参数，只支持json或txt');
            }
            
            // 构建文件路径
            const filePath = path.join(chatManager.fullChatRecordDir, `${sessionId}.${format}`);
            
            // 检查文件是否存在
            if (!fs.existsSync(filePath)) {
                console.error(`请求的聊天记录不存在: ${filePath}`);
                return res.status(404).send('请求的聊天记录不存在');
            }
            
            // 设置Content-Type
            if (format === 'json') {
                res.setHeader('Content-Type', 'application/json; charset=utf-8');
            } else {
                res.setHeader('Content-Type', 'text/plain; charset=utf-8');
            }
            
            // 发送文件
            const fileStream = fs.createReadStream(filePath);
            fileStream.pipe(res);
            
        } catch (err) {
            console.error('访问聊天记录文件时出错:', err);
            res.status(500).send('访问聊天记录文件时出错');
        }
    });

    // 添加API端点，用于获取所有聊天记录列表
    app.get('/api/chat-records', async (req, res) => {
        try {
            // 读取聊天记录目录中的所有文件
            const files = await fsPromises.readdir(chatManager.fullChatRecordDir);
            
            // 过滤出JSON文件（聊天记录）
            const jsonFiles = files.filter(file => file.endsWith('.json') && !file.startsWith('README'));
            
            // 收集聊天记录信息
            const records = [];
            
            for (const file of jsonFiles) {
                const sessionId = file.replace('.json', '');
                const filePath = path.join(chatManager.fullChatRecordDir, file);
                
                try {
                    // 获取文件状态信息
                    const stats = await fsPromises.stat(filePath);
                    
                    // 读取文件内容以获取第一条消息作为预览
                    const data = await fsPromises.readFile(filePath, 'utf8');
                    const messages = JSON.parse(data);
                    
                    // 获取第一条用户消息作为预览
                    const firstUserMessage = messages.find(msg => msg.role === 'user');
                    const preview = firstUserMessage ? 
                        (firstUserMessage.content.length > 50 ? 
                            firstUserMessage.content.substring(0, 50) + '...' : 
                            firstUserMessage.content) : 
                        '无预览';
                    
                    records.push({
                        sessionId,
                        messageCount: messages.length,
                        lastModified: stats.mtime,
                        preview,
                        jsonUrl: `/api/chat-records/${sessionId}/json`,
                        txtUrl: `/api/chat-records/${sessionId}/txt`
                    });
                } catch (err) {
                    console.error(`读取聊天记录 ${file} 时出错:`, err);
                }
            }
            
            // 按最后修改时间排序，最新的排在前面
            records.sort((a, b) => new Date(b.lastModified) - new Date(a.lastModified));
            
            res.json({
                success: true,
                records,
                total: records.length
            });
            
        } catch (err) {
            console.error('获取聊天记录列表时出错:', err);
            res.status(500).json({
                success: false,
                error: '获取聊天记录列表时出错'
            });
        }
    });
}

module.exports = {
    ChatSessionManager,
    setupChatRoutes
}; 