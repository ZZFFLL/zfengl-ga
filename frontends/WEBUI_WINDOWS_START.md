# 新 WebUI Windows 启动说明

## 1. 生产静态版

在仓库根目录执行：

```cmd
start_webui.cmd
```

特点：

- 只开一个控制台窗口
- 自动检查 `frontends\webui\dist`，没有就先执行构建
- 然后启动 `python -m frontends.webui_server --host 127.0.0.1 --port 18601`
- 日志直接输出在当前窗口

访问地址：

```text
http://127.0.0.1:18601
```

## 2. 开发模式

在仓库根目录执行：

```cmd
start_webui_dev.cmd
```

特点：

- 打开两个控制台窗口
- 一个跑 Python 后端
- 一个跑 Vite 前端 dev server
- 适合前端改样式或调接口时同时看两边日志

## 3. 注意

- 这两套脚本目前只考虑 Windows
- 默认端口是 `18601`
- 如果端口被占用，需要先停掉旧进程再启动
