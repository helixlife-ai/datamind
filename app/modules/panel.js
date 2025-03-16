const fs = require('fs');
const path = require('path');

// 设置panel路由
function setupPanelRoute(app, watchDirs, config) {
    // 创建panel路由
    app.get('/panel', (req, res) => {
        try {
            // 读取panel.html模板
            const templatePath = path.join(__dirname, '../public/panel.html');
            let panelHtml = fs.readFileSync(templatePath, 'utf8');
            
            // 收集系统状态信息
            const systemStatus = collectSystemStatus(watchDirs, config);
            
            // 生成状态卡片HTML
            const cardsHtml = generateStatusCards(systemStatus);
            
            // 在panel.html中替换状态卡片部分
            const rowStartTag = '<div class="row g-4">';
            const rowStartIdx = panelHtml.indexOf(rowStartTag);
            
            if (rowStartIdx !== -1) {
                // 找到起始标签后，查找下一个 </div> 标签
                const rowContentStartIdx = rowStartIdx + rowStartTag.length;
                const rowEndIdx = panelHtml.indexOf('</section>', rowContentStartIdx);
                
                if (rowEndIdx !== -1) {
                    // 在 </section> 之前找到最后一个 </div>
                    const lastDivBeforeSectionEnd = panelHtml.lastIndexOf('</div>', rowEndIdx);
                    
                    if (lastDivBeforeSectionEnd !== -1 && lastDivBeforeSectionEnd > rowContentStartIdx) {
                        // 找到了合适的替换位置
                        const beforeContent = panelHtml.substring(0, rowContentStartIdx);
                        const afterContent = panelHtml.substring(lastDivBeforeSectionEnd);
                        
                        // 替换内容
                        panelHtml = beforeContent + '\n' + cardsHtml + '\n            ' + afterContent;
                        console.log('成功替换panel.html中的状态卡片部分');
                    } else {
                        // 如果找不到合适的 </div>，直接在 row 开始标签后插入内容
                        const beforeContent = panelHtml.substring(0, rowContentStartIdx);
                        const afterContent = panelHtml.substring(rowContentStartIdx);
                        
                        panelHtml = beforeContent + '\n' + cardsHtml + '\n            ' + afterContent;
                        console.log('已在row标签后插入状态卡片内容');
                    }
                } else {
                    console.error('无法找到</section>标签');
                    // 尝试直接替换loading-indicator
                    const loadingIndicator = '<div id="loading-indicator"';
                    const loadingStartIdx = panelHtml.indexOf(loadingIndicator);
                    
                    if (loadingStartIdx !== -1) {
                        const loadingEndIdx = panelHtml.indexOf('</div>', loadingStartIdx);
                        if (loadingEndIdx !== -1) {
                            const nextEndDiv = panelHtml.indexOf('</div>', loadingEndIdx + 6);
                            if (nextEndDiv !== -1) {
                                const beforeContent = panelHtml.substring(0, loadingStartIdx);
                                const afterContent = panelHtml.substring(nextEndDiv + 6);
                                panelHtml = beforeContent + cardsHtml + afterContent;
                                console.log('已替换loading-indicator为状态卡片内容');
                            }
                        }
                    }
                }
            } else {
                console.error('无法在panel.html中找到row g-4标签');
                
                // 尝试查找dashboard部分
                const dashboardSection = '<section id="dashboard"';
                const dashboardSectionIdx = panelHtml.indexOf(dashboardSection);
                
                if (dashboardSectionIdx !== -1) {
                    // 在dashboard部分中插入内容
                    const sectionTitleEnd = panelHtml.indexOf('</h3>', dashboardSectionIdx);
                    
                    if (sectionTitleEnd !== -1) {
                        const insertPoint = sectionTitleEnd + 5; // </h3>后
                        const beforeContent = panelHtml.substring(0, insertPoint);
                        const afterContent = panelHtml.substring(insertPoint);
                        
                        panelHtml = beforeContent + 
                                     '\n                <div class="row g-4">\n' + 
                                     cardsHtml + 
                                     '\n                </div>\n' + 
                                     afterContent;
                        console.log('已在dashboard部分插入状态卡片内容');
                    }
                }
            }
            
            // 设置正确的Content-Type
            res.setHeader('Content-Type', 'text/html; charset=utf-8');
            res.send(panelHtml);
        } catch (err) {
            console.error('生成panel页面时出错:', err);
            res.status(500).send('生成panel页面时出错');
        }
    });

    // 添加刷新panel的API端点
    app.post('/api/panel/refresh', (req, res) => {
        try {
            // 清除缓存，强制重新收集系统状态
            console.log('刷新panel页面');
            res.json({ success: true, message: '已刷新panel页面' });
        } catch (err) {
            console.error('刷新panel页面时出错:', err);
            res.status(500).json({ success: false, error: '刷新panel页面时出错' });
        }
    });
    
    // 添加获取系统状态的API端点
    app.get('/api/panel/status', (req, res) => {
        try {
            const systemStatus = collectSystemStatus(watchDirs, config);
            res.json({ success: true, data: systemStatus });
        } catch (err) {
            console.error('获取系统状态时出错:', err);
            res.status(500).json({ success: false, error: '获取系统状态时出错' });
        }
    });
    
    // 添加系统操作的API端点
    app.post('/api/panel/action', (req, res) => {
        try {
            const { action, params } = req.body;
            
            switch (action) {
                case 'restart':
                    // 重启服务
                    console.log('收到重启服务请求');
                    res.json({ success: true, message: '服务重启请求已接收，服务将在5秒后重启' });
                    setTimeout(() => {
                        process.exit(0); // 假设有进程管理器会自动重启服务
                    }, 5000);
                    break;
                    
                case 'clearCache':
                    // 清除缓存
                    console.log('收到清除缓存请求');
                    // 这里可以添加清除缓存的逻辑
                    res.json({ success: true, message: '缓存已清除' });
                    break;
                    
                default:
                    res.status(400).json({ success: false, error: '未知操作' });
            }
        } catch (err) {
            console.error('执行系统操作时出错:', err);
            res.status(500).json({ success: false, error: '执行系统操作时出错' });
        }
    });
}

