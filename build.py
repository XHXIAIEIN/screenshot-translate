import plistlib
import sys
import uuid

MARK = '￼'  # 对象替换字符，标记文本模板里附件的插入点
SENTINEL = '⸻'  # 空行会让接口产生空 q：段落间隔先换成哨兵行，译完再还原
TARGET = 'zh-CN'
MIN_LETTERS = 2  # 词长不超过该值的拉丁词不算翻译内容：人名、代号常见此形
TITLE = '翻译结果'
BILINGUAL = 1  # 烙进快捷指令的对照开关缺省值：1 逐行对照，0 只显示译文
BOTTOM_INSET = 120  # 底部横条裁掉的像素，按 3 倍图计
SHARE_INPUT = {'Type': 'ExtensionInput'}

# --- 清理规则 ---
# 正则在快捷指令的替换动作里执行；replace() 落盘时把非 ASCII 字符
# 转成 \uXXXX 转义（verify 兜底强制），源码里直接写字符即可

NOISE = '(?m)' + '|'.join([
    # 行尾的箭头、勾叉、图标类符号，或连串的点
    r'[ \t]*(?:>=|=>|==|[>›»→≡⋮⋯☰★☆'
    r'✓✕✗×■□▪▸▾⚙]+'
    r'|[.·•…⋯‧∙]{2,})[ \t]*$',
    # 整行只有分隔线
    r'^[ \t]*(?:[-=._~*·•…][ \t]*){2,}$',
    # 整行只有箭头
    r'^[ \t]*(?:[>‹›»→][ \t]*){1,12}$',
    # 整行只有一个非汉字字符
    r'^[ \t]*[^一-鿿\s][ \t]*$\n?',
    # 整行只有一至三个符号
    r'^[ \t]*[^\w\s]{1,3}[ \t]*$\n?',
    # 整行是时间、日期、电量这类数字串
    r'^[ \t]*[\d :.,\-/%°+\t]+(?:[AaPp]\.?[Mm]\.?)?[ \t]*$\n?',
    # 整行是数字加计量单位
    r'^[ \t]*\d+(?:[.,]\d+)?[ \t]*'
    r'(?:[Cc]m|[Mm]m|[Kk]m|[Kk]g|[Ll]bs?|[Ff]t|[Ii]n|[Mm]i|[MmGg])[ \t]*$\n?',
    # 有汉字、无假名和谚文的行：已经是中文，不进翻译
    r'^[ \t]*(?![^\n]*[぀-ヿㇰ-ㇿ가-힣ｦ-ﾝ])'
    r'(?=[^\n]*[㐀-鿿])[^\n]*$\n?',
    # 行首一两个字符的孤立碎片；放过单字母词（大小写都算：U up? 也是句子）、
    # 数字、货币符号（OCR 常把 $50 拆成 $ 50）、带变音符的字母，
    # 以及谚文假名这类单字成词的文字（只清 ASCII 碎片和符号）
    r'^[ \t]*(?![AEIOUYaeiouy\d$¥€£₩À-ÖØ-öø-ÿẠ-ỹ][ \t])'
    r'(?=[\x00-\x7f]|[^\w])'
    r'(\S)\1?[ \t]+(?=\S)',
])
# 一行在后文原样重现时，删掉靠前的那次
DEDUP = r'(?m)^([ \t]*[^ \t\n][^\n]*)\n(?=(?:[^\n]*\n)*\1(?:\n|$))'
# 连续空行
BLANKS = r'(?m)(?:^[ \t]*\n)+'
# 译文里的哨兵行；哨兵可能被翻译改写成别的符号
UNSENTINEL = r'(?m)^[ \t]*(?:⸻|[^\w\s]{1,3})[ \t]*(?=\n|$)'
# 行尾没收句、下一行以小写字母开头：把硬换行并回空格
JOIN = (r'(?m)([^.!?:;。！？：；។⸻\n])\n'
        r'(?=[a-zà-öø-ÿā-ɏḀ-ỿ])')
# 长行没收句、下一行是中日韩等不用空格分词的文字：直接接上
WRAP = (r'(?m)^([^\n]{20,}[^.!?:;。！？：；។⸻\n])\n'
        r'(?=[฀-໿က-႟ក-៿'
        r'぀-ヿ㐀-鿿가-힣])')

CLEAN = [
    ('去噪文本', NOISE, '', True),
    # 行首图标碎片剥掉后才露出整行规则的目标（「| 160 cm」→「160 cm」）：
    # 同一动作里各规则不回看彼此的产物，残行要再过一遍
    ('二次去噪', NOISE, '', True),
    ('去重文本', DEDUP, '', True),
    ('整理文本', BLANKS, SENTINEL + '\n', False),
    ('合并断行', JOIN, '$1 ', True),
    ('合并段落', WRAP, '$1', True),
]

# --- 翻译门槛与响应解析 ---

LATIN = r'A-Za-zÀ-ÖØ-öø-ɏḀ-ỿ'
# 孤立的短拉丁词串；剔掉它们再剔掉标点数字，剩下的才算翻译内容
SHORT_WORDS = (r'(?<![{L}])[{L}]{{1,{n}}}(?![{L}])'
               .format(L=LATIN, n=MIN_LETTERS))

