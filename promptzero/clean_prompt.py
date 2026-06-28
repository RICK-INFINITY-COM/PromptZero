#!/usr/bin/env python3
"""
Prompt Cleaner — 零 Token 提示词瘦身器
纯规则引擎，剥离人类自然语言中的语气词、填充词、冗余内容。
无 LLM 调用，零 token 消耗。

用法:
    echo "你的提示词" | python clean_prompt.py
    python clean_prompt.py "你的提示词"
    python clean_prompt.py -i input.txt -o output.txt
"""

import re
import sys
import os
from typing import List, Tuple

# ─── 配置 ───────────────────────────────────────────
LEVEL = os.environ.get("PROMPT_CLEANER_LEVEL", "moderate")  # safe | moderate | aggressive


# ─── 中文规则 ────────────────────────────────────────

# 句尾语气词（出现在句尾标点前或句尾）
CN_SENTENCE_END_PARTICLES = r'[啊吧呢嘛呗啦呀哇哈哦噢呃嗯]'

# 句首/独立语气词
CN_STANDALONE_PARTICLES = [
    r'\b呃[，,。.!！?？\s]*',
    r'\b嗯[，,。.!！?？\s]*',
    r'\b哦[，,。.!！?？\s]*',
    r'\b噢[，,。.!！?？\s]*',
    r'\b额[，,。.!！?？\s]*',
    r'\b哎[，,。.!！?？\s]*',
    r'\b嗨[，,。.!！?？\s]*',
]

# 填充短语（无信息量的口头禅）
CN_FILLER_PHRASES = [
    # 口头禅
    r'就是说[，,。.!！?？\s]*',
    r'就是说呢[，,。.!！?？\s]*',
    r'怎么说呢[，,。.!！?？\s]*',
    r'怎么说[，,。.!！?？\s]*',
    r'反正[，,。.!！?？\s]*',
    r'讲真的[，,。.!！?？\s]*',
    r'说白了[，,。.!！?？\s]*',
    r'我想想[，,。.!！?？\s]*',
    r'然后呢[，,。.!！?？\s]*',
    r'你知道吗[，,。.!！?？\s]*',
    r'我就是想说[，,。.!！?？\s]*',
    r'我想说的是[，,。.!！?？\s]*',
    r'我的意思是[，,。.!！?？\s]*',
    # 疑问式铺垫
    r'我想问一下[，,。.!！?？\s]*',
    r'想问一下[，,。.!！?？\s]*',
    r'想问下[，,。.!！?？\s]*',
    r'想请问一下[，,。.!！?？\s]*',
    r'想请问[，,。.!！?？\s]*',
    # 冗余确认
    r'对吧[，,。.!！?？\s]*',
    r'好不好[，,。.!！?？\s]*',
    r'行不行[，,。.!！?？\s]*',
    r'可以吗[，,。.!！?？\s]*',
    r'可以吧[，,。.!！?？\s]*',
    # "那个"的各种变体（填充用法：后跟标点或重复，不跟名词/动词）
    r'那个[，,。.!！?？\s]*那个[，,。.!！?？\s]*',  # 那个那个 (重复=填充)
    r'[，,]\s*那个[，,。.!！?？]+',     # 逗号后的"那个" (后跟标点=填充)
    r'^那个[，,。.!！?？\s]+',          # 句首的"那个" (后跟标点=填充)
    # "这个"填充用法（仅当后跟标点，不跟名词/动词）
    r'[，,]\s*这个[，,。.!！?？]+',     # 逗号后的"这个" (后跟标点=填充)
    # 冗余尾声
    r'这样子[。.!！?？\s]*$',
    r'这样[。.!！?？\s]*$',
    r'好吗[。.!！?？\s]*$',
    r'好不[。.!！?？\s]*$',
    r'可以不[。.!！?？\s]*$',
    r'可以吗[。.!！?？\s]*$',
]

