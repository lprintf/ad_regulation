from granian.server import Server

if __name__ == "__main__":
    server = Server(
        # 必选参数：应用入口（模块名:应用实例名）
        target="api.app:app",
        
        # 网络相关参数（和输出完全一致：address + port，而非 host/bind）
        address="0.0.0.0",  # 对应主机地址（输出参数名：address）
        port=8000,          # 对应端口（输出参数名：port）
        
        # 应用类型（输出参数是 Interfaces 枚举，但支持字符串简写，避免导入错误）
        interface="asgi",  # 若你的应用是 Flask/Django，改为 "wsgi"
        
        # 开发模式热重载（输出支持 reload 参数，直接设为 True）
        reload=True,
        
        # 日志相关（输出参数名：log_level，支持字符串值）
        log_level="info",  # 可选："debug"/"warning"/"error"/"critical"
        
        # 工作进程数（输出默认 workers=1，显式指定更稳妥）
        workers=1,
        
        # 可选：静态文件相关（若不需要可删除）
        static_path_mount=None,  # 不挂载静态文件（默认 None）
        
        # 可选：重载忽略规则（按需添加，避免无关文件修改触发重载）
        reload_ignore_dirs=["venv", "logs"],  # 忽略 venv 和 logs 目录
        reload_ignore_patterns=[".*\.pyc", ".*\.log"],  # 忽略 .pyc 和 .log 文件
    )
    # 启动服务器
    server.run()