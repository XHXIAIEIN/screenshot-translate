import os
import plistlib
import uuid

MARK = '\ufffc'
SENTINEL = '\u2E3B'
AS_TEXT = [{'Type': 'WFCoercionVariableAggrandizement',
            'CoercionItemClass': 'WFStringContentItem'}]
SHARE_INPUT = {'Type': 'ExtensionInput'}
IMG = {'VariableName': '源图像', 'Type': 'Variable'}

NOISE = (r'(?m)[ \t]*(?:>=|=>|==|[>\u203A\u00BB\u2192])[ \t]*$'
         r'|^[ \t]*(?:[-=._~*\u00B7\u2022\u2026][ \t]*){3,}$'
         r'|^[ \t]*(?:[>\u2039\u203A\u00BB\u2192][ \t]*){1,12}$'
         r'|^[ \t]*[^\u4E00-\u9FFF\s][ \t]*$\n?'
         r'|^[ \t]*(?=[^\n]*[\u3400-\u9FFF])[^A-Za-z\n]*$\n?')
DEDUP = r'(?m)^([ \t]*[^ \t\n][^\n]*)\n(?=(?:[^\n]*\n)*\1(?:\n|$))'
BLANKS = r'(?m)(?:^[ \t]*\n)+'
UNSENTINEL = r'(?m)^[ \t]*\u2E3B[ \t]*(?=\n|$)'
JOIN = r'(?m)([^.!?:;\u3002\uFF01\uFF1F\uFF1A\uFF1B\u2E3B\n])\n(?=[a-z])'

CLEAN = [
    ('去噪文本', NOISE, '', False),
    ('去重文本', DEDUP, '', True),
    ('整理文本', BLANKS, SENTINEL + '\n', False),
    ('合并断行', JOIN, '$1 ', True),
]


def uid():
    return str(uuid.uuid4()).upper()


def prop(name):
    return [{'Type': 'WFPropertyVariableAggrandizement', 'PropertyName': name}]


def ref(action_uid, name, aggr=None):
    d = {'OutputUUID': action_uid, 'Type': 'ActionOutput', 'OutputName': name}
    if aggr:
        d['Aggrandizements'] = aggr
    return d


def attach(value):
    return {'Value': value, 'WFSerializationType': 'WFTextTokenAttachment'}


def inline(value):
    return {'Value': {'string': MARK, 'attachmentsByRange': {'{0, 1}': value}},
            'WFSerializationType': 'WFTextTokenString'}


def action(name, params):
    return {'WFWorkflowActionIdentifier': 'is.workflow.actions.' + name,
            'WFWorkflowActionParameters': params}


def when(value, group):
    return action('conditional', {
        'WFInput': {'Type': 'Variable', 'Variable': attach(value)},
        'WFCondition': 100,
        'GroupingIdentifier': group, 'WFControlFlowMode': 0})


def otherwise(group):
    return action('conditional', {'GroupingIdentifier': group, 'WFControlFlowMode': 1})


def end(group):
    return action('conditional', {'GroupingIdentifier': group, 'WFControlFlowMode': 2})


def source():
    shot, top, height, crop, ocr, branch = (uid() for _ in range(6))
    acts = [
        action('comment', {'WFCommentActionText':
            '截图 -> 裁剪 → 分享到快捷指令；直接运行 = 现场截屏并裁掉通知栏+底部导航栏'}),
        when(SHARE_INPUT, branch),
        action('setvariable', {'WFInput': attach(SHARE_INPUT), 'WFVariableName': '源图像'}),
        otherwise(branch),
        action('takescreenshot', {'UUID': shot}),
        action('math', {
            'WFInput': attach(ref(shot, '截屏', prop('Height'))),
            'WFMathOperation': '×', 'WFMathOperand': '0.13',
            'CustomOutputName': '顶栏高度', 'UUID': top}),
        action('math', {
            'WFInput': attach(ref(shot, '截屏', prop('Height'))),
            'WFMathOperation': '×', 'WFMathOperand': '0.735',
            'CustomOutputName': '内容高度', 'UUID': height}),
        action('image.crop', {
            'WFInput': attach(ref(shot, '截屏')),
            'WFImageCropPosition': 'Custom',
            'WFImageCropX': '0', 'WFImageCropY': attach(ref(top, '顶栏高度')),
            'WFImageCropWidth': attach(ref(shot, '截屏', prop('Width'))),
            'WFImageCropHeight': attach(ref(height, '内容高度')),
            'CustomOutputName': '内容图像', 'UUID': crop}),
        action('setvariable', {'WFInput': attach(ref(crop, '内容图像')),
                               'WFVariableName': '源图像'}),
        end(branch),
        action('extracttextfromimage', {
            'WFImage': attach(IMG), 'CustomOutputName': '提取文本', 'UUID': ocr}),
    ]
    return acts, ref(ocr, '提取文本')