# 每行裹一份原文随行送回；<br> 把两份文本隔成两段，
# 缺了它模型会把原文连读进译文，短句译文折损（ありがとう → 非常）
WRAP_LINE = '<span translate="no">$1</span><br>$1'

# 响应是 JSON 数组，每行原文对应一个元素：
#   ["<span translate=\"no\">原文</span><br>译文","语言"]
# 设备上响应多半已被解析成列表、拼回逐行文本：括号引号剥掉，语言码独占一行。
# 解析不生效时进来的才是原始 JSON，先经 UNESCAPE 反转义成同样的逐行文本；
# 解析过的文本不能再走这四步——原文里字面的 \" 和 ["…"] 会被误当转义吞掉。
# 之后 PAIRING 把逐行文本整形成对照稿：原文行在上、译文行在下、块间空行。
# 译文缺失的块缩成单行原文——翻译丢了也不丢内容

UNESCAPE = [
    # 每个元素独占一行；语言码等尾巴一并吃掉，防备接口添字段
    ('分列元素', r'\["((?:[^"\\]|\\.)*)"[^\]]*\]', '\n$1\n\n', True),
    # 只剩括号逗号的结构行
    ('剥壳', r'(?m)^[,\[\]]+[ \t]*(?:\n|$)', '', True),
    ('还原引号', r'\\"', '"', True),
    # JSON 里一个反斜杠写作两个；ICU 替换模板里也是
    ('还原反斜杠', r'\\\\', '\\\\', True),
]
# 形态判据：span 属性上的转义引号只存在于未解析的原始 JSON 里
ESCAPE_MARK = 'translate=\\"'

PAIRING = [
    # 解析路径下独行的语言码（en、zh-CN）：删成空行，兼作块间隔。
    # 内容行都带 span 包装，不会整行只是两三个字母
    ('清语言码', r'(?m)^[A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?[ \t]*$\n?', '\n', True),
    # span 里是原样送回的原文，行内其余部分是译文：拆成上下两行。
    # span 有时会被挪到译文后面，位置不作数
    ('拆分对照', r'(?m)^(.*)<span translate="no">(.*?)</span>(?:<br>)? ?(.*)$',
     '$2\n$1$3', True),
    ('删隔断', r'<br ?/?>', '', False),
    ('修行边', r'(?m)^[ \t]+|[ \t]+$', '', True),
    # HTML 模式会把标点转成实体；和号要留到最后还原，
    # 不然原文里字面的 &lt; 会被二次解码
    ('还原小于号', r'&lt;', '<', False),
    ('还原大于号', r'&gt;', '>', False),
    ('还原直引号', r'&quot;', '"', False),
    ('还原撇号', r'&#39;', "'", False),
    ('还原和号', r'&amp;', '&', False),
    ('收空行', r'\n{3,}', '\n\n', True),
    # 哨兵行的译文没有意义
    ('缩哨兵', r'(?m)^(⸻)\n[^\n]+$', '$1', True),
    # 原文没有拉丁字母、译文却是纯 ASCII：翻译退化成了罗马字，留原文
    ('删音译', r'(?m)^((?![^\n]*[A-Za-z])[^\n]*[^\x00-\x7f][^\n]*)'
     r'\n[\x20-\x7e]+$', '$1', True),
    # 译文与原文一字不差：接口原样送回，不用摆两遍
    ('并同文', r'(?m)^([^\n]+)\n\1$', '$1', True),
    ('修边', r'\A\s+|\s+\z', '', True),
]

# 对照模式下哨兵块整个删掉：块间空行已承担分段
DROP_SENTINEL = r'(?m)^⸻[ \t]*(?:\n\n?|$)'
# 只看译文时删去每块首行（原文行）；单行块是保下来的原文，不删
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


