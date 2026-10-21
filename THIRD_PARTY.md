# Third-party components

The MIT license covers this repository's original Python, JavaScript, HTML and scripts only.

Third-party runtime assets, model data and the optional Douyin connector are not committed or relicensed here. `setup.ps1` downloads renderer assets and the Haru sample for local use after the user reviews their separate terms.

| Component | Source / terms |
| --- | --- |
| PixiJS 6.5.10 | https://github.com/pixijs/pixijs (MIT) |
| pixi-live2d-display 0.4.0 | https://github.com/guansss/pixi-live2d-display (MIT) |
| Live2D Cubism Core | https://www.live2d.com/en/sdk/license/ (separate proprietary terms) |
| Haru sample model | https://www.live2d.com/en/learn/sample/ (Live2D sample terms and Free Material License Agreement) |
| Optional Douyin connector | https://github.com/Primusse/douyin-ai-assist ; license not found in checked revision, not redistributed |

This content uses sample data owned and copyrighted by Live2D Inc. The sample data are utilized in accordance with terms and conditions set by Live2D Inc. This content itself is created at the author's sole discretion.

The local connector adapter expects revision `417e21474f278222a0d809ff9b15a8068e80b31b`. The original deployed copy was locally changed to enable TLS certificate validation and set a 15-second HTTP timeout. Real Douyin event delivery remains unverified; local simulation works independently of that connector.
