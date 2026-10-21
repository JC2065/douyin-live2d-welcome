# 抖音接入：实验状态

[返回 README](../README.md)

`connect_douyin.py` 只处理上游进房消息中明确的进入事件，将 ID 和昵称发送至本地服务。它不发送弹幕、不自动开播、不运行上游 AI 回复或冷场播报。

**尚未验证真实直播间，事件也不保证覆盖所有观众。**

## 前置条件

- 本地服务运行且角色声音已启用；直播间正在直播。
- Node.js 在 PATH 中。
- 自行评估 [上游连接器](https://github.com/Primusse/douyin-ai-assist) 的许可和适用条件。检查的提交未发现许可文件，因此本仓库不分发、不自动安装它。
- 桥接按提交 `417e21474f278222a0d809ff9b15a8068e80b31b` 编写，预期目录 `vendor/douyin-ai-assist`。

原部署对上游 `live_client.py` 做了两处本地修改：`requests.get(...)` 增加 `timeout=15`；`run_forever` 的 `cert_reqs` 从 `ssl.CERT_NONE` 改为 `ssl.CERT_REQUIRED`。这些修改没有随第三方源码发布。上游历史固定签名参数仍需真实开播验证或升级。

## 手动启动

依赖准备好后，将示例数字替换为自己的直播间号：

```powershell
.\.venv\Scripts\python.exe connect_douyin.py 123456789
```

按 `Ctrl+C` 停止。检查桥接终端和本地处理记录；控制台模式标签不会随连接状态变化。反馈时提供脱敏错误，不要公开 Cookie、凭据或观众名单。
