# 截图翻译

截图翻译是一个 iOS 快捷指令：截取屏幕、识别文字，用 Google 翻译译成中文，结果以弹窗显示并复制到剪贴板。全部使用系统自带动作，不依赖第三方 App。

## 安装

在 iPhone 上打开 [iCloud 链接](https://www.icloud.com/shortcuts/f9d4dd8784034492ae25baf71b78d930) 安装。

装好后为它绑定一个触发方式：操作按钮、轻点背面或悬浮球。后两者在 **设置** > **辅助功能** > **触控** 里设置。

## 使用

**翻译整个屏幕**：运行快捷指令，它会截屏并翻译屏幕上的文字。

**翻译选中区域**：手动截图，点左下角缩略图进入编辑，裁剪目标区域。然后从**共享**菜单中选择快捷指令 **截图翻译**。

结果默认逐行对照：原文在上、译文在下，段落间空行分隔。混排多语种时各行分别翻译。弹窗可滚动、可选中，内容同时复制到剪贴板。界面杂项（时间、电量、图标残迹）和已是中文的行会被过滤。某一行没能译成中文时，只保留原文——翻译接口认不出源语言时会退化成音译或漏词，宁可给原文。

**只看译文**：编辑快捷指令。第一个动作是个数字开关，把它从 1 改成 0，即可只显示译文。

如果翻译失败，或者识别到的内容都不值得翻译（人名、编号、纯数字），弹窗显示识别出的原文。如果一个字都没识别到，会收到一条通知。

## 从源码构建

```sh
python build.py
```

产物为 `截图翻译.shortcut`。

iOS 不允许直接导入未签名的快捷指令文件，需借助辅助快捷指令：

1. 安装 [Shortcut Installer](https://www.icloud.com/shortcuts/9918c1c856c049b4beb7918904b1fe0d)，它由本仓库的 `installer.py` 生成。
2. 把 `截图翻译.shortcut` 传到 iPhone（AirDrop、微信、QQ、Telegram 均可）。
3. 选中该文件（不必先存进「文件」App），轻点 **共享** > **Shortcut Installer**。

## License

MIT

本项目与 Apple Inc. 无关，未获其背书。Apple、iOS、快捷指令均为 Apple Inc. 的商标。

## Credits

`Shortcut Installer` 的远程签名借用了 [Shortcut Source Helper](https://www.icloud.com/shortcuts/7125fde0360a49f5994d02fb6d1b1fbd) 的服务端点；它自身首次导入到 iPhone，也要靠 [Shortcut Source Tool](https://www.icloud.com/shortcuts/e6fdda8687cf49b4a4c965995b70c051) 和 Shortcut Source Helper 完成。感谢两者的作者。
