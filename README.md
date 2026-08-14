# 截图翻译

iOS 快捷指令：截屏 → OCR → Google 翻译 → 复制并弹窗显示。
不装任何第三方 App，全部使用系统自带动作。

建议用**操作按钮**、轻点背面或悬浮球触发（设置 → 辅助功能 → 触控）。

## 安装

iOS 不接受未签名的 `.shortcut`，所以先装好本仓库的「导入快捷指令」——以后任何 `.shortcut` 都由它一键导入。

首次安装（两个工具装完都可以删）：

1. 安装 [Shortcut Source Tool](https://www.icloud.com/shortcuts/e6fdda8687cf49b4a4c965995b70c051) 和 [Shortcut Source Helper](https://www.icloud.com/shortcuts/7125fde0360a49f5994d02fb6d1b1fbd)
2. 把 `导入快捷指令.shortcut` 存进「文件」
3. 运行 Shortcut Source Tool，选 **📝 File**（不要选 💫 Shortcut），选中刚存的文件
4. 依次选 **Edit/Restore Source** → **Skip** → 右上角 ☑️ → 命名 → **Done** → **Remote Sign**，完成后自动进入快捷指令库

之后导入就是一个动作：把 `.shortcut` 传到 iPhone（微信 / AirDrop 均可），在「文件」里长按 → **共享** → **导入快捷指令**。用它装好 `截图翻译.shortcut`，完成。

## 用法

- **直接运行**：自动截屏，裁掉顶部通知栏和底部导航栏，翻译整屏内容
- **选区翻译**：手动截图 → 点缩略图 → 拖裁剪框 → 分享 → 选本快捷指令

译文自动复制进剪贴板，并弹窗显示，可滚动可选中，段落结构保留。界面噪音（时间电量、图标残迹）和中文行会被自动剔除；没识别到值得翻译的文字、或没译出来时，通知一声，剪贴板留原文。

文本发给 Google 的公开翻译端点（**出设备**），介意的话别用。

## 自定义

改 `build.py` 后重新运行 `python build.py` 生成：

- `TARGET`：目标语言
- `MIN_LETTERS`：起译门槛
- `TITLE`：弹窗标题
- 清洗正则、裁剪比例：见文件头部和 `source()`

## License

MIT
