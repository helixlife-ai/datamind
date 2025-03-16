const fs = require('fs');
const path = require('path');

// 设置explorer路由
function setupExplorerRoute(app, watchDirs, config) {
    // 创建explorer路由
    app.get('/explorer', (req, res) => {
        try {
            // 读取explorer.html模板
            const templatePath = path.join(__dirname, '../public/explorer.html');
            let explorerHtml = fs.readFileSync(templatePath, 'utf8');
            
            // 设置正确的Content-Type
            res.setHeader('Content-Type', 'text/html; charset=utf-8');
            res.send(explorerHtml);
        } catch (err) {
            console.error('生成explorer页面时出错:', err);
            res.status(500).send('生成explorer页面时出错');
        }
    });

    // 添加获取文件内容的API端点
    app.get('/api/file', (req, res) => {
        try {
            const { dir, path: filePath } = req.query;
            
            if (!dir || !filePath) {
                return res.status(400).json({ error: '缺少必要参数' });
            }
            
            // 查找匹配的监控目录
            const watchDir = watchDirs.find(d => d.path === dir);
            if (!watchDir) {
                return res.status(404).json({ error: '未找到指定目录' });
            }
            
            // 构建完整的文件路径
            const fullPath = path.join(watchDir.fullPath, filePath);
            
            // 检查文件是否存在
            if (!fs.existsSync(fullPath)) {
                return res.status(404).json({ error: '文件不存在' });
            }
            
            // 检查是否是目录
            const stats = fs.statSync(fullPath);
            if (stats.isDirectory()) {
                return res.status(400).json({ error: '请求的路径是一个目录' });
            }
            
            // 读取文件内容
            const content = fs.readFileSync(fullPath, 'utf8');
            
            // 返回文件内容
            res.json({ content });
        } catch (err) {
            console.error('读取文件内容时出错:', err);
            res.status(500).json({ error: '读取文件内容时出错: ' + err.message });
        }
    });
    
    // 添加获取文件结构的API端点
    app.get('/api/fileStructure', (req, res) => {
        try {
            const structure = {};
            watchDirs.forEach(dir => {
                structure[dir.path] = {
                    name: dir.name,
                    description: dir.description,
                    files: buildFileSystemStructure(dir.fullPath)
                };
            });
            res.json(structure);
        } catch (err) {
            console.error('获取文件结构时出错:', err);
            res.status(500).json({ error: '获取文件结构时出错: ' + err.message });
        }
    });
    
    // 添加获取文件变更历史的API端点
    app.get('/api/fileChanges', (req, res) => {
        try {
            const { dir, path: filePath } = req.query;
            
            if (!dir || !filePath) {
                return res.status(400).json({ error: '缺少必要参数' });
            }
            
            // 查找匹配的监控目录
            const watchDir = watchDirs.find(d => d.path === dir);
            if (!watchDir) {
                return res.status(404).json({ error: '未找到指定目录' });
            }
            
            // 构建完整的文件路径
            const fullPath = path.join(watchDir.fullPath, filePath);
            
            // 检查文件是否存在
            if (!fs.existsSync(fullPath)) {
                return res.status(404).json({ error: '文件不存在' });
            }
            
            // 这里可以实现获取文件变更历史的逻辑
            // 由于没有实际的变更历史存储，这里返回一个空数组
            res.json({ changes: [] });
        } catch (err) {
            console.error('获取文件变更历史时出错:', err);
            res.status(500).json({ error: '获取文件变更历史时出错: ' + err.message });
        }
    });
}

// 构建文件系统结构
function buildFileSystemStructure(dirPath) {
    const result = {};
    
    try {
        const items = fs.readdirSync(dirPath);
        
        items.forEach(item => {
            const itemPath = path.join(dirPath, item);
            const stats = fs.statSync(itemPath);
            
            if (stats.isDirectory()) {
                result[item] = buildFileSystemStructure(itemPath);
            } else {
                result[item] = true;
            }
        });
    } catch (err) {
        console.error(`构建文件系统结构时出错 (${dirPath}):`, err);
    }
    
    return result;
}

module.exports = { setupExplorerRoute, buildFileSystemStructure }; 