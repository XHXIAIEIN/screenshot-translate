import plistlib
import sys
import uuid

MARK = '￼'  # 对象替换字符，标记文本模板里附件的插入点
SENTINEL = '⸻'  # 段落间隔的占位行，译完还原
MIN_LETTERS = 2  # 不超过该词长的拉丁词不算翻译内容
TARGET = 'zh-CN'
# 判定一行是否已是目标语言的字符类，随 TARGET 一起改
TARGET_CHARS = r'\u3400-\u9fff'
# 日韩也写汉字，命中这些就不算目标语言
TARGET_EXCLUDE = r'\u3040-\u30ff\u31f0-\u31ff\uac00-\ud7a3\uff66-\uff9d'
TITLE = '翻译结果'
ORIGINAL = '原文'  # 没有译文可给时的展示标题
BILINGUAL = 1  # 对照开关的缺省值：1 双语对照，0 只显示译文
TOP_INSET = 0
BOTTOM_INSET = 0
SHARE_INPUT = {'Type': 'ExtensionInput'}

# --- 清理规则 ---

NOISE = '(?m)' + '|'.join([
    # 行尾的箭头、勾叉、图标类符号，或连串的点
    r'[ \t]*(?:>=|=>|==|[>\u203a\u00bb\u2192\u2261\u22ee\u22ef\u2630\u2605'
    r'\u2606\u2713\u2715\u2717\u00d7\u25a0\u25a1\u25aa\u25b8\u25be\u2699]+'
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
    # 已经是目标语言的行，不进翻译
    rf'^[ \t]*(?![^\n]*[{TARGET_EXCLUDE}])'
    rf'(?=[^\n]*[{TARGET_CHARS}])[^\n]*$\n?',
    # 行首一两个字符的孤立碎片
    r'^[ \t]*(?![AEIOUYaeiouy\d$\u00a5\u20ac\u00a3\u20a9'
    r'\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u00ff\u1ea0-\u1ef9][ \t])'
    r'(?=[\x00-\x7f]|[^\w])'
    r'(\S)\1?[ \t]+(?=\S)',
])
# 一行在后文原样重现时，删掉靠前的那次
DEDUP = r'(?m)^([ \t]*[^ \t\n][^\n]*)\n(?=(?:[^\n]*\n)*\1(?:\n|$))'
# 连续空行
BLANKS = r'(?m)(?:^[ \t]*\n)+'
# 译文里的哨兵行，可能已被翻译改写成别的符号
UNSENTINEL = r'(?m)^[ \t]*(?:\u2e3b|[^\w\s]{1,3})[ \t]*(?=\n|$)'
# 行尾没收句、下一行以小写字母开头：把硬换行并回空格
JOIN = (r'(?m)([^.!?:;\u3002\uff01\uff1f\uff1a\uff1b\u17d4\u2e3b\n])\n'
        r'(?=[a-z\u00e0-\u00f6\u00f8-\u00ff\u0101-\u024f\u1e00-\u1eff])')
# 长行没收句、下一行是中日韩等不用空格分词的文字：直接接上
WRAP = (r'(?m)^([^\n]{20,}'
        r'[^.!?:;\u3002\uff01\uff1f\uff1a\uff1b\u17d4\u2e3b\n])\n'
        r'(?=[\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff'
        r'\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3])')

CLEAN = [
    ('去噪文本', NOISE, '', True),
    ('二次去噪', NOISE, '', True),
    ('去重文本', DEDUP, '', True),
    ('整理文本', BLANKS, SENTINEL + '\n', False),
    ('合并断行', JOIN, '$1 ', True),
    ('合并段落', WRAP, '$1', True),
]

# --- 翻译门槛与响应解析 ---

LATIN = r'A-Za-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u024f\u1e00-\u1eff'
# 剔掉孤立的短拉丁词和标点数字，剩下的才算翻译内容
GIST = (r'(?<![{L}])[{L}]{{1,{n}}}(?![{L}])|[\W\d_]'
        .format(L=LATIN, n=MIN_LETTERS))

