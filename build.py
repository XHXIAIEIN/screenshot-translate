import plistlib
import sys
import uuid

MARK = '￼'
SENTINEL = '⸻'
TARGET = 'zh-CN'
MIN_LETTERS = 3
TITLE = '翻译结果'
SRC = '源图像'
DRAFT = '译稿'
GOOGLE = ('https://translate.googleapis.com/translate_a/single'
          '?client=gtx&dt=t&dj=1&sl=auto&tl=')
# 正则必须全 ASCII（非 ASCII 会被导入工具拦下，verify 兜底），非拉丁字符一律写 \u 转义
ZH = (r'(?m)^.*(?:zh|chinese|traditional'
      r'|\u4e2d\u6587|\u7e41\u4f53|\u7e41\u9ad4'
      r'|\u7ca4\u8bed|yue|cantonese).*$')
ZH_MARK = 'ZHSKIP'
SHARE_INPUT = {'Type': 'ExtensionInput'}

NOISE = (r'(?m)[ \t]*(?:>=|=>|==|[>\u203a\u00bb\u2192\u2261\u22ee\u22ef\u2630\u2605\u2606\u2713\u2715\u2717\u00d7\u25a0\u25a1\u25aa\u25b8\u25be\u2699]+'
         r'|[.\u00b7\u2022\u2026\u22ef\u2027\u2219]{2,})[ \t]*$'
         r'|^[ \t]*(?:[-=._~*\u00b7\u2022\u2026][ \t]*){2,}$'
         r'|^[ \t]*(?:[>\u2039\u203a\u00bb\u2192][ \t]*){1,12}$'
         r'|^[ \t]*[^\u4e00-\u9fff\s][ \t]*$\n?'
         r'|^[ \t]*[^\w\s]{1,3}[ \t]*$\n?'
         r'|^[ \t]*[\d :.,\-/%\u00b0+\t]+(?:[AaPp]\.?[Mm]\.?)?[ \t]*$\n?'
         r'|^[ \t]*\d+(?:[.,]\d+)?[ \t]*'
         r'(?:[Cc]m|[Mm]m|[Kk]m|[Kk]g|[Ll]bs?|[Ff]t|[Ii]n|[Mm]i|[MmGg])[ \t]*$\n?'
         r'|^[ \t]*(?![^\n]*[\u3040-\u30ff\u31f0-\u31ff\uac00-\ud7a3\uff66-\uff9d])'
         r'(?=[^\n]*[\u3400-\u9fff])[^\n]*$\n?'
         r'|^[ \t]*(?![AIaiyoeu\d\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u00ff\u1ea0-\u1ef9][ \t])(\S)\1?[ \t]+(?=\S)')
DEDUP = r'(?m)^([ \t]*[^ \t\n][^\n]*)\n(?=(?:[^\n]*\n)*\1(?:\n|$))'
BLANKS = r'(?m)(?:^[ \t]*\n)+'
UNSENTINEL = r'(?m)^[ \t]*(?:\u2e3b|[^\w\s]{1,3})[ \t]*(?=\n|$)'
JOIN = (r'(?m)([^.!?:;\u3002\uff01\uff1f\uff1a\uff1b\u17d4\u2e3b\n])\n'
        r'(?=[a-z\u00e0-\u00f6\u00f8-\u00ff\u0101-\u024f\u1e00-\u1eff])')
WRAP = (r'(?m)^([^\n]{20,}[^.!?:;\u3002\uff01\uff1f\uff1a\uff1b\u17d4\u2e3b\n])\n'
        r'(?=[\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff'
        r'\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3])')

CLEAN = [
    ('去噪文本', NOISE, '', True),
    ('去重文本', DEDUP, '', True),
    ('整理文本', BLANKS, SENTINEL + '\n', False),
    ('合并断行', JOIN, '$1 ', True),
    ('合并段落', WRAP, '$1', True),
]


# --- plist 构件 ---

def uid():
    return str(uuid.uuid4()).upper()


def prop(name):
    return [{'Type': 'WFPropertyVariableAggrandizement', 'PropertyName': name}]


def ref(action_uid, name, aggr=None):
    d = {'OutputUUID': action_uid, 'Type': 'ActionOutput', 'OutputName': name}
    if aggr:
        d['Aggrandizements'] = aggr
    return d


def variable(name):
    return {'VariableName': name, 'Type': 'Variable'}


def attach(value):
    return {'Value': value, 'WFSerializationType': 'WFTextTokenAttachment'}


def tokens(*parts):
    string, attachments = '', {}
    for part in parts:
        if isinstance(part, str):
            string += part
        else:
            attachments['{%d, 1}' % len(string)] = part
            string += MARK
    return {'Value': {'string': string, 'attachmentsByRange': attachments},
            'WFSerializationType': 'WFTextTokenString'}


