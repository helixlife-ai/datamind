// 输出缓冲区
const outputBuffers = new Map();

/**
 * 发送任务输出到客户端
 * @param {string} alchemy_id - 任务ID
 * @param {string} output - 输出内容
 * @param {boolean} isError - 是否为错误
 * @param {Object} io - Socket.IO实例
 */
function emitTaskOutput(alchemy_id, output, isError = false, io) {
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
        
        // 如果有进程管理器，保存到历史记录
        if (global.processManager && alchemy_id) {
            global.processManager.addTaskHistory(alchemy_id, bufferInfo.buffer, bufferInfo.isError);
        }
        
        // 清空缓冲区
        bufferInfo.buffer = '';
        bufferInfo.isError = false;
        bufferInfo.timeout = null;
    }, 100); // 100毫秒的延迟，可以根据需要调整
}

module.exports = {
    emitTaskOutput,
    outputBuffers
}; 