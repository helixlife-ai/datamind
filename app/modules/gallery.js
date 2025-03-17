const fs = require('fs');
const path = require('path');

// 设置gallery路由
function setupGalleryRoute(app, watchDirs, config, io) {
    // 创建gallery路由
    app.get('/gallery', (req, res) => {
        try {
            // 读取gallery.html模板
            const templatePath = path.join(__dirname, '../public/gallery.html');
            let galleryHtml = fs.readFileSync(templatePath, 'utf8');
            
            // 设置正确的Content-Type
            res.setHeader('Content-Type', 'text/html; charset=utf-8');
            res.send(galleryHtml);
        } catch (err) {
            console.error('生成gallery页面时出错:', err);
            res.status(500).send('生成gallery页面时出错');
        }
    });

    // 添加刷新gallery的API端点
    app.post('/api/gallery/refresh', (req, res) => {
        try {
            // 收集所有炼丹目录中的制品信息
            const artifacts = collectAllArtifacts(watchDirs);
            
            // 通过Socket.IO广播更新的卡片数据
            io.emit('gallery:artifacts', artifacts);
            
            console.log('刷新gallery页面');
            res.json({ success: true, message: '已刷新gallery页面' });
        } catch (err) {
            console.error('刷新gallery页面时出错:', err);
            res.status(500).json({ success: false, error: '刷新gallery页面时出错' });
        }
    });
    
    // 添加新的API端点，用于访问制品文件
    app.get('/api/artifacts/:alchemyDir/:iterPath(*)', (req, res) => {
        try {
            const { alchemyDir, iterPath } = req.params;
            
            // 查找alchemy_runs目录
            let alchemyRunsDir = watchDirs.find(dir => dir.path.endsWith('alchemy_runs'));
            let alchemyPath = null;
            
            if (alchemyRunsDir) {
                // 直接使用找到的alchemy_runs目录
                alchemyPath = alchemyRunsDir.fullPath;
            } else {
                // 查找是否作为子目录存在
                for (const dir of watchDirs) {
                    const possiblePath = path.join(dir.fullPath, 'alchemy_runs');
                    if (fs.existsSync(possiblePath)) {
                        alchemyPath = possiblePath;
                        break;
                    }
                }
            }
            
            if (!alchemyPath) {
                return res.status(404).send('未找到alchemy_runs目录');
            }
            
            // 构建完整的文件路径
            const filePath = path.join(alchemyPath, alchemyDir, iterPath);
            
            // 检查文件是否存在
            if (!fs.existsSync(filePath)) {
                console.error(`请求的文件不存在: ${filePath}`);
                return res.status(404).send('请求的文件不存在');
            }
            
            // 根据文件扩展名设置Content-Type
            const ext = path.extname(filePath).toLowerCase();
            let contentType = 'text/plain';
            
            switch (ext) {
                case '.html':
                    contentType = 'text/html; charset=utf-8';
                    break;
                case '.css':
                    contentType = 'text/css';
                    break;
                case '.js':
                    contentType = 'application/javascript';
                    break;
                case '.json':
                    contentType = 'application/json';
                    break;
                case '.png':
                    contentType = 'image/png';
                    break;
                case '.jpg':
                case '.jpeg':
                    contentType = 'image/jpeg';
                    break;
                case '.gif':
                    contentType = 'image/gif';
                    break;
                case '.svg':
                    contentType = 'image/svg+xml';
                    break;
            }
            
            res.setHeader('Content-Type', contentType);
            
            // 发送文件
            const fileStream = fs.createReadStream(filePath);
            fileStream.pipe(res);
            
        } catch (err) {
            console.error('访问制品文件时出错:', err);
            res.status(500).send('访问制品文件时出错');
        }
    });
    
    // 设置Socket.IO事件处理
    io.on('connection', (socket) => {
        console.log('Gallery客户端连接');
        
        // 客户端请求制品数据
        socket.on('gallery:requestArtifacts', () => {
            try {
                // 收集所有炼丹目录中的制品信息
                const artifacts = collectAllArtifacts(watchDirs);
                
                // 发送制品数据给客户端
                socket.emit('gallery:artifacts', artifacts);
                console.log('已发送制品数据给客户端');
            } catch (err) {
                console.error('发送制品数据时出错:', err);
                socket.emit('gallery:error', { message: '获取制品数据失败' });
            }
        });
        
        // 监听断开连接事件
        socket.on('disconnect', () => {
            console.log('Gallery客户端断开连接');
        });
    });
    
    // 设置文件监视器，监控alchemy_runs目录的变化
    setupAlchemyWatcher(watchDirs, io);
}