# 每行裹一份原文随行送回，<br> 把两份文本隔成两段
WRAP_LINE = '<span translate="no">$1</span><br>$1'

# 响应是 JSON 数组，每行原文对应一个元素：
#   ["<span translate=\"no\">原文</span><br>译文","语言"]
# 设备上多半已被解析成逐行文本，没解析的先经 UNESCAPE 反转义成同样的形态；
# 之后 PAIRING 整形成对照稿：原文行在上、译文行在下、块间空行

UNESCAPE = [
    # 每个元素独占一行，语言码等尾巴一并吃掉
    ('分列元素', r'\["((?:[^"\\]|\\.)*)"[^\]]*\]', '\n$1\n\n', True),
    # 只剩括号逗号的结构行
    ('剥壳', r'(?m)^[,\[\]]+[ \t]*(?:\n|$)', '', True),
    ('还原引号', r'\\"', '"', True),
    ('还原反斜杠', r'\\\\', '\\\\', True),
]
PAIR_MARK = '<span translate='  # 出现即接口已应答
ESCAPE_MARK = 'translate=\\"'  # 出现即响应还是未解析的原始 JSON

PAIRING = [
    # 独行的语言码（en、zh-CN）删成空行，兼作块间隔
    ('清语言码', r'(?m)^[A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?[ \t]*$\n?', '\n', True),
    # span 里是原文，行内其余部分是译文：拆成上下两行
    ('拆分对照', r'(?m)^(.*)<span translate="no">(.*?)</span>(?:<br>)? ?(.*)$',
     '$2\n$1$3', True),
    ('删隔断', r'<br ?/?>', '', False),
    ('修行边', r'(?m)^[ \t]+|[ \t]+$', '', True),
    # HTML 模式把标点转成了实体，和号最后还原
    ('还原小于号', r'&lt;', '<', False),
    ('还原大于号', r'&gt;', '>', False),
    ('还原直引号', r'&quot;', '"', False),
    ('还原撇号', r'&#39;', "'", False),
    ('还原和号', r'&amp;', '&', False),
    ('收空行', r'\n{3,}', '\n\n', True),
    # 哨兵行的译文没有意义
    ('缩哨兵', r'(?m)^(\u2e3b)\n[^\n]+$', '$1', True),
    # 译文里没有目标语言的字，说明这行没译过去：只留原文
    ('留原文', rf'(?m)^([^\n]+)\n(?![^\n]*[{TARGET_CHARS}])[^\n]+$', '$1', True),
    # 译文与原文一字不差，不用摆两遍
    ('并同文', r'(?m)^([^\n]+)\n\1$', '$1', True),
    ('修边', r'\A\s+|\s+\z', '', True),
]

# 对照模式下整块删掉哨兵
DROP_SENTINEL = r'(?m)^\u2e3b[ \t]*(?:\n\n?|$)'
# 只看译文时删去每块首行的原文，单行块不删
DROP_ORIG = r'(?m)^[^\n]*\n(?=[^\n])'
BLANK_LINES = r'(?m)^[ \t]*\n'


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


def show(value, title, output):
    """交付一份文本：复制到剪贴板，再以 title 为名弹出预览"""
    doc = uid()
    return [
        action('setclipboard', {'WFInput': attach(value)}),
        action('setitemname', {
            'WFInput': attach(value), 'WFName': tokens(title),
            'CustomOutputName': output, 'UUID': doc}),
        action('previewdocument', {'WFInput': attach(ref(doc, output))}),
    ]


def ascii_regex(find):
    # 正则里的非 ASCII 字符统一转成 \uXXXX 转义，BMP 之外的拆成代理对
    def esc(c):
        if c.isascii():
            return c
        if ord(c) > 0xffff:
            hi, lo = divmod(ord(c) - 0x10000, 0x400)
            return '\\u%04x\\u%04x' % (0xd800 + hi, 0xdc00 + lo)
        return '\\u%04x' % ord(c)
    return ''.join(esc(c) for c in find)