# 冗余礼貌用语 → 简短形式
CN_POLITENESS_MAP = [
    # 祈使句缩短
    (r'请问你能不能帮我', '帮我'),
    (r'请问你能帮我', '帮我'),
    (r'请问你可不可以帮我', '帮我'),
    (r'请问你可以帮我', '帮我'),
    (r'能不能麻烦你帮我', '帮我'),
    (r'能不能帮我', '帮我'),
    (r'可以帮我', '帮我'),
    (r'麻烦你帮我', '帮我'),
    (r'麻烦你', ''),
    (r'劳驾', ''),
    (r'拜托', ''),
    (r'能不能[请你]*', ''),
    (r'可不可以[请你]*', ''),
    # 感谢语（prompt 末尾的感谢对 AI 无意义）
    (r'谢谢[你了啊呀哈啦]*[！!。.]*', ''),
    (r'多谢[了呀哈啦]*[！!。.]*', ''),
    (r'非常感谢[你了啊呀哈啦]*[！!。.]*', ''),
    (r'很感谢[你了啊呀哈啦]*[！!。.]*', ''),
    (r'感谢[你了啊呀哈啦]*[！!。.]*', ''),
    (r'感激不尽[！!。.]*', ''),
    (r'感恩[！!。.]*', ''),
    (r'三克油[！!。.]*', ''),
    # 冗余的"非常"在句尾
    (r'[，,]?\s*非常\s*$', ''),
]

# 重复修饰归一化
CN_REDUNDANT_MODIFIERS = [
    (r'非常非常', '很'),
    (r'特别特别', '很'),
    (r'十分十分', '很'),
    (r'超级超级', '很'),
    (r'真的真的', '真的'),
    (r'确实确实', '确实'),
]


# ─── 英文规则 ────────────────────────────────────────

# 填充词（Filler words）
EN_FILLER_WORDS = [
    r'\bum[，,.\s]*',
    r'\buh[，,.\s]*',
    r'\ber[，,.\s]*',
    r'\bah[，,.\s]*',
    r'\bhm+[，,.\s]*',      # hmm, hmmm
    r'\buh[-\s]?huh?\b[，,.\s]*',  # uh-huh
    r'\bmm[-\s]?hmm?\b[，,.\s]*',  # mm-hmm
    r'\byou know[，,.\s]*',  # common filler
    r'\bi mean[，,.\s]*',    # common filler
    # NOTE: "like" is NOT included because it's too often meaningful
    # ("I'd like to", "looks like", "something like that")
]

EN_WEAKENER_PHRASES = [
    r'\bsort of[，,.\s]*',
    r'\bkind of[，,.\s]*',
    r'\ba bit of[，,.\s]*',
    r'\bbasically[，,.\s]*',
    r'\bactually[，,.\s]*',
    r'\bliterally[，,.\s]*',
    r'\bhonestly[，,.\s]*',
    r'\bfrankly[，,.\s]*',
    r'\bto be honest[，,.\s]*',
    r'\bto be fair[，,.\s]*',
    r'\bi feel like[，,\s]*',
    r'\bi think that[，,\s]*',
    r'\bi believe that[，,\s]*',
    r'\bin my opinion[，,.\s]*',
    r'\bif you will[，,.\s]*',
    r'\bas it were[，,.\s]*',
    r'\bso to speak[，,.\s]*',
]