// 设置alchemy_runs目录监视器
function setupAlchemyWatcher(watchDirs, io) {
    // 查找alchemy_runs目录
    let alchemyRunsDir = watchDirs.find(dir => dir.path.endsWith('alchemy_runs'));
    let alchemyPath = null;
    
    if (alchemyRunsDir) {
        // 直接使用找到的alchemy_runs目录
        alchemyPath = alchemyRunsDir.fullPath;
    } else {
        // 查找是否作为子目录存在
        for (const dir of watchDirs) {
            const possiblePath = path.join(dir.fullPath, 'alchemy_runs');
            if (fs.existsSync(possiblePath)) {
                alchemyPath = possiblePath;
                break;
            }
        }
    }
    
    if (!alchemyPath) {
        console.warn('未找到alchemy_runs目录，无法监控制品变化');
        return;
    }
    
    // 使用fs.watch监控目录变化
    const watcher = fs.watch(alchemyPath, { recursive: true }, (eventType, filename) => {
        // 只关注status.json文件的变化
        if (filename && filename.includes('status.json')) {
            console.log(`检测到制品变化: ${filename}`);
            
            // 延迟一小段时间，确保文件写入完成
            setTimeout(() => {
                try {
                    // 收集所有炼丹目录中的制品信息
                    const artifacts = collectAllArtifacts(watchDirs);
                    
                    // 通过Socket.IO广播更新的卡片数据
                    io.emit('gallery:artifacts', artifacts);
                    console.log('已广播更新的制品数据');
                } catch (err) {
                    console.error('广播制品数据时出错:', err);
                }
            }, 500);
        }
    });
    
    // 处理监视器错误
    watcher.on('error', (error) => {
        console.error('监控alchemy_runs目录时出错:', error);
    });
    
    console.log(`已开始监控alchemy_runs目录: ${alchemyPath}`);
    
    // 返回监视器，以便在需要时关闭
    return watcher;
}

