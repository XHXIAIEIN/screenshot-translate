# 截图翻译

iOS 快捷指令：截屏 → OCR → 文本清洗 → 系统翻译 → 复制并显示。
不依赖第三方 App，全部使用系统自带动作。`.shortcut` 文件由 Python 脚本生成，可在任意平台构建。

## 用法

两条路线，运行时自动区分：

- **直接运行**：现场截屏，按比例裁掉顶部通知栏和底部导航栏，翻译整屏内容
- **选区翻译**：截图 → 点缩略图 → 拖裁剪框 → 完成 → 分享 → 选本快捷指令，只翻译你框选的区域

译文自动复制进剪贴板并弹窗显示，段落结构保留。

## 安装

未签名的 `.shortcut` 文件不能直接导入，需要经 [Shortcut Source Tool](https://routinehub.co/shortcut/5256/) 签名导入：

1. iPhone 安装 Shortcut Source Tool 及配套的 Shortcut Source Helper
2. 把 `截图翻译.shortcut` 传到 iPhone（微信 / AirDrop / 文件均可）
3. 用 Shortcut Source Tool 打开该文件：
   1. 选择 **Edit/Restore Source**
   2. 选择 **Skip**
   3. 点击右上角 ☑️ 按钮，为 shortcut 命名后点击 **Done**
   4. 选择 **Remote Sign**，签名完成后即加入快捷指令库

## 自定义

改 `build.py` 后重新运行 `python build.py` 即可：

- 裁剪比例：`source()` 里两个 math 动作的 `0.13`（顶部）和 `0.735`（保留高度）
- 目标语言：`deliver()` 里的 `zh_CN`
- 清洗规则：文件头部的正则表（去噪 / 去重 / 空行折叠 / 断行合并）

## 原理

`.shortcut` 是二进制 plist，`build.py` 直接构造动作数组并序列化，落盘前自检（UUID 引用完整性、条件块配平、变量占位符对齐）。

OCR 清洗链按序执行四步正则替换：

1. **去噪**：删除装饰箭头、分隔线、被误识别成字符的图标、无需翻译的中文行
2. **去重**：同一行文本重复出现只保留一次（如 UI 按钮词）
3. **空行折叠**：段落边界折叠为哨兵字符，翻译后还原，保住段落结构
4. **断行合并**：行尾无标点且下行小写开头的 OCR 断行拼回同一句，显著提升译文质量

## License

MIT