EN_POLITENESS_MAP = [
    # would you / could you
    (r'\bcould you please\b', 'please'),
    (r'\bwould you mind\b', 'please'),
    (r'\bwould you be able to\b', 'please'),
    (r'\bwould you kindly\b', 'please'),
    (r'\bcould you kindly\b', 'please'),
    # I was wondering
    (r"\bi was just wondering if you could\b", "please"),
    (r"\bi was wondering if you could\b", "please"),
    (r"\bi was wondering whether you could\b", "please"),
    (r"\bi was just wondering if\b", ""),
    (r"\bi was wondering if\b", ""),
    (r"\bi was wondering whether\b", ""),
    # if you don't mind
    (r"\bif you don't mind\b", ""),
    (r"\bif that's okay\b", ""),
    (r"\bif that's alright\b", ""),
    (r"\bwhen you get a chance\b", ""),
    (r"\bwhen you have a moment\b", ""),
    (r"\bwhen you have a chance\b", ""),
    # 冗余礼貌副词
    (r'\bkindly\b', ''),
    # 感谢语（英文）
    (r'\bthank you so much[!.,\s]*', ''),
    (r'\bthank you very much[!.,\s]*', ''),
    (r'\bthanks so much[!.,\s]*', ''),
    (r'\bthanks a lot[!.,\s]*', ''),
    (r'\bthanks a bunch[!.,\s]*', ''),
    (r'\bmany thanks[!.,\s]*', ''),
    (r'\bthanks in advance[!.,\s]*', ''),
    (r'\bi really appreciate it[!.,\s]*', ''),
    (r'\bi appreciate it[!.,\s]*', ''),
    (r'\bthank you[!.,\s]*', ''),
    (r'\bthanks[!.,\s]*', ''),
]

EN_REDUNDANT_MODIFIERS = [
    (r'\bvery very\b', 'very'),
    (r'\breally really\b', 'really'),
    (r'\bextremely extremely\b', 'very'),
    (r'\babsolutely\s+absolutely\b', 'absolutely'),
]


# ─── 通用规则 ────────────────────────────────────────

# 重复标点归一化
REPEATED_PUNCTUATION = [
    (r'！{2,}', '！'),
    (r'!{2,}', '!'),
    (r'？{2,}', '？'),
    (r'\?{2,}', '?'),
    (r'。{2,}', '。'),
    (r'\.{3,}', '…'),       # 三个以上句号 → 省略号
    (r'，{2,}', '，'),
    (r',{2,}', ','),
    (r'；{2,}', '；'),
    (r';{2,}', ';'),
    (r'～{2,}', '～'),
    (r'~{2,}', '~'),
]

# 多余空格
EXTRA_SPACES = [
    (r'[ \t]+', ' '),        # 多个空格/tab → 单个空格
    (r'[ \t]+$', ''),        # 行尾空格
    (r'^[ \t]+', ''),        # 行首空格
    (r'([。，！？；：、]) ', r'\1'),  # 中文标点后不要空格
    (r' ([。，！？；：、])', r'\1'),  # 中文标点前不要空格
]


# ─── 代码块保护 ─────────────────────────────────────

def _split_code_blocks(text: str) -> List[Tuple[bool, str]]:
    """
    将文本分割为 (is_code, content) 的列表。
    代码块（```...```）标记为 is_code=True，不会被修改。
    """
    parts = []
    pattern = re.compile(r'(```[^`]*```)', re.DOTALL)
    last_end = 0
    for match in pattern.finditer(text):
        if match.start() > last_end:
            parts.append((False, text[last_end:match.start()]))
        parts.append((True, match.group(1)))
        last_end = match.end()
    if last_end < len(text):
        parts.append((False, text[last_end:]))
    return parts


# ─── 核心清理函数 ────────────────────────────────────