def action(name, params):
    return {'WFWorkflowActionIdentifier': 'is.workflow.actions.' + name,
            'WFWorkflowActionParameters': params}


def setvar(value, name):
    return action('setvariable', {'WFInput': attach(value), 'WFVariableName': name})


def replace(text, find, repl, name, case_sensitive=True):
    step = uid()
    return action('text.replace', {
        'WFInput': tokens(text),
        'WFReplaceTextFind': find,
        'WFReplaceTextRegularExpression': True,
        'WFReplaceTextCaseSensitive': case_sensitive,
        'WFReplaceTextReplace': repl,
        'CustomOutputName': name, 'UUID': step}), ref(step, name)


def when(value, group, condition=100, **extra):
    # WFCondition：100 有值，'Contains' 包含，2 大于
    return action('conditional', {
        'WFInput': {'Type': 'Variable', 'Variable': attach(value)},
        'WFCondition': condition,
        'GroupingIdentifier': group, 'WFControlFlowMode': 0, **extra})


def otherwise(group):
    return action('conditional', {'GroupingIdentifier': group, 'WFControlFlowMode': 1})


def end(group):
    return action('conditional', {'GroupingIdentifier': group, 'WFControlFlowMode': 2})


def workflow(icon_color, actions, input_classes):
    return {
        'WFWorkflowMinimumClientVersionString': '900',
        'WFWorkflowMinimumClientVersion': 900,
        'WFWorkflowIcon': {'WFWorkflowIconStartColor': icon_color,
                           'WFWorkflowIconGlyphNumber': 59729},
        'WFWorkflowClientVersion': '4046.0.2.1.102',
        'WFWorkflowOutputContentItemClasses': [],
        'WFWorkflowHasOutputFallback': False,
        'WFWorkflowActions': actions,
        'WFWorkflowInputContentItemClasses': input_classes,
        'WFWorkflowTypes': ['ActionExtension', 'WFWorkflowTypeShowInSearch'],
        'WFWorkflowImportQuestions': [],
        'WFQuickActionSurfaces': [],
        'WFWorkflowHasShortcutInputVariables': True,
    }


# --- 流程 ---

def source():
    shot, top, height, crop, ocr, branch = (uid() for _ in range(6))
    acts = [
        action('comment', {'WFCommentActionText':
            '分享表单进来 = 翻译截图裁好的选区；直接运行 = 现场截屏并裁掉顶栏底栏，'
            '得从返回轻点 / 操作按钮 / 辅助触控触发，否则截到的是快捷指令 App 自己'}),
        when(SHARE_INPUT, branch),
        setvar(SHARE_INPUT, SRC),
        otherwise(branch),
        action('takescreenshot', {'UUID': shot}),
        action('math', {
            'WFInput': attach(ref(shot, '截屏', prop('Height'))),
            'WFMathOperation': '×', 'WFMathOperand': '13E-2',
            'CustomOutputName': '顶栏高度', 'UUID': top}),
        action('math', {
            'WFInput': attach(ref(shot, '截屏', prop('Height'))),
            'WFMathOperation': '×', 'WFMathOperand': '735E-3',
            'CustomOutputName': '内容高度', 'UUID': height}),
        action('image.crop', {
            'WFInput': attach(ref(shot, '截屏')),
            'WFImageCropPosition': 'Custom',
            'WFImageCropX': '0', 'WFImageCropY': attach(ref(top, '顶栏高度')),
            'WFImageCropWidth': attach(ref(shot, '截屏', prop('Width'))),
            'WFImageCropHeight': attach(ref(height, '内容高度')),
            'CustomOutputName': '内容图像', 'UUID': crop}),
        setvar(ref(crop, '内容图像'), SRC),
        end(branch),
        action('extracttextfromimage', {
            'WFImage': attach(variable(SRC)), 'CustomOutputName': '提取文本', 'UUID': ocr}),
    ]
    return acts, ref(ocr, '提取文本')


def cleanup(text):
    acts = []
    for name, find, repl, case_sensitive in CLEAN:
        act, text = replace(text, find, repl, name, case_sensitive)
        acts.append(act)
    return acts, text


