#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
规则集：跨境电商 listing 合规
================================
**本规则集的存在意义不是业务价值，而是证明分层是真的。**
它是在引擎冻结之后写的 —— engine/ 与 engine 下的任何文件都没有因为
它的存在而修改过一个字节。若这成立，「加垂类 = 放个目录」就是事实。

规则来源：平台官方政策（见每条 source）。不引二手博客。
"""
import os
import re
import json
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
from engine.engine import Rule  # noqa: E402

POLICY = {
    'version': '2026-10-11.0',
    'display': '跨境电商 listing 合规',
    'red_lines': [
        '本规则集只做【可确定性判定】的检查；不做商品合规性的实质判断',
        '平台政策会变 —— 每次使用前请核对 source 链接是否为最新版本',
    ],
    'rules': {
        'AMZ-TITLE-LEN': {
            'group': 'Amazon 标题',
            'severity': 'BLOCK',
            'enforce_type': 'platform_technical',
            'desc': '标题字符数上限（美国站 75 / 欧洲站 200），超出影响搜索权重',
            'check': 'amz_title_len',
            'source': 'Amazon Seller Central 商品标题规范',
        },
        'AMZ-TITLE-REPEAT': {
            'group': 'Amazon 标题',
            'severity': 'WARN',
            'enforce_type': 'platform_technical',
            'desc': '同一单词在标题中重复出现超过 2 次（介词/冠词除外）会被降权',
            'check': 'amz_title_repeat',
            'params': {'max_repeat': 2},
            'source': 'Amazon Seller Central 标题撰写指南',
        },
        'AMZ-TITLE-BANNED': {
            'group': 'Amazon 标题',
            'severity': 'BLOCK',
            'enforce_type': 'platform_technical',
            'desc': '标题不得含促销词/保证性表述/特殊符号（!$?_{}^¬¦）',
            'check': 'amz_title_banned',
            'params': {
                'banned_words': ['free shipping', '100% quality guaranteed',
                                 'best seller', 'guaranteed', 'freebie'],
                'banned_chars': '!$?_{}^¬¦',
            },
            'source': 'Amazon Seller Central 标题撰写指南',
        },
        'AMZ-BULLET-CHARS': {
            'group': 'Amazon 五点',
            'severity': 'BLOCK',
            'enforce_type': 'platform_technical',
            'desc': '五点描述不得含 emoji 与特定符号集（™®€…†‡o¢£¥©±~）',
            'check': 'amz_bullet_chars',
            # v0.1.1：删掉串在表里的字母 `o`（原写作 '™®€…†‡o¢£¥©±~'）。
            # 它让任何含字母 o 的英文五点都被判违规 —— 该规则等于失效。
            'params': {'banned_chars': '™®€…†‡¢£¥©±~'},
            'source': 'Amazon 五点描述规范',
        },
        'AMZ-BULLET-EMOTION': {
            'group': 'Amazon 五点',
            'severity': 'BLOCK',
            'enforce_type': 'platform_technical',
            'desc': '五点不得含 emoji、保证信息（"全额退款"）、公司名/网址/链接、引导好评',
            'check': 'amz_bullet_emotion',
            'params': {
                'banned_patterns': [
                    r'全[额额]?退款', r'guarantee', r'点击.{0,4}链接', r'https?://',
                    r'www\.', r'好评', r'五[星颗]好评', r'\bASIN\b', r'N/A',
                ],
                'emoji_re': '[\U0001F300-\U0001FAFF☀-➿️]',
            },
            'source': 'Amazon 五点描述规范',
        },
        'AMZ-BULLET-LEN': {
            'group': 'Amazon 五点',
            'severity': 'WARN',
            'enforce_type': 'platform_technical',
            'desc': '每条五点长度须在 10–255 字符区间',
            'check': 'amz_bullet_len',
            'params': {'min': 10, 'max': 255},
            'source': 'Amazon 五点描述规范',
        },
        'AMZ-BULLET-TOTAL': {
            'group': 'Amazon 五点',
            'severity': 'BLOCK',
            'enforce_type': 'platform_technical',
            'desc': '五点合计不超过 1000 字节，否则不进搜索索引（此为最易被忽略的硬阈值）',
            'check': 'amz_bullet_total',
            'params': {'max_bytes': 1000},
            'source': 'Amazon 搜索索引字节限制',
        },
        'AMZ-BULLET-PREFIX': {
            'group': 'Amazon 五点',
            'severity': 'WARN',
            'enforce_type': 'platform_technical',
            'desc': '每条五点建议以「标题: 」前缀开头（卖点前置，便于扫读）',
            'check': 'amz_bullet_prefix',
            'source': 'Amazon 五点描述写法建议',
        },
        'ADS-MISREPRESENTATION': {
            'group': '广告合规',
            'severity': 'BLOCK',
            'enforce_type': 'legal_mandatory',
            'desc': '不得含隐藏收费条款、误导性减重/理财收益表述、无法获得的优惠',
            'check': 'ads_misrepresentation',
            'params': {
                'banned_patterns': [
                    r'100%\s*有效', r'包治', r'根治', r'治愈', r'零风险',
                    r'稳赚', r'保本', r'必赚', r'无风险收益', r'一夜暴富',
                    r'无效退款', r'全网最低', r'国家级', r'最佳', r'第一',
                    r'免费.{0,6}运费', r'限时.{0,4}抢购',
                ],
            },
            'source': 'Google Ads 政策：Misrepresentation / Unacceptable business practices',
        },
        'ADS-HEALTH-CLAIM': {
            'group': '广告合规',
            'severity': 'WARN',
            'enforce_type': 'legal_mandatory',
            'desc': '健康类功效宣称需有认证支撑（LegitScript），且不得基于健康推断做个性化定向',
            'check': 'ads_health_claim',
            'params': {
                'health_patterns': [r'减肥', r'瘦身', r'降血糖', r'降血压',
                                    r'抗癌', r'防癌', r'消炎', r'增强免疫'],
            },
            'source': 'Google Ads 政策：健康与药品',
        },
    },
}


def _listing(track):
    """取 listing 结构，兼容真实世界的两种写法。

    - 嵌套：{"listing": {"title":…, "bullets":[…]}}   —— 部分导出工具
    - 扁平：{"title":…, "bullets":[…]}                —— **最常用形态**

    v0.1.2 教训：本函数原写作 track.get('listing', {})，只认嵌套。
    扁平 listing 直接拿不到 title/bullets/ad_copy → 10 条规则 SKIP 9 条，
    报告却是「放行 / exit 0」——**假绿**。而扁平才是默认用法，
    只测嵌套的夹具等于拿幸运路径冒充功能可用。
    """
    inner = track.get('listing')
    if isinstance(inner, dict):
        return inner
    # 扁平：把顶层业务字段收成同一形状，让下游规则不必分两种写法
    keep = ('title', 'bullets', 'ad_copy', 'product', 'marketplace')
    return {k: v for k, v in track.items()
            if k in keep and not k.startswith('_')}


def check_amz_title_len(track, rule, ctx):
    t = _listing(track).get('title')
    if not t:
        return ('SKIP', '未提供标题')
    n = len(t)
    # v0.2.0 三态示范：marketplace 未声明时**不再默认按 US(75) 判定**。
    # 旧逻辑的隐含假设会双向出错：EU 卖家的 76-200 字符合法标题被误杀
    # （假阳性），US 卖家以为上限 200 而被搜索索引拒收（假阴性）。
    # 判不了就说判不了——有确切的未决事实（marketplace），不带 severity。
    mp = ctx.get('marketplace')
    if not mp:
        return ('NEEDS_VALIDATION',
                f'标题 {n} 字符，但 _context.marketplace 未声明——'
                f'无法确定适用上限（美国站 75 / 欧洲站 200）。'
                f'请在 JSON 的 _context 里声明 marketplace 后重跑')
    limit = 75 if mp == 'US' else 200
    if n > limit:
        return ('FAIL', f'标题 {n} 字符，超出 {limit} 上限（{mp} 站）')
    return ('PASS', f'标题 {n} 字符 ≤ {limit}（{mp} 站）')


def check_amz_title_repeat(track, rule, ctx):
    t = _listing(track).get('title')
    if not t:
        return ('SKIP', '未提供标题')
    limit = rule.get('params', {}).get('max_repeat', 2)
    stop = {'the', 'a', 'an', 'of', 'and', 'for', 'with', 'to', 'in', 'on', 'at'}
    words = [w for w in re.findall(r'[a-zA-Z]+', t.lower()) if w not in stop]
    counts = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    over = {w: c for w, c in counts.items() if c > limit}
    if over:
        return ('WARN', f'重复超限：{over}（上限 {limit} 次）')
    return ('PASS', f'无词重复超 {limit} 次')


def check_amz_title_banned(track, rule, ctx):
    t = _listing(track).get('title') or ''
    low = t.lower()
    hits = [w for w in rule.get('params', {}).get('banned_words', [])
            if w in low]
    chars = rule.get('params', {}).get('banned_chars', '')
    bad = sorted({c for c in t if c in chars})
    if hits or bad:
        return ('FAIL', f'促销词 {hits} ／ 禁用符号 {bad}')
    return ('PASS', '无促销词与禁用符号')


def check_amz_bullet_chars(track, rule, ctx):
    bullets = _listing(track).get('bullets') or []
    if not bullets:
        return ('SKIP', '未提供五点')
    bad = rule.get('params', {}).get('banned_chars', '')
    for i, b in enumerate(bullets, 1):
        hit = sorted({c for c in b if c in bad})
        if hit:
            return ('FAIL', f'第 {i} 条含禁用符号 {hit}')
    return ('PASS', f'{len(bullets)} 条五点均无禁用符号')


def check_amz_bullet_emotion(track, rule, ctx):
    bullets = _listing(track).get('bullets') or []
    if not bullets:
        return ('SKIP', '未提供五点')
    p = rule.get('params', {})
    emo = re.compile(p.get('emoji_re', ''))
    for i, b in enumerate(bullets, 1):
        if emo.search(b):
            return ('FAIL', f'第 {i} 条含 emoji')
        for pat in p.get('banned_patterns', []):
            m = re.search(pat, b, flags=re.I)
            if m:
                return ('FAIL', f'第 {i} 条含禁止表述：{m.group(0)!r}')
    return ('PASS', f'{len(bullets)} 条五点均无禁止表述')


def check_amz_bullet_len(track, rule, ctx):
    bullets = _listing(track).get('bullets') or []
    if not bullets:
        return ('SKIP', '未提供五点')
    p = rule.get('params', {})
    for i, b in enumerate(bullets, 1):
        n = len(b)
        if n < p.get('min', 10) or n > p.get('max', 255):
            return ('WARN', f'第 {i} 条 {n} 字符，超出 '
                            f'{p.get("min")}–{p.get("max")} 区间')
    return ('PASS', f'{len(bullets)} 条五点长度均合规')


def check_amz_bullet_total(track, rule, ctx):
    bullets = _listing(track).get('bullets') or []
    if not bullets:
        return ('SKIP', '未提供五点')
    total = sum(len(b.encode('utf-8')) for b in bullets)
    cap = rule.get('params', {}).get('max_bytes', 1000)
    if total > cap:
        return ('FAIL', f'五点合计 {total} 字节 > {cap}，不进搜索索引'
                        f'（超 {total - cap} 字节）')
    return ('PASS', f'五点合计 {total} 字节 ≤ {cap}')


def check_amz_bullet_prefix(track, rule, ctx):
    bullets = _listing(track).get('bullets') or []
    if not bullets:
        return ('SKIP', '未提供五点')
    miss = [i for i, b in enumerate(bullets, 1) if '：' not in b and ':' not in b]
    if miss:
        return ('WARN', f'第 {miss} 条缺「标题: 」前缀（建议项，非硬性）')
    return ('PASS', '各条均含卖点前缀')


def check_ads_misrepresentation(track, rule, ctx):
    ad = _listing(track).get('ad_copy') or {}
    texts = [v for v in ad.values() if isinstance(v, str)]
    if not texts:
        return ('SKIP', '未提供广告文案')
    for pat in rule.get('params', {}).get('banned_patterns', []):
        for t in texts:
            m = re.search(pat, t)
            if m:
                return ('FAIL', f'广告文案含误导性表述：{m.group(0)!r}')
    return ('PASS', f'{len(texts)} 段广告文案无误导性表述')


def check_ads_health_claim(track, rule, ctx):
    ad = _listing(track).get('ad_copy') or {}
    texts = [v for v in ad.values() if isinstance(v, str)]
    product = _listing(track).get('product') or {}
    if not texts and not product:
        return ('SKIP', '未提供广告文案与商品信息')
    blob = ' '.join(texts) + ' ' + ' '.join(
        str(v) for v in product.values() if isinstance(v, str))
    hits = []
    for pat in rule.get('params', {}).get('health_patterns', []):
        m = re.search(pat, blob)
        if m:
            hits.append(m.group(0))
    if not hits:
        return ('PASS', '未检出健康类功效宣称')
    certified = ad.get('legitscript_certified') is True
    if certified:
        return ('WARN', f'检出健康类宣称 {hits}，已声明 LegitScript 认证'
                        f'——确认平台是否仍限制基于健康推断的定向')
    return ('FAIL', f'检出健康类功效宣称 {hits} 且未提供 LegitScript 认证，'
                    f'Google Ads 禁止此类投放')


CHECKERS = {k[len('check_'):]: v for k, v in list(globals().items())
            if k.startswith('check_') and callable(v)}


class RuleSet:
    name = 'ecommerce'
    display = POLICY['display']
    version = POLICY['version']

    @classmethod
    def load(cls):
        rules = []
        for rid, rd in POLICY['rules'].items():
            fn = CHECKERS.get(rd['check'])
            if not fn:
                continue
            meta = {k: v for k, v in rd.items() if k not in ('check', 'severity', 'desc')}
            rules.append(Rule(rid, rd['desc'], rd.get('severity', 'WARN'), fn, **meta))
        return rules

    @classmethod
    def meta(cls):
        return {'display': cls.display, 'red_lines': POLICY['red_lines'],
                'needs_pro_review': [
                    {'rule': 'AMZ-*', 'risk': 'medium',
                     'question': 'Amazon 各站点政策独立且更新频繁，本表阈值为公开规范常见值，'
                                 '发布前须按目标站点最新 Seller Central 文档逐条复核。',
                     'who': '需按站点官方文档复核'}]}

    @classmethod
    def validate(cls):
        """返回「配置错误」的规则 ID 列表（空=全部对得上）。

        两类错都在这里抓住，不让它等到跑的时候才炸：
        1. check 字段对不上 CHECKERS —— 键名不匹配会静默变 0 条规则。
        2. 禁符表混进字母 —— v0.1.1 实际踩过：AMZ-BULLET-CHARS 的
           banned_chars 里混进一个小写 `o`，导致任何含字母 o 的英文
           五点（office / product / bottle / motion…）全部 BLOCK。
           「符号表误含普通字母」这种 bug 肉眼几乎看不出来，但在英文
           语料上是核弹级误报。所以做硬断言：banned_chars 出现任何
           字母，一律点名报错，不许上线。
           ⚠ 只对 banned_chars 断言，不看 banned_words ——
           禁词本来就是英文词组（guaranteed / freebie），里面有字母是对的。
        """
        bad = []
        for rid, rd in POLICY['rules'].items():
            if rd.get('check') not in CHECKERS:
                bad.append(rid)
            for c in rd.get('params', {}).get('banned_chars', '') or '':
                if c.isalpha():
                    bad.append(
                        f'{rid}（banned_chars 含字母 {c!r}，'
                        f'会把普通英文词判成违规）')
        return bad