def replace(text, find, repl, name, case_sensitive=True):
    step = uid()
    return action('text.replace', {
        'WFInput': tokens(text),
        'WFReplaceTextFind': ascii_regex(find),
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


# 缺省外观是蓝底四芒星、缺省输入是图像，三项都可覆盖。
# 颜色是 RGBA 打包的整数，图标编号见 electrikmilk/shortcuts-glyph-search
def workflow(actions, icon_color=946986751, icon_glyph=62352,
             input_classes=('WFImageContentItem',)):
    return {
        'WFWorkflowMinimumClientVersionString': '900',
        'WFWorkflowMinimumClientVersion': 900,
        'WFWorkflowIcon': {'WFWorkflowIconStartColor': icon_color,
                           'WFWorkflowIconGlyphNumber': icon_glyph},
        'WFWorkflowClientVersion': '4046.0.2.1.102',
        'WFWorkflowOutputContentItemClasses': [],
        'WFWorkflowHasOutputFallback': False,
        'WFWorkflowActions': actions,
        'WFWorkflowInputContentItemClasses': list(input_classes),
        'WFWorkflowTypes': ['ActionExtension', 'WFWorkflowTypeShowInSearch'],
        'WFWorkflowImportQuestions': [],
        'WFQuickActionSurfaces': [],
        'WFWorkflowHasShortcutInputVariables': True,
    }


# --- 流程 ---

def source():
    src = '源图像'
    shot, height, crop, ocr, branch = (uid() for _ in range(5))
    image, trim = ref(shot, '截屏'), []
    if TOP_INSET or BOTTOM_INSET:
        trim = [
            action('math', {
                'WFInput': attach(ref(shot, '截屏', prop('Height'))),
                'WFMathOperation': '-',
                'WFMathOperand': str(TOP_INSET + BOTTOM_INSET),
                'CustomOutputName': '内容高度', 'UUID': height}),
            action('image.crop', {
                'WFInput': attach(ref(shot, '截屏')),
                'WFImageCropPosition': 'Custom',
                'WFImageCropX': '0', 'WFImageCropY': str(TOP_INSET),
                'WFImageCropWidth': attach(ref(shot, '截屏', prop('Width'))),
                'WFImageCropHeight': attach(ref(height, '内容高度')),
                'CustomOutputName': '内容图像', 'UUID': crop}),
        ]
        image = ref(crop, '内容图像')
    return [
        when(SHARE_INPUT, branch),
        setvar(SHARE_INPUT, src),
        otherwise(branch),
        action('takescreenshot', {'UUID': shot}),
        *trim,
        setvar(image, src),
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


BASE = ('https://translate.googleapis.com/translate_a/t'
        '?client=gtx&format=html&sl=auto&tl=' + TARGET)


def google(text):
    enc, req, join = (uid() for _ in range(3))
    trim_act, trimmed = replace(text, r'\A\s+|\s+\z', '', '修边原文')
    amp_act, escaped = replace(trimmed, r'&', '&amp;', '转义和号')
    lt_act, escaped = replace(escaped, r'<', '&lt;', '转义小于号')
    gt_act, escaped = replace(escaped, r'>', '&gt;', '转义大于号')
    wrap_act, wrapped = replace(
        escaped, r'(?m)^([^\n]+)$', WRAP_LINE, '包装原文')
    q_act, q = replace(ref(enc, '编码文本'), r'%0A', '&q=', '请求参数', False)
    return [
        trim_act, amp_act, lt_act, gt_act, wrap_act,
        action('urlencode', {'WFInput': tokens(
            wrapped), 'WFEncodeMode': 'Encode', 'CustomOutputName': '编码文本', 'UUID': enc}),
        q_act,
        action('downloadurl', {
            'WFURL': tokens(BASE + '&q=', q),
            'CustomOutputName': '接口响应', 'UUID': req}),
        action('text.combine', {'text': attach(ref(req, '接口响应')),
                                'WFTextSeparator': 'New Lines',
                                'CustomOutputName': '整段响应', 'UUID': join}),
    ], ref(join, '整段响应')


def deliver(text, switch):
    count, chars, enough, translated, raw_json, mode, readable = (
        uid() for _ in range(7))
    google_acts, response = google(text)
    # 翻译内容门槛：一个字母都不剩就不必翻
    letters_act, letters = replace(text, GIST, '', '字母序列', False)
    lines = '逐行响应'
    unescape_acts, undoc = [], response
    for name, find, repl, case_sensitive in UNESCAPE:
        act, undoc = replace(undoc, find, repl, name, case_sensitive)
        unescape_acts.append(act)
    pair_acts, doc = [], variable(lines)
    for name, find, repl, case_sensitive in PAIRING:
        act, doc = replace(doc, find, repl, name, case_sensitive)
        pair_acts.append(act)
    # 对照稿与纯译文稿都从同一份对照结构派生
    strip_act, paired = replace(doc, DROP_SENTINEL, '', '对照稿')
    orig_act, trans_only = replace(doc, DROP_ORIG, '', '纯译文')
    blank_act, packed = replace(trans_only, BLANK_LINES, '', '紧排译文')
    restore_act, restored = replace(packed, UNSENTINEL, '', '译文', False)
    # 文首文末剩下的空行是多余的
    edge_act, trimmed = replace(restored, r'\A\s+|\s+\z', '', '修边译文')
    return [
        letters_act,
        action('count', {'Input': attach(letters), 'WFCountType': 'Characters',
                         'CustomOutputName': '字母数', 'UUID': count}),
        when(ref(count, '字母数'), enough, 2, WFNumberValue=0),
        *google_acts,
        when(response, translated, 'Contains',
             WFConditionalActionString=PAIR_MARK),
        setvar(response, lines),
        when(response, raw_json, 'Contains',
             WFConditionalActionString=ESCAPE_MARK),
        *unescape_acts,
        setvar(undoc, lines),
        end(raw_json),
        *pair_acts,
        when(switch, mode, 4, WFNumberValue=1),
        strip_act,
        *show(paired, '对照结果', '对照展示稿'),
        otherwise(mode),
        orig_act, blank_act, restore_act, edge_act,
        *show(trimmed, TITLE, '展示稿'),
        end(mode),
        # 接口没应答时交付原文
        otherwise(translated),
        *show(text, ORIGINAL, '原文稿'),
        end(translated),
        # 没有够格送译的内容：识别到字就交付原文，一个字都没有才提示
        otherwise(enough),
        action('count', {'Input': attach(text), 'WFCountType': 'Characters',
                         'CustomOutputName': '原文字数', 'UUID': chars}),
        when(ref(chars, '原文字数'), readable, 2, WFNumberValue=0),
        *show(text, ORIGINAL, '原文备份稿'),
        otherwise(readable),
        action('notification', {'WFNotificationActionBody': '没有识别到文字',
                                'WFNotificationActionSound': False}),
        end(readable),
        end(enough),
    ]


def toggle():
    """对照开关，在快捷指令编辑器里改这个数字切换模式"""
    num = uid()
    return [
        action('comment', {'WFCommentActionText': '对照开关：1 逐行对照，0 只显示译文'}),
        action('number', {'WFNumberActionNumber': BILINGUAL,
                          'CustomOutputName': '对照开关', 'UUID': num}),
        setvar(ref(num, '对照开关'), '对照开关'),
    ], variable('对照开关')


def build():
    switch_acts, switch = toggle()
    head, ocr_text = source()
    body, clean_text = cleanup(ocr_text)
    return workflow(switch_acts + head + body + deliver(clean_text, switch))


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
