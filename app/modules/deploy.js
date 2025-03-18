const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const express = require('express');

// 设置deploy路由
function setupDeployRoute(app, watchDirs, config, io) {
    // 创建deploy路由
    app.get('/deploy', (req, res) => {
        try {
            // 读取deploy.html模板
            const templatePath = path.join(__dirname, '../public/deploy.html');
            let deployHtml = fs.readFileSync(templatePath, 'utf8');
            
            // 设置正确的Content-Type
            res.setHeader('Content-Type', 'text/html; charset=utf-8');
            res.send(deployHtml);
        } catch (err) {
            console.error('生成deploy页面时出错:', err);
            res.status(500).send('生成deploy页面时出错');
        }
    });

    // 添加静态文件服务
    app.use('/js', express.static(path.join(__dirname, '../public/js')));

    // 确保部署目录存在
    const deployDir = path.join(process.cwd(), 'work_dir/gh_page');
    if (!fs.existsSync(deployDir)) {
        fs.mkdirSync(deployDir, { recursive: true });
        console.log(`创建部署目录: ${deployDir}`);
    }

    // 设置Socket.IO事件处理
    io.on('connection', (socket) => {
        console.log('Deploy客户端连接，添加事件监听');
        
        // 客户端请求制品数据
        socket.on('deploy:requestArtifacts', () => {
            try {
                console.log('收到制品数据请求');
                
                // 收集所有炼丹目录中的制品信息
                const artifacts = collectAllArtifacts(watchDirs);
                console.log(`找到 ${artifacts.length} 个制品`);
                
                // 发送制品数据给客户端
                socket.emit('deploy:artifacts', artifacts);
                console.log('已发送制品数据给客户端');
            } catch (err) {
                console.error('发送制品数据时出错:', err);
                socket.emit('deploy:error', { message: '获取制品数据失败' });
                
                // 在出错的情况下也发送样本数据
                const sampleArtifacts = generateSampleArtifacts();
                socket.emit('deploy:artifacts', sampleArtifacts);
                console.log('已发送样本制品数据作为备用');
            }
        });
        
        // 客户端请求当前站点信息
        socket.on('deploy:requestSiteInfo', () => {
            try {
                // 获取站点信息
                const siteInfo = getSiteInfo();
                
                // 发送站点信息给客户端
                socket.emit('deploy:siteInfo', siteInfo);
                console.log('已发送站点信息给客户端');
            } catch (err) {
                console.error('发送站点信息时出错:', err);
                socket.emit('deploy:error', { message: '获取站点信息失败' });
            }
        });
        
        // 生成部署文件
        socket.on('deploy:generateFiles', (data) => {
            try {
                const { artifacts } = data;
                
                // 确保有选择的制品
                if (!artifacts || artifacts.length === 0) {
                    socket.emit('deploy:error', { message: '没有选择任何制品' });
                    return;
                }
                
                // 发送日志
                socket.emit('deploy:log', `准备生成 ${artifacts.length} 个制品的部署文件...`);
                
                // 生成部署文件
                generateDeployFiles(artifacts, socket, watchDirs);
            } catch (err) {
                console.error('生成部署文件时出错:', err);
                socket.emit('deploy:error', { message: '生成部署文件失败: ' + err.message });
            }
        });
        
        // 部署到GitHub
        socket.on('deploy:toGitHub', (data) => {
            try {
                const { repoUrl, branch, commitMessage, token } = data;
                
                // 检查必要参数
                if (!repoUrl) {
                    socket.emit('deploy:error', { message: '缺少仓库URL' });
                    return;
                }
                
                // 发送日志
                socket.emit('deploy:log', `准备部署到 ${repoUrl} 的 ${branch} 分支...`);
                
                // 执行部署脚本
                deployToGitHub(repoUrl, branch, commitMessage, token, socket);
            } catch (err) {
                console.error('部署到GitHub时出错:', err);
                socket.emit('deploy:error', { message: '部署到GitHub失败: ' + err.message });
                socket.emit('deploy:complete', { success: false, error: err.message });
            }
        });
        
        // 监听断开连接事件
        socket.on('disconnect', () => {
            console.log('Deploy客户端断开连接');
        });
    });
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
                break;
            }
        }
    }
    
    if (!alchemyPath) {
        console.log('未找到alchemy_runs目录');
        return artifacts;
    }
    
    // 遍历所有炼丹目录
    let alchemyDirs = [];
    try {
        alchemyDirs = fs.readdirSync(alchemyPath);
    } catch (err) {
        console.error('读取炼丹目录时出错:', err);
        return artifacts;
    }
    
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
                        const artifactUrl = `/api/artifacts/${dirName}/${iteration.output}`;
                        
                        artifacts.push({
                            alchemyId,
                            alchemyDir: dirName,
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
    
    // 如果没有找到任何制品，返回样本数据
    if (artifacts.length === 0) {
        return generateSampleArtifacts();
    }
    
    return artifacts;
}

// 生成样本制品数据（当无法找到真实数据时使用）
function generateSampleArtifacts() {
    console.log('使用样本数据替代实际制品数据');
    
    // 检查是否有 work_dir/gh_page/artifacts.json
    const artifactsJsonPath = path.join(process.cwd(), 'work_dir/gh_page', 'artifacts.json');
    
    if (fs.existsSync(artifactsJsonPath)) {
        try {
            // 如果存在则直接使用这个文件
            const artifactsJson = JSON.parse(fs.readFileSync(artifactsJsonPath, 'utf8'));
            
            // 转换格式以匹配预期的制品格式
            return artifactsJson.map(artifact => ({
                ...artifact,
                relativePath: artifact.relativePath || `artifacts/${artifact.alchemyId}.html`
            }));
        } catch (err) {
            console.error('读取artifacts.json文件失败:', err);
        }
    }
    
    // 如果不存在，则生成样本数据
    return [
        {
            alchemyId: '001',
            alchemyDir: 'alchemy_001',
            query: '分析中国近十年GDP增长趋势',
            timestamp: '2023-05-15T08:30:00Z',
            iteration: 3,
            screenshot: null,
            relativePath: 'artifacts/001.html'
        },
        {
            alchemyId: '002',
            alchemyDir: 'alchemy_002',
            query: '预测2023年全球主要股市走势',
            timestamp: '2023-06-22T14:45:00Z',
            iteration: 2,
            screenshot: null,
            relativePath: 'artifacts/002.html'
        },
        {
            alchemyId: '003',
            alchemyDir: 'alchemy_003',
            query: '分析新冠疫情对全球旅游业的影响',
            timestamp: '2023-07-10T11:20:00Z',
            iteration: 5,
            screenshot: null,
            relativePath: 'artifacts/003.html'
        }
    ];
}

// 获取当前站点信息
function getSiteInfo() {
    console.log('获取站点信息');
    const deployDir = path.join(process.cwd(), 'work_dir/gh_page');
    const deployInfoPath = path.join(deployDir, 'deploy_info.json');
    
    // 检查部署目录是否存在
    if (!fs.existsSync(deployDir)) {
        console.log('部署目录不存在，创建目录');
        fs.mkdirSync(deployDir, { recursive: true });
    }
    
    if (fs.existsSync(deployInfoPath)) {
        try {
            console.log('找到部署信息文件');
            const deployInfo = JSON.parse(fs.readFileSync(deployInfoPath, 'utf8'));
            return deployInfo;
        } catch (err) {
            console.error('读取部署信息时出错:', err);
        }
    } else {
        console.log('部署信息文件不存在');
    }
    
    // 如果没有找到部署信息，尝试读取artifacts.json来获取作品数量
    const artifactsPath = path.join(deployDir, 'artifacts.json');
    if (fs.existsSync(artifactsPath)) {
        try {
            console.log('找到制品信息文件');
            const artifacts = JSON.parse(fs.readFileSync(artifactsPath, 'utf8'));
            return {
                lastDeploy: new Date().toISOString(),
                repoUrl: '未知',
                branch: '未知',
                artifactCount: artifacts.length,
                url: '未知'
            };
        } catch (err) {
            console.error('读取artifacts.json时出错:', err);
        }
    } else {
        console.log('制品信息文件不存在');
    }
    
    // 都没有找到，返回默认信息
    console.log('返回默认站点信息');
    return {
        lastDeploy: new Date().toISOString(),
        repoUrl: '未部署',
        branch: 'gh-pages',
        artifactCount: 0,
        url: '未部署'
    };
}

// 查找alchemy_runs目录
function findAlchemyDir(watchDirs) {
    // 查找所有炼丹目录
    let alchemyDir = watchDirs.find(dir => dir.path.endsWith('alchemy_runs'));
    let alchemyPath = null;
    
    if (alchemyDir) {
        // 直接使用找到的alchemy_runs目录
        alchemyPath = alchemyDir.fullPath;
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
    
    return alchemyPath;
}

// 生成部署文件
function generateDeployFiles(artifacts, socket, watchDirs) {
    const deployDir = path.join(process.cwd(), 'work_dir/gh_page');
    
    // 确保部署目录存在
    if (!fs.existsSync(deployDir)) {
        fs.mkdirSync(deployDir, { recursive: true });
    }
    
    // 移除现有的部署文件
    socket.emit('deploy:log', '清理现有部署文件...');
    try {
        // 保留deploy_info.json文件
        const deployInfoPath = path.join(deployDir, 'deploy_info.json');
        let deployInfo = null;
        
        if (fs.existsSync(deployInfoPath)) {
            try {
                deployInfo = JSON.parse(fs.readFileSync(deployInfoPath, 'utf8'));
            } catch (e) {
                console.error('读取部署信息时出错:', e);
            }
        }
        
        // 删除目录中的所有文件和子目录
        const files = fs.readdirSync(deployDir);
        for (const file of files) {
            const filePath = path.join(deployDir, file);
            if (file !== 'deploy_info.json') {
                if (fs.lstatSync(filePath).isDirectory()) {
                    fs.rmSync(filePath, { recursive: true, force: true });
                } else {
                    fs.unlinkSync(filePath);
                }
            }
        }
        
        // 如果有部署信息，重新保存
        if (deployInfo) {
            fs.writeFileSync(deployInfoPath, JSON.stringify(deployInfo, null, 2), 'utf8');
        }
        
        socket.emit('deploy:log', '清理完成，开始生成新文件...');
    } catch (err) {
        console.error('清理部署目录时出错:', err);
        socket.emit('deploy:log', `清理部署目录时出错: ${err.message}`);
        return;
    }
    
    // 创建artifacts.json文件
    const artifactsJson = artifacts.map(artifact => ({
        alchemyId: artifact.alchemyId,
        alchemyDir: artifact.alchemyDir,
        query: artifact.query,
        timestamp: artifact.timestamp,
        iteration: artifact.iteration,
        screenshot: artifact.screenshot,
        relativePath: `artifacts/${artifact.alchemyId}.html`
    }));
    
    // 写入artifacts.json
    fs.writeFileSync(
        path.join(deployDir, 'artifacts.json'),
        JSON.stringify(artifactsJson, null, 2),
        'utf8'
    );
    
    socket.emit('deploy:log', `创建artifacts.json文件，包含${artifactsJson.length}个制品`);
    
    // 创建artifacts目录
    const artifactsDir = path.join(deployDir, 'artifacts');
    if (!fs.existsSync(artifactsDir)) {
        fs.mkdirSync(artifactsDir, { recursive: true });
    }
    
    // 创建images目录
    const imagesDir = path.join(deployDir, 'images');
    if (!fs.existsSync(imagesDir)) {
        fs.mkdirSync(imagesDir, { recursive: true });
    }
    
    // 查找alchemy_runs目录
    const alchemyPath = findAlchemyDir(watchDirs);
    if (!alchemyPath) {
        socket.emit('deploy:log', '错误: 无法找到alchemy_runs目录');
        socket.emit('deploy:filesGenerated', { success: false, error: '无法找到alchemy_runs目录' });
        return;
    }
    
    // 复制每个制品的HTML和截图文件
    let successCount = 0;
    for (const artifact of artifacts) {
        try {
            // 构建源文件路径
            const htmlSourcePath = path.join(alchemyPath, artifact.alchemyDir, artifact.outputPath);
            
            // 检查HTML文件是否存在
            if (!fs.existsSync(htmlSourcePath)) {
                socket.emit('deploy:log', `警告: 找不到制品 ${artifact.alchemyId} 的HTML文件，跳过`);
                continue;
            }
            
            // 读取HTML文件
            let htmlContent = fs.readFileSync(htmlSourcePath, 'utf8');
            
            // 构建目标文件路径
            const htmlTargetPath = path.join(artifactsDir, `${artifact.alchemyId}.html`);
            
            // 写入HTML文件
            fs.writeFileSync(htmlTargetPath, htmlContent, 'utf8');
            
            // 如果有截图，复制截图文件
            if (artifact.screenshot) {
                const screenshotSourcePath = path.join(alchemyPath, artifact.alchemyDir, artifact.screenshot);
                const screenshotFilename = path.basename(artifact.screenshot);
                const screenshotTargetPath = path.join(imagesDir, `${artifact.alchemyId}_${screenshotFilename}`);
                
                // 检查截图文件是否存在
                if (fs.existsSync(screenshotSourcePath)) {
                    fs.copyFileSync(screenshotSourcePath, screenshotTargetPath);
                    
                    // 更新artifacts.json中的截图路径
                    const index = artifactsJson.findIndex(item => item.alchemyId === artifact.alchemyId);
                    if (index !== -1) {
                        artifactsJson[index].screenshot = `images/${artifact.alchemyId}_${screenshotFilename}`;
                    }
                } else {
                    socket.emit('deploy:log', `警告: 找不到制品 ${artifact.alchemyId} 的截图文件，使用默认图片`);
                    const index = artifactsJson.findIndex(item => item.alchemyId === artifact.alchemyId);
                    if (index !== -1) {
                        artifactsJson[index].screenshot = null;
                    }
                }
            }
            
            successCount++;
            socket.emit('deploy:log', `已复制制品 ${artifact.alchemyId} 的文件`);
        } catch (err) {
            console.error(`处理制品 ${artifact.alchemyId} 时出错:`, err);
            socket.emit('deploy:log', `处理制品 ${artifact.alchemyId} 时出错: ${err.message}`);
        }
    }
    
    // 更新artifacts.json文件（因为可能有截图路径更新）
    fs.writeFileSync(
        path.join(deployDir, 'artifacts.json'),
        JSON.stringify(artifactsJson, null, 2),
        'utf8'
    );
    
    // 创建简单的index.html文件，重定向到gallery.html
    const indexHtml = `
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="0;url=./gallery.html">
    <title>重定向到作品集</title>
</head>
<body>
    <p>正在跳转到作品集...</p>
    <script>window.location.href = "./gallery.html";</script>
</body>
</html>`;
    
    fs.writeFileSync(path.join(deployDir, 'index.html'), indexHtml, 'utf8');
    
    // 创建gallery.html文件
    const galleryHtml = generateGalleryHtml(artifactsJson);
    fs.writeFileSync(path.join(deployDir, 'gallery.html'), galleryHtml, 'utf8');
    
    socket.emit('deploy:log', `创建了gallery页面和重定向index页面`);
    
    // 添加.nojekyll文件（防止GitHub Pages使用Jekyll处理）
    fs.writeFileSync(path.join(deployDir, '.nojekyll'), '', 'utf8');
    
    // 生成部署信息文件
    const deployInfo = {
        lastDeploy: new Date().toISOString(),
        repoUrl: '尚未部署',
        branch: '尚未部署',
        artifactCount: successCount,
        url: '尚未部署'
    };
    
    fs.writeFileSync(
        path.join(deployDir, 'deploy_info.json'),
        JSON.stringify(deployInfo, null, 2),
        'utf8'
    );
    
    // 完成
    socket.emit('deploy:filesGenerated', {
        success: true,
        artifactCount: successCount,
        path: deployDir
    });
}

// 生成gallery.html内容
function generateGalleryHtml(artifacts) {
    return `
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DataMind - Gallery</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Crimson+Text:ital@1&family=Poppins:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        body {
            font-family: 'Poppins', -apple-system, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f8fafc;
            min-height: 100vh;
            color: #1e293b;
        }
        
        .container {
            max-width: 100%;
            margin: 0;
            padding: 0;
            min-height: 100vh;
            box-sizing: border-box;
            display: flex;
            flex-direction: column;
        }
        
        h1 {
            color: #333;
            margin: 0;
            padding: 20px 0;
            font-weight: 600;
            background: linear-gradient(135deg, #1e293b, #3b82f6);
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.5px;
        }
        
        .card {
            border: 1px solid rgba(203, 213, 225, 0.7);
            border-radius: 10px;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.03);
            transition: box-shadow 0.3s, transform 0.2s;
            margin-bottom: 20px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            height: 100%;
        }
        
        .card:hover {
            box-shadow: 0 6px 15px rgba(0, 0, 0, 0.05);
            transform: translateY(-5px);
        }
        
        .card-img-container {
            position: relative;
            width: 100%;
            padding-top: 66.67%; /* 2:3 宽高比 */
            overflow: hidden;
        }
        
        .card-img {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
            object-position: center;
        }
        
        .card-body {
            padding: 16px;
            flex: 1;
        }
        
        .card-title {
            font-weight: 600;
            color: #334155;
            margin-bottom: 10px;
            font-size: 1.25rem;
        }
        
        .card-text {
            color: #64748b;
            margin-bottom: 15px;
            font-size: calc(0.75rem + 0.3vw);
            line-height: 1.5;
        }
        
        .card-footer {
            padding: 0 16px 16px;
        }
        
        .card-footer .btn {
            padding: 8px 16px;
            font-size: calc(0.75rem + 0.2vw);
        }
        
        .header {
            display: flex;
            align-items: center;
            padding: 8px 4%;
            background: linear-gradient(to right, #ffffff, #f1f5f9);
            border-bottom: 1px solid rgba(203, 213, 225, 0.5);
            height: 60px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
            flex-shrink: 0;
            width: 100%;
            position: sticky;
            top: 0;
            left: 0;
            z-index: 1000;
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
        }
        
        .title-container {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        
        .main-title {
            display: flex;
            align-items: center;
            gap: 14px;
        }
        
        .product-name {
            font-size: 22px;
            font-weight: 600;
            margin: 0;
            background: linear-gradient(135deg, #1e293b, #3b82f6);
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.5px;
        }
        
        .product-subtitle {
            font-family: 'Crimson Text', Georgia, serif;
            font-size: 14px;
            font-style: italic;
            color: #64748b;
            margin: 0;
            padding-left: 28px;
            position: relative;
        }
        
        .product-subtitle::before {
            content: "⚗️";
            position: absolute;
            left: 0;
            top: 50%;
            transform: translateY(-50%);
            font-size: 16px;
        }
        
        .product-tagline {
            font-size: 13px;
            font-weight: 600;
            color: #3b82f6;
            margin: 0;
            padding: 4px 12px;
            border-radius: 6px;
            background: rgba(59, 130, 246, 0.08);
            white-space: nowrap;
            letter-spacing: -0.2px;
            box-shadow: 0 2px 4px rgba(59, 130, 246, 0.1);
        }
        
        .product-tagline::before {
            content: "✨";
            margin-right: 8px;
        }
        
        .hero-section {
            background-image: url('https://images.unsplash.com/photo-1518770660439-4636190af475?ixlib=rb-4.0.3&auto=format&fit=crop&w=1200&q=80');
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            padding: 4rem 2rem;
            position: relative;
            border-radius: 12px;
            margin: 0 1rem 2rem;
            color: #fff;
        }
        
        .hero-section::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(135deg, rgba(30, 41, 59, 0.85), rgba(59, 130, 246, 0.75));
            border-radius: 12px;
            z-index: 0;
        }
        
        .hero-section h2, 
        .hero-section p {
            position: relative;
            z-index: 1;
        }
        
        .hero-section h2 {
            color: #ffffff;
            font-size: 2.5rem;
            text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
        }
        
        .hero-section p {
            color: rgba(255, 255, 255, 0.9);
            font-size: 1.1rem;
            text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
        }
        
        main {
            padding: 2rem 4%;
        }
        
        .footer {
            margin-top: auto;
            padding: 2rem;
            background-color: #f1f5f9;
            text-align: center;
            color: #64748b;
            font-size: 0.875rem;
            border-top: 1px solid rgba(203, 213, 225, 0.5);
        }
        
        .btn {
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: 500;
            transition: all 0.2s;
        }
        
        .btn-primary {
            background-color: #3b82f6;
            border-color: #3b82f6;
            box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
        }
        
        .btn-primary:hover {
            background-color: #2563eb;
            border-color: #2563eb;
            box-shadow: 0 4px 8px rgba(59, 130, 246, 0.3);
            transform: translateY(-1px);
        }
        
        .section-title {
            font-size: 1.75rem;
            font-weight: 600;
            margin-bottom: 1.5rem;
            color: #334155;
            border-bottom: 1px solid rgba(203, 213, 225, 0.5);
            padding-bottom: 0.5rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title-container">
                <div class="main-title">
                    <h1 class="product-name">DataMind</h1>
                    <p class="product-subtitle">The Alchemy Cauldron</p>
                    <p class="product-tagline">Data in, Surprise out!</p>
                </div>
            </div>
        </div>

        <main class="flex-grow-1">
            <section class="text-center mb-5 px-4 hero-section">
                <h2 class="mb-3 fw-bold">精选作品展示</h2>
                <p class="mx-auto" style="max-width: 700px;">
                    探索我们的炼丹作品集，每一个项目都代表着独特的AI创意和专业的执行力
                </p>
            </section>

            <section id="projects" class="mb-5 px-4">
                <h3 class="section-title">作品集</h3>
                
                <div class="row g-4">
                    ${generateArtifactCards(artifacts)}
                </div>
            </section>
        </main>

        <footer class="footer">
            <p>由 DataMind 强力驱动 · ${new Date().getFullYear()}</p>
        </footer>
    </div>

    <script>
        // 为卡片添加动画效果
        document.addEventListener('DOMContentLoaded', function() {
            const cards = document.querySelectorAll('.card');
            cards.forEach((card, index) => {
                card.style.opacity = '0';
                card.style.transform = 'translateY(20px)';
                card.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                
                // 延迟显示，创建瀑布流效果
                setTimeout(() => {
                    card.style.opacity = '1';
                    card.style.transform = 'translateY(0)';
                }, index * 100);
            });
            
            // 为卡片中的图片添加错误处理
            document.querySelectorAll('.card-img').forEach(img => {
                img.onerror = function() {
                    this.src = 'https://images.unsplash.com/photo-1581291518633-83b4ebd1d83e?ixlib=rb-4.0.3&auto=format&fit=crop&w=600&h=400&q=80';
                };
            });
        });
        
        // 滚动动画
        window.addEventListener('scroll', () => {
            const cards = document.querySelectorAll('.card');
            
            cards.forEach(card => {
                const cardTop = card.getBoundingClientRect().top;
                const triggerBottom = window.innerHeight * 0.8;
                
                if (cardTop < triggerBottom) {
                    card.style.opacity = '1';
                    card.style.transform = 'translateY(0)';
                }
            });
        });
    </script>
</body>
</html>
    `;
}

// 生成作品卡片HTML
function generateArtifactCards(artifacts) {
    if (!artifacts || artifacts.length === 0) {
        return `
        <div class="col-12 text-center py-5">
            <p class="text-muted">暂无制品</p>
        </div>
        `;
    }
    
    let cardsHtml = '';
    
    artifacts.forEach((artifact) => {
        // 截断过长的查询文本
        const queryText = artifact.query.length > 80 
            ? artifact.query.substring(0, 80) + '...' 
            : artifact.query;
            
        // 格式化时间戳
        const date = new Date(artifact.timestamp);
        const formattedDate = `${date.getFullYear()}-${(date.getMonth()+1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')}`;
        
        // 使用相对路径的预览图URL
        const previewImgUrl = artifact.screenshot 
            ? artifact.screenshot
            : "https://images.unsplash.com/photo-1581291518633-83b4ebd1d83e?ixlib=rb-4.0.3&auto=format&fit=crop&w=600&h=400&q=80";
        
        cardsHtml += `
        <div class="col-12 col-sm-6 col-md-4 col-lg-3 col-xl-2">
            <div class="card h-100">
                <div class="card-img-container">
                    <img src="${previewImgUrl}" alt="制品预览" class="card-img" loading="lazy">
                </div>
                <div class="card-body">
                    <p class="card-text">${queryText}</p>
                    <p class="card-text text-muted small">迭代: ${artifact.iteration} | 创建于: ${formattedDate}</p>
                </div>
                <div class="card-footer bg-white border-top-0 d-flex justify-content-between align-items-center">
                    <a href="${artifact.relativePath}" class="btn btn-primary" target="_self">查看详情</a>
                    <span class="badge bg-light text-secondary">#${artifact.alchemyId}</span>
                </div>
            </div>
        </div>
        `;
    });
    
    return cardsHtml;
}

// 部署到GitHub
function deployToGitHub(repoUrl, branch, commitMessage, token, socket) {
    const deployScript = path.join(process.cwd(), 'scripts', 'deploy_to_github_pages.py');
    const sourceDir = path.join(process.cwd(), 'work_dir/gh_page');
    
    // 检查脚本是否存在
    if (!fs.existsSync(deployScript)) {
        socket.emit('deploy:log', `错误: 找不到部署脚本 ${deployScript}`);
        socket.emit('deploy:complete', { 
            success: false, 
            error: `找不到部署脚本。请确认 scripts/deploy_to_github_pages.py 文件存在。` 
        });
        return;
    }
    
    // 检查源目录是否存在
    if (!fs.existsSync(sourceDir)) {
        socket.emit('deploy:log', `错误: 找不到源目录 ${sourceDir}`);
        socket.emit('deploy:complete', { 
            success: false, 
            error: `找不到源目录。请先生成部署文件。` 
        });
        return;
    }
    
    // 准备命令参数
    const args = [
        deployScript,
        sourceDir,
        '--repo', repoUrl,
        '--branch', branch
    ];
    
    if (commitMessage) {
        args.push('--commit-message', commitMessage);
    }
    
    if (token) {
        args.push('--token', token);
    }
    
    socket.emit('deploy:log', `启动部署脚本: python ${deployScript} ${sourceDir} --repo ${repoUrl} --branch ${branch}`);
    
    // 尝试多种方式运行Python脚本
    let pythonProcess;
    try {
        // 首先尝试使用'python'命令
        pythonProcess = spawn('python', args);
    } catch (error) {
        try {
            // 如果失败，尝试使用'python3'命令
            socket.emit('deploy:log', `使用python命令失败，尝试使用python3...`);
            pythonProcess = spawn('python3', args);
        } catch (error2) {
            socket.emit('deploy:log', `启动部署脚本失败: ${error2.message}`);
            socket.emit('deploy:complete', { 
                success: false, 
                error: `启动部署脚本失败。请确认Python已正确安装。` 
            });
            return;
        }
    }
    
    // 处理标准输出
    pythonProcess.stdout.on('data', (data) => {
        const output = data.toString().trim();
        if (output) {
            socket.emit('deploy:log', output);
        }
    });
    
    // 处理标准错误
    pythonProcess.stderr.on('data', (data) => {
        const errorOutput = data.toString().trim();
        if (errorOutput) {
            // 不包含token的安全输出
            const safeOutput = token ? errorOutput.replace(new RegExp(token, 'g'), '****') : errorOutput;
            socket.emit('deploy:log', `错误: ${safeOutput}`);
        }
    });
    
    // 处理脚本完成
    pythonProcess.on('close', (code) => {
        if (code === 0) {
            socket.emit('deploy:log', '部署脚本执行成功！');
            
            // 更新部署信息
            updateDeployInfo(repoUrl, branch, sourceDir);
            
            // 提取仓库用户名和仓库名
            const repoMatch = repoUrl.match(/github\.com\/([^\/]+)\/([^\/\.]+)/);
            let url = '';
            
            if (repoMatch && repoMatch.length >= 3) {
                const username = repoMatch[1];
                const repoName = repoMatch[2].replace('.git', '');
                url = `https://${username}.github.io/${repoName}/`;
            } else {
                url = `部署成功，但无法确定GitHub Pages URL`;
            }
            
            // 发送成功完成信号
            socket.emit('deploy:complete', {
                success: true,
                url
            });
        } else {
            socket.emit('deploy:log', `部署脚本执行失败，退出代码: ${code}`);
            socket.emit('deploy:complete', {
                success: false,
                error: `部署脚本执行失败，退出代码: ${code}`
            });
        }
    });
    
    // 处理可能的错误
    pythonProcess.on('error', (err) => {
        socket.emit('deploy:log', `启动部署脚本时出错: ${err.message}`);
        socket.emit('deploy:complete', {
            success: false,
            error: `启动部署脚本时出错: ${err.message}`
        });
    });
}

// 更新部署信息
function updateDeployInfo(repoUrl, branch, deployDir) {
    const deployInfoPath = path.join(deployDir, 'deploy_info.json');
    
    let deployInfo = {
        lastDeploy: new Date().toISOString(),
        repoUrl,
        branch,
        artifactCount: 0,
        url: ''
    };
    
    // 如果存在旧的部署信息，读取制品数量
    if (fs.existsSync(deployInfoPath)) {
        try {
            const oldInfo = JSON.parse(fs.readFileSync(deployInfoPath, 'utf8'));
            deployInfo.artifactCount = oldInfo.artifactCount || 0;
        } catch (err) {
            console.error('读取旧部署信息时出错:', err);
        }
    }
    
    // 计算制品数量
    const artifactsPath = path.join(deployDir, 'artifacts.json');
    if (fs.existsSync(artifactsPath)) {
        try {
            const artifacts = JSON.parse(fs.readFileSync(artifactsPath, 'utf8'));
            deployInfo.artifactCount = artifacts.length;
        } catch (err) {
            console.error('读取artifacts.json时出错:', err);
        }
    }
    
    // 生成GitHub Pages URL
    const repoMatch = repoUrl.match(/github\.com\/([^\/]+)\/([^\/\.]+)/);
    if (repoMatch && repoMatch.length >= 3) {
        const username = repoMatch[1];
        const repoName = repoMatch[2].replace('.git', '');
        deployInfo.url = `https://${username}.github.io/${repoName}/`;
    } else {
        deployInfo.url = '未知';
    }
    
    // 保存部署信息
    fs.writeFileSync(deployInfoPath, JSON.stringify(deployInfo, null, 2), 'utf8');
}

module.exports = { setupDeployRoute }; 