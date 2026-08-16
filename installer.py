"""生成「安装快捷指令」：把未签名的 .shortcut 送远程签名，签好直接进快捷指令库"""

from build import SHARE_INPUT, action, attach, end, otherwise, ref, save, tokens, uid, when, workflow

# Shortcut Source Helper「Remote Sign」背后的服务：gzip 的 plist 进，gzip 的签名件出
SIGN_URL = 'http://shortcuts.gluebyte.workers.dev/'


def build():
    zipped, req, signed, named = (uid() for _ in range(4))
    branch, ok = uid(), uid()
    # 文件的 Name 属性不含扩展名，命名时要自己补回 .shortcut
    input_name = {'Type': 'ExtensionInput', 'Aggrandizements': [
        {'Type': 'WFPropertyVariableAggrandizement',
         'PropertyName': 'Name', 'PropertyUserInfo': 'WFItemName'}]}
    resp_ext = ref(req, '签名响应', [
        {'Type': 'WFPropertyVariableAggrandizement',
         'PropertyName': 'File Extension',
         'PropertyUserInfo': 'WFFileExtensionProperty'}])
    resp_text = ref(req, '签名响应', [
        {'Type': 'WFCoercionVariableAggrandizement',
         'CoercionItemClass': 'WFStringContentItem'}])
    return workflow([
        action('comment', {'WFCommentActionText':
                           '这个快捷指令自身未签名，首次导入需要 Shortcut Source Tool 以及 Shortcut Source Helper 的远程签名服务。'
                           '两者装好后即可删除：\n'
                           '\n'
                           'Shortcut Source Tool：\n'
                           'https://www.icloud.com/shortcuts/e6fdda8687cf49b4a4c965995b70c051'
                           '\n\n'
                           'Shortcut Source Helper：\n'
                           'https://www.icloud.com/shortcuts/7125fde0360a49f5994d02fb6d1b1fbd'
                           }),
        when(SHARE_INPUT, branch),
        action('makezip', {
            'WFInput': attach(SHARE_INPUT), 'WFArchiveFormat': 'gz',
            'CustomOutputName': '压缩包', 'UUID': zipped}),
        action('downloadurl', {
            'WFURL': SIGN_URL, 'WFHTTPMethod': 'POST', 'WFHTTPBodyType': 'File',
            'WFRequestVariable': attach(ref(zipped, '压缩包')),
            'CustomOutputName': '签名响应', 'UUID': req}),
        # 签成回 .gz，失败回错误文本（服务停机时是空响应）：看扩展名分道
        when(resp_ext, ok, 4, WFConditionalActionString='gz'),
        action('unzip', {'WFArchive': attach(ref(req, '签名响应')),
                         'CustomOutputName': '签名文件', 'UUID': signed}),
        action('setitemname', {
            'WFInput': attach(ref(signed, '签名文件')),
            'WFName': tokens(input_name, '.shortcut'),
            'CustomOutputName': '安装包', 'UUID': named}),
        action('openin', {
            'WFInput': attach(ref(named, '安装包')),
            'WFOpenInAppIdentifier': 'com.apple.shortcuts',
            'WFSelectedApp': {'BundleIdentifier': 'com.apple.shortcuts',
                              'Name': 'Shortcuts', 'TeamIdentifier': '0000000000'},
            'WFOpenInAskWhenRun': False}),
        # 交接给快捷指令 App 需要片刻，立即退出会掐断打开动作
        action('delay', {'WFDelayTime': 1}),
        otherwise(ok),
        action('alert', {'WFAlertActionTitle': '签名失败',
                         'WFAlertActionMessage': tokens(
                             '远程签名服务异常，稍后再试。服务端响应：\n', resp_text),
                         'WFAlertActionCancelButtonShown': False}),
        end(ok),
        otherwise(branch),
        action('alert', {'WFAlertActionTitle': '没有拿到文件',
                         'WFAlertActionMessage':
                             '请选择一个 .shortcut 文件，然后「共享」→「安装快捷指令」',
                         'WFAlertActionCancelButtonShown': False}),
        end(branch),
    ], icon_color=3980825855, icon_glyph=61440,
        input_classes=['WFGenericFileContentItem'])


if __name__ == '__main__':
    save(build(), '安装快捷指令.shortcut')
