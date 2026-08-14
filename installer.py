"""生成「导入快捷指令」：把未签名的 .shortcut 交给 Shortcut Source Helper 签名并加入库。"""

from build import SHARE_INPUT, action, attach, end, otherwise, save, setvar, uid, variable, when, workflow

HELPER = 'Shortcut Source Helper'
SRC = '源文件'
HINT = '在「文件」里长按 .shortcut，选择「共享」→「导入快捷指令」'


def call_helper(source):
    """Helper 拿到 plist 就签名建快捷指令，名字取自文件名，不必再手动命名"""
    return action('runworkflow', {
        'WFWorkflowName': HELPER,
        'WFWorkflow': {
            'Value': {'ActionIdentifier': 'is.workflow.actions.runworkflow',
                      'isSelf': False, 'workflowName': HELPER},
            'WFSerializationType': 'WFWorkflowReference'},
        'WFInput': attach(source),
        'WFShowWorkflow': False})


def build():
    branch = uid()
    return workflow(3980825855, [
        action('comment', {'WFCommentActionText':
            '签名这一步 iOS 做不到，只能转给 Shortcut Source Helper，'
            '它会联网远程签名或走 SSH 交给 Mac'}),
        when(SHARE_INPUT, branch),
        setvar(SHARE_INPUT, SRC),
        call_helper(variable(SRC)),
        otherwise(branch),
        # 直接运行时没有输入，Helper 会转去让你选一个已有的快捷指令，不是我们要的
        action('alert', {'WFAlertActionTitle': '没有拿到文件',
                         'WFAlertActionMessage': HINT,
                         'WFAlertActionCancelButtonShown': False}),
        end(branch),
    ], ['WFGenericFileContentItem'])


if __name__ == '__main__':
    save(build(), '导入快捷指令.shortcut')
