# 飞书文件发送 SOP

## 功能
通过飞书发送文件给用户（支持图片、视频、文档等）

## 前置条件
- 飞书应用已配置 `fs_app_id` 和 `fs_app_secret`（在 mykeys 中）
- 需要安装 `lark-oapi` 包

## 依赖安装
```python
pip install lark-oapi -q
```

## 使用步骤

### 1. 初始化飞书客户端
```python
import sys
import os
os.chdir('/home/GenericAgent')
sys.path.insert(0, '/home/GenericAgent')

import frontends.fsapp as fsapp
import lark_oapi as lark

# 构建客户端（如未初始化）
if not fsapp.client:
    fsapp.client = lark.Client.builder().app_id(fsapp.APP_ID).app_secret(fsapp.APP_SECRET).log_level(lark.LogLevel.INFO).build()
```

### 2. 发送文件
```python
# 用户ID（从 feishu_sessions 目录获取）
receive_id = "ou_xxxxxxxxxxxx"  # 用户的 open_id
file_path = "/path/to/file.mp4"

result = fsapp._send_local_file(receive_id, file_path)
print(f"发送结果: {result}")
```

## 获取用户 open_id
从会话目录 `temp/feishu_sessions/` 下的 JSON 文件中获取：
- 文件名格式：`ou_xxxxx.json`
- 文件内 `open_id` 字段

## 支持的文件类型
- 图片：`.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`
- 视频：`.mp4`, `.mov`, `.avi`
- 文档：`.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`, `.ppt`, `.pptx`
- 其他：`.zip`, `.rar`, `.txt` 等

## 常见问题
- **'NoneType' object has no attribute 'im'**：客户端未初始化，需先执行步骤1
- **文件不存在**：检查文件路径是否正确
- **发送失败**：检查网络和飞书应用权限
- **视频无法播放**：飞书聊天窗口不支持直接播放MP4，需下载到本地播放（这是飞书产品限制，非代码问题）

## 快捷函数封装
```python
def feishu_send_file(file_path, receive_id=None):
    """发送文件到飞书"""
    import os, sys
    os.chdir('/home/GenericAgent')
    sys.path.insert(0, '/home/GenericAgent')
    
    import frontends.fsapp as fsapp
    import lark_oapi as lark
    
    # 初始化客户端
    if not fsapp.client:
        fsapp.client = lark.Client.builder().app_id(fsapp.APP_ID).app_secret(fsapp.APP_SECRET).log_level(lark.LogLevel.INFO).build()
    
    # 默认用户ID（当前会话）
    if not receive_id:
        # 从会话文件读取
        session_dir = '/home/GenericAgent/temp/feishu_sessions'
        for f in os.listdir(session_dir):
            if f.endswith('.json'):
                import json
                with open(os.path.join(session_dir, f)) as fp:
                    data = json.load(fp)
                    receive_id = data.get('open_id')
                    break
    
    return fsapp._send_local_file(receive_id, file_path)
```

## [FEISHU_LIVE_SWITCH]
- 开关：`fs_live_thinking_enabled`、`fs_live_tool_use_enabled`
- 来源：`mykey.py`/`mykeys.get(..., True)`
- 关闭：在 `mykey.py` 显式设 `False`
- 复用顺序：先查 `fsapp.py` → 再改 `mykey.py`
