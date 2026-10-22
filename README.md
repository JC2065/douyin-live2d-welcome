# Live2D 直播欢迎助手

[![Python tests](https://github.com/JC2065/douyin-live2d-welcome/actions/workflows/tests.yml/badge.svg)](https://github.com/JC2065/douyin-live2d-welcome/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)

**让直播间的小助手念出观众昵称，用 Live2D 动作和对话气泡迎接每次到来。**

面向技术直播的轻量本地工具：中文欢迎语、音量驱动嘴型，以及按观众 ID 独立计算的 60 秒冷却。内置 12 条可编辑的技术直播欢迎语，每轮打乱且避免连续重复，无需大模型 API Key。

> **早期预览版本。** 本地模拟欢迎已验证；抖音 WebSocket 连接和直播统计消息已实测；已完成一次真实进房触发与浏览器播放回报验证；直播伴侣采集和收音仍待验证。实验性桥接不等于开箱即用的抖音场控产品。本项目不是抖音官方工具。

[安装与排障](docs/GETTING_STARTED.md) · [实现与接口](docs/ARCHITECTURE.md) · [抖音接入状态](docs/DOUYIN.md) · [贡献指南](CONTRIBUTING.md)

## 欢迎效果

```text
小明进入 → 获准欢迎 → 生成语音 → 角色动作 + 欢迎气泡 + 嘴型
                                  「欢迎小明，一起探索技术吧！」
同一 ID 在 60 秒内再次进入 → 忽略，不延长冷却
同一 ID 满 60 秒后再次进入 → 重新欢迎
```

## 功能与状态

| 能力 | 当前状态 |
| --- | --- |
| 模拟观众进房、按 ID 冷却 | 可用，精确 60 秒边界与不同 ID 已有单元测试 |
| Live2D、气泡、中文语音、嘴型 | 本地浏览器流程已验证，默认 Haru 示例角色 |
| 暂停欢迎、独立角色窗口 | 已实现，只允许一个活动播放窗口 |
| 绿幕与透明网页 | 已提供，直播软件采集效果待验证 |
| 抖音进房桥接 | 真实连接、进房触发与浏览器播放回报已实测；依赖可选连接器 |
| AI 聊天、主播讲话自动避让 | 未实现，不监听麦克风 |

## 快速开始

需要 **Windows、Python 3.12（含 `py` 启动器）、Git、支持 WebGL 的现代浏览器**。安装素材与在线语音需要网络。Node.js 仅用于可选桥接或 UI 测试。

```powershell
git clone https://github.com/JC2065/douyin-live2d-welcome.git
cd douyin-live2d-welcome

# 先阅读 THIRD_PARTY.md 链接的 Live2D 运行库与示例模型条款。
# 此参数表示你已阅读并接受适用条款。
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -AcceptLive2DTerms
.\start.cmd
```

打开 [本地控制台](http://127.0.0.1:18765/)：

1. 等待角色加载，点击 **启用欢迎声音**。
2. 点击 **模拟进房**，观察气泡并试听欢迎语。
3. 用相同 ID 再点一次，确认冷却；满 60 秒后重试。
4. 点击 **换一个观众**，验证独立触发。
5. 可选连接器就绪后，在「连接抖音直播间」粘贴分享文字并连接；控制台展示连接状态和事件计数。

安装脚本已做语法检查，尚未完成全新 Windows 环境端到端安装验证。遇到问题查看 [排障指南](docs/GETTING_STARTED.md)。

## 点赞、礼物与评论播报

控制台可分别启用「点赞感谢」「礼物播报」「评论朗读」，本机保存开关。三项默认开启。

- 评论：朗读昵称和内容，超长内容截断到 100 字，网址替换成“一个链接”。不调用大模型回复。
- 礼物：感谢送礼人并读出名称、数量；可连击礼物在结束消息时汇总，避免每次计数都重复播报。
- 点赞：同一用户 8 秒内合并去重，临近的不同用户可合并感谢。
- 礼物、评论优先于尚未播放的欢迎和点赞；当前语音会先播完。

这些事件共享一个语音队列。若浏览器阻止声音，会显示「恢复欢迎声音」，不会把阻止状态误报为播放完成。平台没有推送的事件无法播报。

## 冷却规则

冷却从服务端 **接受欢迎请求** 时开始，而不是声音播放结束。相同昵称、不同 ID 被视为不同观众。

| 时间（同一 ID） | 结果 |
| --- | --- |
| 第 0 秒进入 | 接受欢迎，开始计时 |
| 第 30 秒再次进入 | 忽略，仍从第 0 秒计时 |
| 第 59.999 秒再次进入 | 忽略 |
| 第 60 秒再次进入 | 接受欢迎，重新计时 |

没有就绪的播放窗口、暂停或待处理队列已满时，请求不会进入冷却。冷却保存在内存中，重启后重置。接受请求不保证最终发声：语音错误、暂停、过期或拥堵都可能导致跳过。

## 多人进房与播放确认

欢迎会等待约 0.8 秒收集新人，最多三人一组并依次点名；独立用户仍按 60 秒规则判断。生成队列和待播队列各最多 120 条，事件最多保留 120 秒，拥堵过期会记入统计。

网页每次只领取一组，播放完成回报后再取下一组。普通播放失败重试一次；声音权限阻止时保留待播事件，等待点击恢复。控制台显示重复、未启用声音、播放失败、过期以及各类互动收到/已播计数。

## 直播软件接入

控制台的 **打开独立角色窗口** 默认使用绿幕，同时关闭内嵌预览，防止重复播放。

| 页面 | 本地地址 |
| --- | --- |
| 控制台 | `http://127.0.0.1:18765/` |
| 透明角色页面 | `http://127.0.0.1:18765/overlay` |
| 绿幕角色页面 | `http://127.0.0.1:18765/overlay?green=1` |

绿幕需要直播软件支持窗口采集与色键；透明页面需要相应网页源支持。网页透明不代表窗口采集后透明，浏览器发声也不代表直播音轨已收录。先录制短片确认画面、音量和重复收音。详见 [使用指南](docs/GETTING_STARTED.md)。

## 开发与验证

核心测试不依赖网络、Live2D 或第三方 Python 包：

```powershell
py -3.12 -m unittest test_welcome -v
```

UI 测试需要运行中的服务、素材、Microsoft Edge，并先关闭其他角色窗口：

```powershell
npm install
npm run test:ui
```

GitHub Actions 运行冷却、分享解析与欢迎流程单元测试（模拟网络与播放器）。UI 测试检查模型、气泡、播放结束回调、冷却与暂停，不证明真实直播事件或音轨采集有效。[架构与测试边界](docs/ARCHITECTURE.md)

## 数据与许可

- 默认只监听 `127.0.0.1:18765`，无开机自启；不要直接暴露到公网。
- 欢迎文字包含处理后的昵称，会发送至 Edge TTS。浏览器语音回退也可能联网。
- 本地音频保存在 `data/audio/`，清理策略约保留最新 200 个 MP3；详见 [数据说明](SECURITY.md)。
- 原创代码采用 **[MIT](LICENSE)**。Live2D Core、Haru 模型及其他依赖有独立条款，不属于本仓库 MIT 授权。第三方资产不会随仓库分发。

This content uses sample data owned and copyrighted by Live2D Inc. The sample data are utilized in accordance with terms and conditions set by Live2D Inc. This content itself is created at the author's sole discretion.

来源与条款见 [THIRD_PARTY.md](THIRD_PARTY.md)。感谢 [pixi-live2d-display](https://github.com/guansss/pixi-live2d-display)、[PixiJS](https://github.com/pixijs/pixijs)、[edge-tts](https://github.com/rany2/edge-tts) 及实验性连接器 [douyin-ai-assist](https://github.com/Primusse/douyin-ai-assist)。

## 参与项目

欢迎可复现的问题、文档修正和小范围 PR。请阅读 [贡献指南](CONTRIBUTING.md)，使用 [Issue 模板](https://github.com/JC2065/douyin-live2d-welcome/issues/new/choose)。敏感问题参照 [安全说明](SECURITY.md)。

[变更记录](CHANGELOG.md) · [计划与限制](docs/ROADMAP.md)