// 收集系统状态信息
function collectSystemStatus(watchDirs, config) {
    const status = {
        system: {
            uptime: process.uptime(),
            memory: process.memoryUsage(),
            nodeVersion: process.version,
            platform: process.platform,
            cpuUsage: process.cpuUsage()
        },
        directories: [],
        config: {
            port: config.port,
            apiKeys: Object.keys(config.apiKeys || {}).length,
            watchDirsCount: watchDirs.length
        }
    };
    
    // 收集监控目录信息
    watchDirs.forEach(dir => {
        try {
            const stats = fs.statSync(dir.fullPath);
            const dirInfo = {
                name: dir.name,
                path: dir.path,
                size: calculateDirSize(dir.fullPath),
                fileCount: countFiles(dir.fullPath),
                lastModified: stats.mtime
            };
            status.directories.push(dirInfo);
        } catch (err) {
            console.error(`获取目录 ${dir.path} 信息时出错:`, err);
            status.directories.push({
                name: dir.name,
                path: dir.path,
                error: err.message
            });
        }
    });
    
    return status;
}

// 计算目录大小
function calculateDirSize(dirPath) {
    let totalSize = 0;
    
    try {
        const files = fs.readdirSync(dirPath);
        
        for (const file of files) {
            const filePath = path.join(dirPath, file);
            const stats = fs.statSync(filePath);
            
            if (stats.isDirectory()) {
                totalSize += calculateDirSize(filePath);
            } else {
                totalSize += stats.size;
            }
        }
    } catch (err) {
        console.error(`计算目录 ${dirPath} 大小时出错:`, err);
    }
    
    return totalSize;
}

// 统计目录中的文件数量
function countFiles(dirPath) {
    let count = 0;
    
    try {
        const files = fs.readdirSync(dirPath);
        
        for (const file of files) {
            const filePath = path.join(dirPath, file);
            const stats = fs.statSync(filePath);
            
            if (stats.isDirectory()) {
                count += countFiles(filePath);
            } else {
                count++;
            }
        }
    } catch (err) {
        console.error(`统计目录 ${dirPath} 文件数量时出错:`, err);
    }
    
    return count;
}