def ascii_regex(find):
    # 正则统一转成 \uXXXX 转义：非 ASCII 字符在部分设备的替换动作里水土不服。
    # ICU 按 UTF-16 计数，超出 BMP 的字符要拆成代理对
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
    shot, top, avail, height, crop, ocr, branch = (uid() for _ in range(7))
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
        # 可用高度是截屏减去顶栏的部分。底部横条的高度不随屏幕大小变，
        # 按比例裁会在长屏幕上吃掉正文，所以减的是固定像素
        action('math', {
            'WFInput': attach(ref(shot, '截屏', prop('Height'))),
            'WFMathOperation': '×', 'WFMathOperand': '87E-2',
            'CustomOutputName': '可用高度', 'UUID': avail}),
        action('math', {
            'WFInput': attach(ref(avail, '可用高度')),
            'WFMathOperation': '-', 'WFMathOperand': str(BOTTOM_INSET),
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


BASE = ('https://translate.googleapis.com/translate_a/t'
        '?client=gtx&format=html&sl=auto&tl=' + TARGET)


def google(text):
    """把清理后的文本送谷歌翻译，回传原始响应。不用系统翻译（本可不出设备）：
    不支持的语言不报错，退化成罗马字音译——有值不算失败，
    「空值才回退」在快捷指令里兜不住。
    每行独立作一个 q：语言检测逐行进行，混排截图里的少数语种不再被整体
    检测淹没；译文按元素与行一一对应，不再指望接口保留换行。
    行首再用 notranslate span 裹一份原文，接口把 span 内容原样送回——
    原文译文同乘一个元素回来，逐行对照不需要循环配对（「重复项目」在设备的
    文本模板里解析为空，循环配对每行要跑八个动作，是旧版最慢的一环）。
    文本编码后拼进 URL 走 GET。POST 的坑趟遍了：「表单」体实为 multipart，
    接口只认 urlencoded；「文件」体的自定义 Content-Type 头不生效——
    两种都拿到 400 错误页。URL 全长约 16K 字符封顶，特长文本同样得 400，
    响应里没有配对痕迹，落进「没译出来」分支"""
    enc, req, join = (uid() for _ in range(3))
    trim_act, trimmed = replace(text, r'\A\s+|\s+\z', '', '修边原文')
    # 原文里的 & < > 先转成实体：载荷里唯一的真标签必须是下面包上去的
    # span 和 <br>，字面的 </span> 混进去会让配对解析错乱。和号最先转
    amp_act, escaped = replace(trimmed, r'&', '&amp;', '转义和号')
    lt_act, escaped = replace(escaped, r'<', '&lt;', '转义小于号')
    gt_act, escaped = replace(escaped, r'>', '&gt;', '转义大于号')
    wrap_act, wrapped = replace(
        escaped, r'(?m)^([^\n]+)$', WRAP_LINE, '包装原文')
    q_act, q = replace(ref(enc, '编码文本'), r'%0A', '&q=', '请求参数', False)
    return [
        trim_act, amp_act, lt_act, gt_act, wrap_act,
        action('urlencode', {'WFInput': tokens(wrapped), 'WFEncodeMode': 'Encode',
                             'CustomOutputName': '编码文本', 'UUID': enc}),
        q_act,
        action('downloadurl', {
            'WFURL': tokens(BASE + '&q=', q),
            'CustomOutputName': '接口响应', 'UUID': req}),
        # 响应标着 application/json，「获取 URL 内容」把它解析成列表。
        # 列表会原样穿过只有孤身变量的文本模板，替换动作变成逐项映射，
        # 多个条目一路传到快速查看，弹成「选取项目」列表——
        # 先拼合回单个文本，替换链才有完整的文档可整形
        action('text.combine', {'text': attach(ref(req, '接口响应')),
                                'WFTextSeparator': 'New Lines',
                                'CustomOutputName': '整段响应', 'UUID': join}),
    ], ref(join, '整段响应')


def deliver(text, switch):
    count, match, pairs, pair_doc, plain_doc, enough, translated, raw_json, mode = (
        uid() for _ in range(9))
    google_acts, response = google(text)
    # 翻译内容门槛：剔掉孤立短拉丁词，再剔掉标点数字，一无所剩就不必翻
    short_act, gist = replace(text, SHORT_WORDS, '', '实词序列', False)
    letters_act, letters = replace(gist, r'[\W\d_]', '', '字母序列', False)
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
    return [
        short_act, letters_act,
        action('count', {'Input': attach(letters), 'WFCountType': 'Characters',
                         'CustomOutputName': '字母数', 'UUID': count}),
        when(ref(count, '字母数'), enough, 2, WFNumberValue=0),
        *google_acts,
        # 成败看响应里有没有 span 痕迹：错误页和空响应都不会有
        action('text.match', {
            'WFMatchTextPattern': '<span translate=',
            'text': tokens(response),
            'CustomOutputName': '配对痕迹', 'UUID': match}),
        action('count', {'Input': attach(ref(match, '配对痕迹')),
                         'WFCountType': 'Items',
                         'CustomOutputName': '配对数', 'UUID': pairs}),
        when(ref(pairs, '配对数'), translated, 2, WFNumberValue=0),
        setvar(response, lines),
        when(response, raw_json, 'Contains', WFConditionalActionString=ESCAPE_MARK),
        *unescape_acts,
        setvar(undoc, lines),
        end(raw_json),
        *pair_acts,
        when(switch, mode, 4, WFNumberValue=1),
        strip_act,
        action('setclipboard', {'WFInput': attach(paired)}),
        action('setitemname', {
            'WFInput': attach(paired), 'WFName': tokens('对照结果'),
            'CustomOutputName': '对照展示稿', 'UUID': pair_doc}),
        action('previewdocument', {'WFInput': attach(ref(pair_doc, '对照展示稿'))}),
        otherwise(mode),
        orig_act, blank_act, restore_act,
        action('setclipboard', {'WFInput': attach(restored)}),
        action('setitemname', {
            'WFInput': attach(restored), 'WFName': tokens(TITLE),
            'CustomOutputName': '展示稿', 'UUID': plain_doc}),
        action('previewdocument', {'WFInput': attach(ref(plain_doc, '展示稿'))}),
        end(mode),
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


def toggle():
    """对照开关放在最前面：在快捷指令编辑器里改这个数字即可切换模式"""
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
