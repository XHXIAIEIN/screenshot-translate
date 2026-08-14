import plistlib
import sys
import uuid

MARK = '￼'  # 对象替换字符，标记文本模板里附件的插入点
SENTINEL = '⸻'  # 翻译接口会吞空行：段落间隔先换成哨兵行，译完再还原
TARGET = 'zh-CN'
MIN_LETTERS = 3
TITLE = '翻译结果'
SHARE_INPUT = {'Type': 'ExtensionInput'}

# --- 清理规则 ---
# 正则在快捷指令的替换动作里执行，统一写 \uXXXX 转义保持 ASCII（verify 强制）

NOISE = '(?m)' + '|'.join([
    # 行尾的箭头、勾叉、图标类符号，或连串的点
    r'[ \t]*(?:>=|=>|==|[>\u203a\u00bb\u2192\u2261\u22ee\u22ef\u2630\u2605\u2606'
    r'\u2713\u2715\u2717\u00d7\u25a0\u25a1\u25aa\u25b8\u25be\u2699]+'
    r'|[.\u00b7\u2022\u2026\u22ef\u2027\u2219]{2,})[ \t]*$',
    # 整行只有分隔线
    r'^[ \t]*(?:[-=._~*\u00b7\u2022\u2026][ \t]*){2,}$',
    # 整行只有箭头
    r'^[ \t]*(?:[>\u2039\u203a\u00bb\u2192][ \t]*){1,12}$',
    # 整行只有一个非汉字字符
    r'^[ \t]*[^\u4e00-\u9fff\s][ \t]*$\n?',
    # 整行只有一至三个符号
    r'^[ \t]*[^\w\s]{1,3}[ \t]*$\n?',
    # 整行是时间、日期、电量这类数字串
    r'^[ \t]*[\d :.,\-/%\u00b0+\t]+(?:[AaPp]\.?[Mm]\.?)?[ \t]*$\n?',
    # 整行是数字加计量单位
    r'^[ \t]*\d+(?:[.,]\d+)?[ \t]*'
    r'(?:[Cc]m|[Mm]m|[Kk]m|[Kk]g|[Ll]bs?|[Ff]t|[Ii]n|[Mm]i|[MmGg])[ \t]*$\n?',
    # 有汉字、无假名和谚文的行：已经是中文，不进翻译
    r'^[ \t]*(?![^\n]*[\u3040-\u30ff\u31f0-\u31ff\uac00-\ud7a3\uff66-\uff9d])'
    r'(?=[^\n]*[\u3400-\u9fff])[^\n]*$\n?',
    # 行首一两个字符的孤立碎片；放过单字母词、数字和带变音符的字母
    r'^[ \t]*(?![AIaiyoeu\d\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u00ff\u1ea0-\u1ef9][ \t])'
    r'(\S)\1?[ \t]+(?=\S)',
])
# 一行在后文原样重现时，删掉靠前的那次
DEDUP = r'(?m)^([ \t]*[^ \t\n][^\n]*)\n(?=(?:[^\n]*\n)*\1(?:\n|$))'
# 连续空行
BLANKS = r'(?m)(?:^[ \t]*\n)+'
# 译文里的哨兵行；哨兵可能被翻译改写成别的符号
UNSENTINEL = r'(?m)^[ \t]*(?:\u2e3b|[^\w\s]{1,3})[ \t]*(?=\n|$)'
# 行尾没收句、下一行以小写字母开头：把硬换行并回空格
JOIN = (r'(?m)([^.!?:;\u3002\uff01\uff1f\uff1a\uff1b\u17d4\u2e3b\n])\n'
        r'(?=[a-z\u00e0-\u00f6\u00f8-\u00ff\u0101-\u024f\u1e00-\u1eff])')
# 长行没收句、下一行是中日韩等不用空格分词的文字：直接接上
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
    # WFCondition：100 有值，'Contains' 包含，2 大于，4 等于
    return action('conditional', {
        'WFInput': {'Type': 'Variable', 'Variable': attach(value)},
        'WFCondition': condition,
        'GroupingIdentifier': group, 'WFControlFlowMode': 0, **extra})


