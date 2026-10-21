# 直播欢迎助手

昵称语音、Live2D 欢迎气泡、独立观众 60 秒冷却。当前版本为 **本地模拟可运行，真实抖音接入待验证**。

## 首次安装（Windows）

安装 Python 3.12 和 Git；可选的抖音连接器还需要 Node.js。克隆本仓库后，在 PowerShell 中执行：

```powershell
# 先阅读 THIRD_PARTY.md 中的 Live2D 运行库和模型条款
powershell -ExecutionPolicy Bypass -File .\setup.ps1 -AcceptLive2DTerms
.\start.cmd
```

本仓库原创代码采用 [MIT](LICENSE)；Live2D Core、模型与第三方依赖有独立条款，详见 [THIRD_PARTY.md](THIRD_PARTY.md)。安装脚本从上游下载素材。仓库不包含模型、运行库、观众数据、语音缓存或本机环境。

本地地址：http://127.0.0.1:18765 。双击 `start.cmd` 启动服务并打开控制台。

## 当前部署

- 本地模拟模式，不连接抖音，不发送评论，不自动开播。
- Live2D Haru 示例角色、欢迎气泡、Edge TTS 中文语音、音量驱动嘴型。
- 同一观众 ID 以最近一次获准欢迎的时间为基准：小于 60 秒忽略，大于等于 60 秒再次进房允许欢迎。忽略事件不刷新时间；不同 ID 独立计时。
- 冷却保存在当前服务进程内，重启后重置。语音和气泡排队播放；没有启用角色窗口时不接收欢迎，暂停期间不计入冷却。
- 欢迎使用固定模板，无需大模型密钥。在线语音需联网；失败时尝试浏览器中文语音，失败会在角色窗口显示。

## 使用

1. 双击 `start.cmd`。
2. 点击角色上的「启用欢迎声音」。
3. 点击「模拟进房」；重复点击验证 60 秒冷却。点「换一个观众」测试独立欢迎。
4. 「打开独立角色窗口」会停止控制台的预览，避免双重声音。新窗口再次启用声音。
5. 独立角色窗口默认绿幕：http://127.0.0.1:18765/overlay?green=1 。透明页面：http://127.0.0.1:18765/overlay 。
6. 直播伴侣实际采集待开播前确认：尝试窗口采集，绿幕画面需要配置对应的色键；如版本支持网页源，可尝试透明页面。仅网页透明不等于窗口采集支持透明。音频需确认直播伴侣采集到浏览器输出，避免重复收音。

「暂停欢迎」会停止当前播放并清空待播事件。不会检测主播麦克风，所以不能自动避让主播讲话。

## 以后连接抖音

可选桥接依赖上游连接器，不随本仓库分发，也不在首次安装时自动下载。检查上游许可与适用条件后，可自行将对应版本放到 `vendor/douyin-ai-assist`；当前桥接为实验性功能。缺少该目录时只能运行本地模拟。上游连接代码需启用 TLS 验证并设置 HTTP 超时，详见 THIRD_PARTY.md。

在本目录终端运行：

```powershell
.\.venv\Scripts\python.exe connect_douyin.py 你的数字直播间号
```

该桥接脚本只在手动运行时连接；目前未运行、未验证真实直播间。控制台的「本地模拟」标签描述本地服务，本版本尚未集成桥接进程状态。抖音连接使用上游非官方接口，收到的事件不保证覆盖每个观众。上游签名参数有历史固定值，正式使用前需要真实开播验证或升级连接器。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest test_welcome -v
node verify-ui.cjs
```

UI 测试前先运行 `npm install` 安装 Playwright，并确保本机已安装 Microsoft Edge、欢迎服务已启动。

边界测试覆盖 59.999 / 60 / 119 / 120 秒、不同观众与缺失 ID。UI 验证使用本机 Edge，验证模型加载、气泡、语音播放结束回调、重复进入和暂停。浏览器播放回调不代表直播伴侣音轨已录到声音。

## 来源与素材

- 抖音连接器：https://github.com/Primusse/douyin-ai-assist ，本地版本 `417e21474f278222a0d809ff9b15a8068e80b31b`。欢迎服务与界面为本目录独立实现。
- Live2D 渲染：https://github.com/guansss/pixi-live2d-display ，运行版 0.4.0，PixiJS 6.5.10。
- Haru 示例来自该仓库 `31317b37d5e22955a44d5b11f37f421e94a11269` 的 test/assets/haru；移除了示例动作附带的无关声音。
- Live2D Core 来自 https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js 。示例模型条款保存在 `web/models/LICENSE-Live2D.md`，角色为 Live2D 官方示例，并非原创角色。相关使用范围按其条款；后续可替换自己有授权的模型。
- `data/preview.png` 为本地运行截图，`data/audio/` 为欢迎语音缓存（最多保留约 200 个文件）。日志为本地运行日志。

服务仅绑定 127.0.0.1，无开机自启。依赖锁定在 requirements-lock.txt。