def _clean_chinese(text: str) -> str:
    """清理中文部分"""

    # 1. 填充短语
    for pattern in CN_FILLER_PHRASES:
        text = re.sub(pattern, '', text)

    # 2. 独立语气词 — 合并为单个正则，循环应用直到无变化
    _standalone_re = re.compile(
        r'(?:^|(?<=[。！？\n\s，,]))(?:呃|嗯|哦|噢|额|哎|嗨)[，,。.!！?？\s]*'
    )
    prev = None
    while prev != text:
        prev = text
        text = _standalone_re.sub('', text)
    # 也处理行首（re.MULTILINE）
    _standalone_re_ml = re.compile(
        r'^(?:呃|嗯|哦|噢|额|哎|嗨)[，,。.!！?？\s]*', re.MULTILINE
    )
    prev = None
    while prev != text:
        prev = text
        text = _standalone_re_ml.sub('', text)

    # 3. 句尾语气词（在标点前）
    text = re.sub(
        rf'{CN_SENTENCE_END_PARTICLES}(?=[。，！？；：、\s]*$)',
        '', text
    )
    text = re.sub(
        rf'{CN_SENTENCE_END_PARTICLES}(?=[。！？])',
        '', text
    )

    # 3b. 重复语气词（嗯嗯 → 空，呃呃 → 空）
    text = re.sub(r'[嗯呃哎]{2,}[，,。.!！?？\s]*', '', text)

    # 4. 冗余礼貌用语 (moderate+)
    if LEVEL in ('moderate', 'aggressive'):
        for pattern, replacement in CN_POLITENESS_MAP:
            text = re.sub(pattern, replacement, text)

    # 5. 重复修饰归一化
    for pattern, replacement in CN_REDUNDANT_MODIFIERS:
        text = re.sub(pattern, replacement, text)

    return text


def _clean_english(text: str) -> str:
    """清理英文部分"""

    # 1. 填充词
    for pattern in EN_FILLER_WORDS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)

    # 2. 弱化短语
    if LEVEL in ('moderate', 'aggressive'):
        for pattern in EN_WEAKENER_PHRASES:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

    # 3. 礼貌冗余 (moderate+)
    if LEVEL in ('moderate', 'aggressive'):
        for pattern, replacement in EN_POLITENESS_MAP:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # 4. 重复修饰
    for pattern, replacement in EN_REDUNDANT_MODIFIERS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text


def _clean_common(text: str) -> str:
    """通用清理"""

    # 1. 重复标点
    for pattern, replacement in REPEATED_PUNCTUATION:
        text = re.sub(pattern, replacement, text)

    # 2. 多余空格
    for pattern, replacement in EXTRA_SPACES:
        text = re.sub(pattern, replacement, text)

    # 3. 多余空行
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 4. aggressive: 删除所有 emoji
    if LEVEL == 'aggressive':
        # 注意：\U000024C2 是独立字符，不能用 \U000024C2-\U0001F251 这种大范围
        # 因为 U+24C2 到 U+1F251 会误覆盖中文字符 (U+4E00-U+9FFF)
        text = re.sub(
            r'[\U0001F300-\U0001F9FF'   # Misc symbols, pictographs, emoticons, supplements
            r'\U0001FA00-\U0001FA6F'    # Chess symbols
            r'\U0001FA70-\U0001FAFF'    # Symbols extended-A
            r'\U00002702-\U000027B0'    # Dingbats
            r'\U0001F100-\U0001F1FF'    # Enclosed alphanumeric supplement
            r'\U0001F200-\U0001F2FF'    # Enclosed ideographic supplement
            r'\U0001F250-\U0001F251'    # 🉐 🉑
            r'\U000024C2'               # Ⓜ
            r'\U0001F600-\U0001F64F'    # Emoticons (explicit)
            r'\U0001F900-\U0001F9FF'    # Supplemental symbols (explicit)
            r'\U000000A9'               # ©
            r'\U000000AE'               # ®
            r'\U0000200D'               # ZWJ
            r'\U0000FE0F'               # Variation selector-16
            r'\U000020E3'               # Combining enclosing keycap
            r']+',
            '', text
        )

    return text


def clean(text: str, level: str = None) -> str:
    """
    清理文本中的语气词、填充词、冗余内容。

    Args:
        text: 原始文本
        level: 激进程度 ('safe', 'moderate', 'aggressive')，默认使用环境变量

    Returns:
        清理后的文本
    """
    global LEVEL
    if level:
        LEVEL = level

    parts = _split_code_blocks(text)

    result_parts = []
    for is_code, content in parts:
        if is_code:
            result_parts.append(content)
        else:
            cleaned = content
            cleaned = _clean_chinese(cleaned)
            cleaned = _clean_english(cleaned)
            cleaned = _clean_common(cleaned)
            result_parts.append(cleaned)

    result = ''.join(result_parts)

    # 去掉首尾多余空格
    result = result.strip()

    # 如果清除后变成纯标点或空白，返回空字符串
    if not re.sub(r'[\s。，！？；：、.!?,;:\s]', '', result):
        return result

    return result