def otherwise(group):
    return action('conditional', {'GroupingIdentifier': group, 'WFControlFlowMode': 1})


def end(group):
    return action('conditional', {'GroupingIdentifier': group, 'WFControlFlowMode': 2})


def workflow(actions):
    return {
        'WFWorkflowMinimumClientVersionString': '900',
        'WFWorkflowMinimumClientVersion': 900,
        'WFWorkflowIcon': {'WFWorkflowIconStartColor': 946986751, 'WFWorkflowIconGlyphNumber': 59729},
        'WFWorkflowClientVersion': '4046.0.2.1.102',
        'WFWorkflowOutputContentItemClasses': [],
        'WFWorkflowHasOutputFallback': False,
        'WFWorkflowActions': actions,
        'WFWorkflowInputContentItemClasses': ['WFImageContentItem'],
        'WFWorkflowTypes': ['ActionExtension', 'WFWorkflowTypeShowInSearch'],
        'WFWorkflowImportQuestions': [],
        'WFQuickActionSurfaces': [],
        'WFWorkflowHasShortcutInputVariables': True,
    }


# --- 流程 ---

def source():
    src = '源图像'
    shot, top, height, crop, ocr, branch = (uid() for _ in range(6))
    return [
        when(SHARE_INPUT, branch),
        setvar(SHARE_INPUT, src),
        otherwise(branch),
        action('takescreenshot', {'UUID': shot}),
        # 比例写 E 记数法：小数点在部分地区解析有歧义，小数写法会被导入工具拦下
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
        setvar(ref(crop, '内容图像'), src),
        end(branch),
        action('extracttextfromimage', {
            'WFImage': attach(variable(src)), 'CustomOutputName': '提取文本', 'UUID': ocr}),
    ], ref(ocr, '提取文本')


def cleanup(text):
    acts = []
    for name, find, repl, case_sensitive in CLEAN:
        act, text = replace(text, find, repl, name, case_sensitive)
        acts.append(act)
    return acts, text


AS_TEXT = [{'Type': 'WFCoercionVariableAggrandizement',
            'CoercionItemClass': 'WFStringContentItem'}]
# 响应 JSON 里的译文值；转义序列整体吞进捕获组
TRANS = r'"trans":"((?:[^"\\]|\\.)*)"'


def google(text):
    """不用系统翻译（本可不出设备）：不支持的语言不报错，退化成罗马字音译——
    有值不算失败，「空值才回退」在快捷指令里兜不住"""
    url = ('https://translate.googleapis.com/translate_a/single'
           '?client=gtx&dt=t&dj=1&sl=auto&tl=' + TARGET + '&q=')
    enc, req, match, groups, joined = (uid() for _ in range(5))
    acts = [
        # 文本编码后拼进 URL 走 GET。POST 的坑趟遍了：「表单」体实为 multipart，
        # 接口只认 urlencoded；「文件」体的自定义 Content-Type 头不生效——
        # 两种都拿到 400 错误页，动作不报错，最终表现为译文为空
        action('urlencode', {'WFInput': tokens(text), 'WFEncodeMode': 'Encode',
                             'CustomOutputName': '编码文本', 'UUID': enc}),
        action('downloadurl', {
            'WFURL': tokens(url, ref(enc, '编码文本')),
            'CustomOutputName': '接口响应', 'UUID': req}),
        # 「获取词典值」加逐项循环在设备上取不出译文（请求和取键都成功，循环
        # 聚合为空）：改把响应当文本，正则一次抽出全部 trans，绕开字典和循环
        action('text.match', {
            'WFMatchTextPattern': TRANS,
            'text': tokens(ref(req, '接口响应', AS_TEXT)),
            'CustomOutputName': '匹配', 'UUID': match}),
        action('text.match.getgroup', {
            'matches': attach(ref(match, '匹配')),
            'WFGetGroupType': 'All Groups',
            'CustomOutputName': '译文组', 'UUID': groups}),
        action('text.combine', {
            'text': attach(ref(groups, '译文组')),
            'WFTextSeparator': 'Custom', 'WFTextCustomSeparator': '',
            'CustomOutputName': '拼接译文', 'UUID': joined}),
    ]
    # 译文值仍是 JSON 字符串字面量：还原常见转义，罕见的 \uXXXX 残留不管
    out = ref(joined, '拼接译文')
    for name, find, repl in [('还原换行', r'\\n', '\n'),
                             ('还原引号', r'\\"', '"'),
                             ('还原撇号', r'\\u0027', "'")]:
        act, out = replace(out, find, repl, name, False)
        acts.append(act)
    return acts, out