// 收集所有炼丹目录中的制品信息
function collectAllArtifacts(watchDirs) {
    const artifacts = [];
    
    // 查找所有炼丹目录
    let alchemyDir = watchDirs.find(dir => dir.path.endsWith('alchemy_runs'));
    let alchemyPath = null;
    
    if (alchemyDir) {
        // 直接使用找到的alchemy_runs目录
        alchemyPath = alchemyDir.fullPath;
        console.log('找到alchemy_runs目录:', alchemyPath);
    } else {
        // 查找是否作为子目录存在
        for (const dir of watchDirs) {
            const possiblePath = path.join(dir.fullPath, 'alchemy_runs');
            if (fs.existsSync(possiblePath)) {
                alchemyPath = possiblePath;
                alchemyDir = {
                    ...dir,
                    fullPath: possiblePath,
                    path: path.join(dir.path, 'alchemy_runs')
                };
                console.log('找到alchemy_runs子目录:', alchemyPath);
                break;
            }
        }
    }
    
    if (!alchemyPath) {
        console.log('未找到alchemy_runs目录');
        return artifacts;
    }
    
    // 遍历所有炼丹目录
    const alchemyDirs = fs.readdirSync(alchemyPath);
    console.log('炼丹目录列表:', alchemyDirs);
    
    alchemyDirs.forEach(dirName => {
        if (dirName.startsWith('alchemy_')) {
            const alchemyId = dirName.split('alchemy_')[1];
            const statusPath = path.join(alchemyDir.fullPath, dirName, 'artifacts', 'status.json');
            
            if (fs.existsSync(statusPath)) {
                try {
                    const statusInfo = JSON.parse(fs.readFileSync(statusPath, 'utf8'));
                    
                    // 获取所有迭代信息
                    const iterations = statusInfo.iterations || [];
                    iterations.forEach(iteration => {
                        // 检查输出路径是否存在
                        if (!iteration.output) {
                            console.log(`迭代 ${iteration.iteration} 没有输出路径，跳过`);
                            return;
                        }
                        
                        // 构建正确的访问URL
                        // 从 iterations/iterX/artifact/output/artifact_iterX.html 转换为可访问的URL
                        const artifactUrl = `/api/artifacts/${dirName}/${iteration.output}`;
                        
                        artifacts.push({
                            alchemyId,
                            alchemyDir: dirName,  // 添加alchemyDir字段，用于构建screenshot URL
                            iteration: iteration.iteration,
                            timestamp: iteration.timestamp,
                            query: iteration.query || statusInfo.original_query || "未知查询",
                            outputPath: iteration.output,
                            // 添加screenshot字段
                            screenshot: iteration.screenshot || null,
                            // 使用新构建的URL
                            relativePath: artifactUrl
                        });
                    });
                } catch (err) {
                    console.error(`读取${statusPath}时出错:`, err);
                }
            }
        }
    });
    
    // 按时间戳排序，最新的排在前面
    artifacts.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    
    console.log('收集到的制品数量:', artifacts.length);
    return artifacts;
}

// 生成作品卡片HTML
function generateArtifactCards(artifacts) {
    let cardsHtml = '';
    
    console.log('收集到的制品数量:', artifacts.length);
    
    // 如果没有制品，显示提示信息
    if (artifacts.length === 0) {
        console.log('没有找到制品，显示提示信息');
        return `
        <div class="col-12 text-center py-5">
            <p class="text-muted">暂无制品，请先创建炼丹任务</p>
        </div>
        `;
    }
    
    console.log(`正在生成${artifacts.length}个作品卡片`);
    
    // 为每个制品生成卡片
    artifacts.forEach((artifact, index) => {
        console.log(`生成第${index+1}个卡片，alchemyId: ${artifact.alchemyId}, 查询: ${artifact.query.substring(0, 30)}...`);
        
        // 截断过长的查询文本
        const queryText = artifact.query.length > 80 
            ? artifact.query.substring(0, 80) + '...' 
            : artifact.query;
            
        // 格式化时间戳
        const date = new Date(artifact.timestamp);
        const formattedDate = `${date.getFullYear()}-${(date.getMonth()+1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')}`;
        
        // 生成预览图URL - 优先使用screenshot字段，如果不存在则使用默认图片
        const previewImgUrl = artifact.screenshot 
            ? `/api/artifacts/${artifact.alchemyDir}/${artifact.screenshot}`
            : "https://images.unsplash.com/photo-1581291518633-83b4ebd1d83e?ixlib=rb-4.0.3&auto=format&fit=crop&w=600&h=400&q=80";
        
        const cardHtml = `
        <div class="col-12 col-sm-6 col-md-4 col-lg-3 col-xl-2">
            <div class="card h-100">
                <div class="card-img-container">
                    <img src="${previewImgUrl}" alt="制品预览" class="card-img" loading="lazy">
                </div>
                <div class="card-body">
                    <h4 class="card-title">炼丹 #${artifact.alchemyId}</h4>
                    <p class="card-text">${queryText}</p>
                    <p class="card-text text-muted small">迭代: ${artifact.iteration} | 创建于: ${formattedDate}</p>
                </div>
                <div class="card-footer bg-white border-top-0">
                    <a href="${artifact.relativePath}" class="btn btn-primary" target="_blank">查看详情</a>
                </div>
            </div>
        </div>
        `;
        cardsHtml += cardHtml;
    });
    
    return cardsHtml;
}

module.exports = { setupGalleryRoute, collectAllArtifacts }; 