def cleanup(text):
    acts = []
    for name, find, repl, case_sensitive in CLEAN:
        step = uid()
        acts.append(action('text.replace', {
            'WFInput': inline(text),
            'WFReplaceTextFind': find,
            'WFReplaceTextRegularExpression': True,
            'WFReplaceTextCaseSensitive': case_sensitive,
            'WFReplaceTextReplace': repl,
            'CustomOutputName': name, 'UUID': step}))
        text = ref(step, name)
    return acts, text


def deliver(text):
    trans, restore, branch = (uid() for _ in range(3))
    return [
        when(text, branch),
        action('text.translate', {
            'WFInputText': inline(text), 'WFSelectedLanguage': 'zh_CN', 'UUID': trans}),
        action('text.replace', {
            'WFInput': inline(ref(trans, '翻译后的文本', AS_TEXT)),
            'WFReplaceTextFind': UNSENTINEL,
            'WFReplaceTextRegularExpression': True,
            'WFReplaceTextCaseSensitive': False,
            'WFReplaceTextReplace': '',
            'CustomOutputName': '译文', 'UUID': restore}),
        action('setclipboard', {'WFInput': attach(ref(restore, '译文'))}),
        action('showresult', {'Text': inline(ref(restore, '译文'))}),
        otherwise(branch),
        action('notification', {'WFNotificationActionBody': '未识别到文字',
                                'WFNotificationActionSound': False}),
        end(branch),
    ]


def build():
    head, ocr_text = source()
    body, clean_text = cleanup(ocr_text)
    return {
        'WFWorkflowMinimumClientVersionString': '900',
        'WFWorkflowMinimumClientVersion': 900,
        'WFWorkflowIcon': {'WFWorkflowIconStartColor': 946986751,
                           'WFWorkflowIconGlyphNumber': 59729},
        'WFWorkflowClientVersion': '4046.0.2.1.102',
        'WFWorkflowOutputContentItemClasses': [],
        'WFWorkflowHasOutputFallback': False,
        'WFWorkflowActions': head + body + deliver(clean_text),
        'WFWorkflowInputContentItemClasses': ['WFImageContentItem'],
        'WFWorkflowTypes': ['ActionExtension', 'WFWorkflowTypeShowInSearch'],
        'WFWorkflowImportQuestions': [],
        'WFQuickActionSurfaces': [],
        'WFWorkflowHasShortcutInputVariables': True,
    }


def verify(workflow):
    acts = workflow['WFWorkflowActions']
    known = {a['WFWorkflowActionParameters']['UUID'] for a in acts
             if 'UUID' in a['WFWorkflowActionParameters']}
    errors, depth = [], 0

    def check(node):
        if isinstance(node, dict):
            if node.get('Type') == 'ActionOutput' and node.get('OutputUUID') not in known:
                errors.append('未定义的 OutputUUID')
            if node.get('WFSerializationType') == 'WFTextTokenString':
                v = node['Value']
                for pos in v.get('attachmentsByRange', {}):
                    if v['string'][int(pos.strip('{}').split(',')[0])] != MARK:
                        errors.append('占位符错位 ' + pos)
            for x in node.values():
                check(x)
        elif isinstance(node, list):
            for x in node:
                check(x)

    for a in acts:
        params = a['WFWorkflowActionParameters']
        if a['WFWorkflowActionIdentifier'].endswith('.conditional'):
            depth += {0: 1, 1: 0, 2: -1}[params['WFControlFlowMode']]
            assert depth >= 0
        find = params.get('WFReplaceTextFind')
        if find and not find.isascii():
            errors.append('正则含非 ASCII')
        check(params)
    if depth:
        errors.append('条件块不配平')
    assert not errors, errors


def main():
    workflow = build()
    verify(workflow)
    dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), '截图翻译.shortcut')
    with open(dst, 'wb') as f:
        plistlib.dump(workflow, f, fmt=plistlib.FMT_BINARY)
    print('written:', dst, len(workflow['WFWorkflowActions']), 'actions')


if __name__ == '__main__':
    main()