def google(text):
    req, rows, loop, joined = (uid() for _ in range(4))
    return ([
        action('downloadurl', {
            'WFURL': GOOGLE + TARGET,
            'WFHTTPMethod': 'POST',
            'WFHTTPBodyType': 'Form',
            'WFFormValues': {'Value': {'WFDictionaryFieldValueItems': [{
                'WFItemType': 0,
                'WFKey': {'Value': {'string': 'q'},
                          'WFSerializationType': 'WFTextTokenString'},
                'WFValue': tokens(text)}]},
                'WFSerializationType': 'WFDictionaryFieldValue'},
            'CustomOutputName': '接口响应', 'UUID': req}),
        action('getvalueforkey', {
            'WFInput': attach(ref(req, '接口响应')),
            'WFDictionaryKey': 'sentences', 'WFGetDictionaryValueType': 'Value',
            'CustomOutputName': '句子表', 'UUID': rows}),
        # sentences 是字典列表，直接取键会弹「选取项目」，必须逐项遍历
        action('repeat.each', {
            'WFInput': attach(ref(rows, '句子表')),
            'GroupingIdentifier': loop, 'WFControlFlowMode': 0}),
        action('getvalueforkey', {
            'WFDictionaryKey': 'trans', 'WFGetDictionaryValueType': 'Value'}),
        action('repeat.each', {
            'GroupingIdentifier': loop, 'WFControlFlowMode': 2,
            'CustomOutputName': '译文片段'}),
        action('text.combine', {
            'WFTextSeparator': 'Custom', 'WFTextCustomSeparator': '',
            'CustomOutputName': '拼接译文', 'UUID': joined}),
    ], ref(joined, '拼接译文'))


def route(text):
    """系统翻译试过又撤了：没装语言包时回空值，不支持的语言退化成罗马字音译——
    后者有值不算失败，「空值才回退 Google」的判据抓不住它，非中文只能一律走 Google"""
    lang, zh_branch = uid(), uid()
    lang_ref = ref(lang, '语言')
    mark_act, mark = replace(lang_ref, ZH, ZH_MARK, '免译判定', False)
    google_acts, google_out = google(text)
    return [
        action('detectlanguage', {
            'WFInput': tokens(text), 'CustomOutputName': '语言', 'UUID': lang}),
        mark_act,
        when(mark, zh_branch, 'Contains', WFConditionalActionString=tokens(ZH_MARK)),
        setvar(text, DRAFT),
        otherwise(zh_branch),
        *google_acts,
        setvar(google_out, DRAFT),
        end(zh_branch),
    ], lang_ref


def deliver(text):
    count, named, enough, translated = (uid() for _ in range(4))
    route_acts, lang_ref = route(text)
    # 图标残迹、时间电量这类漏网的碎片往往只剩一两个字母，攒不够数就不值得翻译
    letters_act, letters = replace(text, r'[\W\d_]', '', '字母序列', False)
    restore_act, restored = replace(variable(DRAFT), UNSENTINEL, '', '译文', False)
    return [
        letters_act,
        action('count', {'Input': attach(letters), 'WFCountType': 'Characters',
                         'CustomOutputName': '字母数', 'UUID': count}),
        when(ref(count, '字母数'), enough, 2, WFNumberValue=MIN_LETTERS),
        *route_acts,
        restore_act,
        when(restored, translated),
        action('setclipboard', {'WFInput': attach(restored)}),
        # 快速查看的窗口标题取自条目名，不改名会拿译文第一行当标题
        action('setitemname', {
            'WFInput': attach(restored), 'WFName': tokens(TITLE),
            'CustomOutputName': '展示稿', 'UUID': named}),
        # 「显示结果」只在快捷指令编辑器里预览得到，从返回轻点或分享表单触发时一声不响
        action('previewdocument', {'WFInput': attach(ref(named, '展示稿'))}),
        otherwise(translated),
        # 译空了就留原文，顺带报出检测到的语言——免译名单该添哪一条，看这个就知道
        action('setclipboard', {'WFInput': attach(text)}),
        action('notification', {
            'WFNotificationActionBody': tokens('没译出来，原文已复制。检测到的语言：', lang_ref),
            'WFNotificationActionSound': False}),
        end(translated),
        otherwise(enough),
        action('notification', {'WFNotificationActionBody': '没有识别到值得翻译的文字',
                                'WFNotificationActionSound': False}),
        end(enough),
    ]


def build():
    head, ocr_text = source()
    body, clean_text = cleanup(ocr_text)
    return workflow(946986751, head + body + deliver(clean_text), ['WFImageContentItem'])


def verify(workflow):
    """落盘前自检：引用完整性、条件块配平、占位符对齐、正则的 ASCII 约束"""
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


def save(workflow, default_name):
    """落盘到命令行指定的路径，缺省写到当前目录"""
    verify(workflow)
    dst = sys.argv[1] if len(sys.argv) > 1 else default_name
    with open(dst, 'wb') as f:
        plistlib.dump(workflow, f, fmt=plistlib.FMT_BINARY)
    print('written:', dst, len(workflow['WFWorkflowActions']), 'actions')


if __name__ == '__main__':
    save(build(), '截图翻译.shortcut')