# ─── 统计函数 ─────────────────────────────────────────

def stats(original: str, cleaned: str) -> dict:
    """估算 token 节省"""
    # 简单估算：中文 1 字符 ≈ 0.5 token，英文 1 词 ≈ 1.3 token
    orig_chars = len(original)
    clean_chars = len(cleaned)
    chars_saved = orig_chars - clean_chars
    pct = (chars_saved / orig_chars * 100) if orig_chars > 0 else 0

    # 粗略 token 估算
    orig_tokens_est = _estimate_tokens(original)
    clean_tokens_est = _estimate_tokens(cleaned)

    return {
        'original_chars': orig_chars,
        'cleaned_chars': clean_chars,
        'chars_saved': chars_saved,
        'char_reduction_pct': round(pct, 1),
        'original_tokens_est': orig_tokens_est,
        'cleaned_tokens_est': clean_tokens_est,
        'tokens_saved_est': orig_tokens_est - clean_tokens_est,
    }


def _estimate_tokens(text: str) -> int:
    """粗略 token 估算"""
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    others = len(text) - chinese_chars - sum(len(w) for w in re.findall(r'[a-zA-Z]+', text))
    return int(chinese_chars * 0.6 + english_words * 1.3 + others * 0.3)


# ─── CLI ──────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Prompt Cleaner — 零 Token 提示词瘦身器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  echo "嗯，请问你能帮我写个脚本吗？" | python clean_prompt.py
  python clean_prompt.py "你好，那个，帮我写个脚本"
  python clean_prompt.py -i input.txt -o output.txt --stats
  PROMPT_CLEANER_LEVEL=aggressive python clean_prompt.py -i in.txt
        '''
    )
    parser.add_argument('text', nargs='?', help='要清理的文本（不提供则从 stdin 读取）')
    parser.add_argument('-i', '--input', help='输入文件路径')
    parser.add_argument('-o', '--output', help='输出文件路径（默认 stdout）')
    parser.add_argument('-l', '--level', choices=['safe', 'moderate', 'aggressive'],
                        default=LEVEL, help='激进程度 (默认: %(default)s)')
    parser.add_argument('-s', '--stats', action='store_true', help='显示节省统计')
    parser.add_argument('-q', '--quiet', action='store_true', help='只输出清理后文本，不显示统计')

    args = parser.parse_args()

    # 读取输入
    if args.input:
        with open(args.input, 'r', encoding='utf-8') as f:
            original = f.read()
    elif args.text:
        original = args.text
    else:
        original = sys.stdin.read()

    if not original.strip():
        sys.exit(0)

    # 清理
    cleaned = clean(original, level=args.level)

    # 统计
    s = stats(original, cleaned)

    # 输出
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(cleaned)
        if not args.quiet:
            print(f"✅ 已保存到 {args.output}", file=sys.stderr)
    else:
        if args.stats and not args.quiet:
            print(f"[原始] {s['original_chars']} 字符 / ~{s['original_tokens_est']} tokens", file=sys.stderr)
            print(f"[清理] {s['cleaned_chars']} 字符 / ~{s['cleaned_tokens_est']} tokens", file=sys.stderr)
            print(f"[节省] {s['chars_saved']} 字符 ({s['char_reduction_pct']}%) / ~{s['tokens_saved_est']} tokens", file=sys.stderr)
            print("-" * 40, file=sys.stderr)
        sys.stdout.write(cleaned)
        if not cleaned.endswith('\n'):
            sys.stdout.write('\n')


if __name__ == '__main__':
    main()