// 格式化文件大小
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    
    return (bytes / Math.pow(1024, i)).toFixed(2) + ' ' + units[i];
}

// 格式化时间
function formatTime(seconds) {
    const days = Math.floor(seconds / (3600 * 24));
    const hours = Math.floor((seconds % (3600 * 24)) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    let result = '';
    if (days > 0) result += `${days}天 `;
    if (hours > 0) result += `${hours}小时 `;
    if (minutes > 0) result += `${minutes}分钟 `;
    if (secs > 0 || result === '') result += `${secs}秒`;
    
    return result;
}

// 生成状态卡片HTML
function generateStatusCards(status) {
    let cardsHtml = '';
    
    // 系统状态卡片
    cardsHtml += `
    <div class="col-12 col-md-6 col-lg-4">
        <div class="card h-100">
            <div class="card-header bg-primary text-white">
                <h5 class="card-title mb-0">系统状态</h5>
            </div>
            <div class="card-body">
                <ul class="list-group list-group-flush">
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        运行时间
                        <span class="badge bg-primary rounded-pill">${formatTime(status.system.uptime)}</span>
                    </li>
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        内存使用
                        <span class="badge bg-primary rounded-pill">${formatFileSize(status.system.memory.rss)}</span>
                    </li>
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        Node版本
                        <span class="badge bg-primary rounded-pill">${status.system.nodeVersion}</span>
                    </li>
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        平台
                        <span class="badge bg-primary rounded-pill">${status.system.platform}</span>
                    </li>
                </ul>
            </div>
            <div class="card-footer">
                <button class="btn btn-sm btn-outline-primary" id="restart-server">重启服务</button>
                <button class="btn btn-sm btn-outline-secondary" id="clear-cache">清除缓存</button>
            </div>
        </div>
    </div>
    `;
    
    // 配置信息卡片
    cardsHtml += `
    <div class="col-12 col-md-6 col-lg-4">
        <div class="card h-100">
            <div class="card-header bg-info text-white">
                <h5 class="card-title mb-0">配置信息</h5>
            </div>
            <div class="card-body">
                <ul class="list-group list-group-flush">
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        服务端口
                        <span class="badge bg-info rounded-pill">${status.config.port}</span>
                    </li>
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        API密钥数量
                        <span class="badge bg-info rounded-pill">${status.config.apiKeys}</span>
                    </li>
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        监控目录数量
                        <span class="badge bg-info rounded-pill">${status.config.watchDirsCount}</span>
                    </li>
                </ul>
            </div>
            <div class="card-footer">
                <button class="btn btn-sm btn-outline-info" id="edit-config">编辑配置</button>
            </div>
        </div>
    </div>
    `;
    
    // 目录状态卡片
    status.directories.forEach(dir => {
        cardsHtml += `
        <div class="col-12 col-md-6 col-lg-4">
            <div class="card h-100">
                <div class="card-header bg-success text-white">
                    <h5 class="card-title mb-0">${dir.name}</h5>
                </div>
                <div class="card-body">
                    ${dir.error ? `
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-triangle-fill"></i> 错误: ${dir.error}
                    </div>
                    ` : `
                    <ul class="list-group list-group-flush">
                        <li class="list-group-item d-flex justify-content-between align-items-center">
                            路径
                            <span class="badge bg-success rounded-pill">${dir.path}</span>
                        </li>
                        <li class="list-group-item d-flex justify-content-between align-items-center">
                            大小
                            <span class="badge bg-success rounded-pill">${formatFileSize(dir.size)}</span>
                        </li>
                        <li class="list-group-item d-flex justify-content-between align-items-center">
                            文件数量
                            <span class="badge bg-success rounded-pill">${dir.fileCount}</span>
                        </li>
                        <li class="list-group-item d-flex justify-content-between align-items-center">
                            最后修改
                            <span class="badge bg-success rounded-pill">${new Date(dir.lastModified).toLocaleString()}</span>
                        </li>
                    </ul>
                    `}
                </div>
                <div class="card-footer">
                    <button class="btn btn-sm btn-outline-success" data-dir="${dir.path}" id="explore-dir">浏览目录</button>
                </div>
            </div>
        </div>
        `;
    });
    
    return cardsHtml;
}

module.exports = { setupPanelRoute }; 