def deliver(text):
    count, named, enough, translated = (uid() for _ in range(4))
    google_acts, google_out = google(text)
    letters_act, letters = replace(text, r'[\W\d_]', '', '字母序列', False)
    restore_act, restored = replace(google_out, UNSENTINEL, '', '译文', False)
    return [
        letters_act,
        action('count', {'Input': attach(
            letters), 'WFCountType': 'Characters', 'CustomOutputName': '字母数', 'UUID': count}),
        when(ref(count, '字母数'), enough, 2, WFNumberValue=MIN_LETTERS),
        *google_acts,
        restore_act,
        when(restored, translated),
        action('setclipboard', {'WFInput': attach(restored)}),
        action('setitemname', {
            'WFInput': attach(restored), 'WFName': tokens(TITLE),
            'CustomOutputName': '展示稿', 'UUID': named}),
        action('previewdocument', {'WFInput': attach(ref(named, '展示稿'))}),
        otherwise(translated),
        action('setclipboard', {'WFInput': attach(text)}),
        action('notification', {
            'WFNotificationActionBody': '没译出来，原文已复制',
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
    return workflow(head + body + deliver(clean_text))


def verify(wf):
    """落盘前自检：引用完整性、条件块配平、占位符对齐、正则的 ASCII 约束"""
    acts = wf['WFWorkflowActions']
    known = {a['WFWorkflowActionParameters']['UUID'] for a in acts
             if 'UUID' in a['WFWorkflowActionParameters']}
    errors, depth = [], 0

    def check(node):
        if isinstance(node, dict):
            if node.get('Type') == 'ActionOutput' and node.get('OutputUUID') not in known:
                errors.append('未定义的 OutputUUID')
            if node.get('WFSerializationType') == 'WFTextTokenString':
                value = node['Value']
                for pos in value.get('attachmentsByRange', {}):
                    start = int(pos.strip('{}').split(',')[0])
                    if value['string'][start] != MARK:
                        errors.append('占位符错位 ' + pos)
            for child in node.values():
                check(child)
        elif isinstance(node, list):
            for child in node:
                check(child)

    for a in acts:
        params = a['WFWorkflowActionParameters']
        if a['WFWorkflowActionIdentifier'].endswith('.conditional'):
            depth += {0: 1, 1: 0, 2: -1}[params['WFControlFlowMode']]
            if depth < 0:
                errors.append('条件块在开启前闭合')
        find = params.get('WFReplaceTextFind')
        if find and not find.isascii():
            errors.append('正则含非 ASCII')
        check(params)
    if depth:
        errors.append('条件块不配平')
    assert not errors, errors


def save(wf, default_name):
    """落盘到命令行指定的路径，缺省写到当前目录"""
    verify(wf)
    dst = sys.argv[1] if len(sys.argv) > 1 else default_name
    with open(dst, 'wb') as f:
        plistlib.dump(wf, f, fmt=plistlib.FMT_BINARY)
    print('written:', dst, len(wf['WFWorkflowActions']), 'actions')


if __name__ == '__main__':
    save(build(), '截图翻译.shortcut')
