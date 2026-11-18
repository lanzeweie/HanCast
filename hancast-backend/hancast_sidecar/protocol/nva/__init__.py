"""NVA 协议（哔哩哔哩「哔哩必连」电视端接收协议）。

分层说明：
- constants: 服务声明、描述品牌字段、帧常量、playState 映射
- framing: 二进制帧编解码（纯函数，不依赖网络与渲染器）
- bili_tv: TV 客户端接口（播放地址、分集卡片、清晰度）
- danmaku: 弹幕 XML → ASS
- http: NVA/1.0 请求行解析、SETUP 族交接、SOAP GetAppInfo
- session: 单连接帧循环、命令分发、播放/进度/弹幕
- manager: 会话注册、活跃会话与广播
- service: 装配渲染器/协议/Guard/配置，向 DLNAServer 提供 HTTP 入口
"""
