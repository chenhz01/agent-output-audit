#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
规则集：短视频 / 口播脚本合规
================================
**本规则集的唯一目的：验证引擎的横向扩展成本。**
它是在引擎冻结之后写的 —— engine/ 无一处改动。

它带一个别的垂类都没有的能力：**时间轴交叉对齐**
（字数 ↔ 语速 ↔ 字幕行宽），因为只有视频有「时间」这个维度。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
from engine.engine import Rule  # noqa: E402

POLICY = {
    'version': '1.0.0',
    'display': '短视频 / 口播脚本合规',
    'red_lines': [
        '语速基准取自经验值（中文口播 220-280 字/分），个体差异大，WARN 需人判断',
        '医疗/金融类内容须另有专业合规审核，本规则集只覆盖通用红线',
    ],
    'rules': {
        'AD-LIMITED-TERM': {
            'group': '广告法',
            'severity': 'BLOCK',
            'enforce_type': 'legal_mandatory',
            'desc': '广告法极限词（国家级/最佳/第一/100%/无效退款/零风险等）',
            'check': 'sv_limited_term',
            'params': {'patterns': [
                r'国家级', r'世界级', r'最高级', r'最佳', r'最好', r'第一名',
                r'100\s*%', r'百分百', r'无效退款', r'包治', r'根治',
                r'治愈率', r'零风险', r'无副作用', r'永久', r'绝对',
                r'全网最低', r'独家首创', r'绝无仅有', r'万能',
            ]},
            'source': '《中华人民共和国广告法》第九条（禁用绝对化用语）',
        },
        'AD-MEDICAL-CLAIM': {
            'group': '医疗宣称',
            'severity': 'BLOCK',
            'enforce_type': 'legal_mandatory',
            'desc': '非医疗资质不得宣称疗效（治愈/根治/无副作用/替代药品）',
            'check': 'sv_medical_claim',
            'params': {'patterns': [
                r'根治', r'治愈', r'痊愈', r'替代(?:药物|药品|治疗)',
                r'无副作用', r'不复发', r'药到病除', r'特效',
            ]},
            'source': '《广告法》第十七条（非医疗广告不得涉及疾病治疗功能）',
        },
        'AD-COMPARISON': {
            'group': '广告法',
            'severity': 'WARN',
            'enforce_type': 'legal_mandatory',
            'desc': '贬低同类商品的比较广告（最好之外的「最」「第一」）',
            'check': 'sv_comparison',
            'params': {'patterns': [r'比[^。！]{0,8}(?:更强|更好|更优|领先)', r'吊打', r'完胜']},
            'source': '《广告法》第十三条（不得贬低其他生产经营者商品）',
        },
        'SCRIPT-RATE': {
            'group': '时间轴',
            'severity': 'WARN',
            # v1.0.1 判据来源修正（2026-10-09 SCT 标注审计）：
            # 220-280 字/分是经验基准，不是任何平台的技术规范 —— 原标
            # platform_technical 属于「借外部权威自抬身价」，按判据来源
            # 应归自定（project_custom），结论采信时降一级。
            'enforce_type': 'project_custom',
            'desc': '口播字数与目标时长不匹配（中文口播 220-280 字/分）',
            'check': 'sv_rate',
            'params': {'per_min_low': 220, 'per_min_high': 280, 'fast_high': 340},
            'source': '口播语速经验基准',
            'confidence_floor': 0.8,
        },
        'SUBTITLE-WIDTH': {
            'group': '时间轴',
            'severity': 'WARN',
            'enforce_type': 'platform_technical',
            'desc': '字幕单行 12-15 字（超出将换行或超出安全区）',
            'check': 'sv_subtitle_width',
            'params': {'low': 12, 'high': 15},
            'source': '竖屏字幕排版惯例（安全区内单行字数）',
        },
        'SCRIPT-EMPTY': {
            'group': '完整性',
            'severity': 'BLOCK',
            'enforce_type': 'project_custom',
            'desc': '口播稿为空或仅标题（无实质内容）',
            'check': 'sv_empty',
            'params': {'min_chars': 30},
            'source': '交付完整性',
        },
        'CTA-UNQUALIFIED': {
            'group': '广告法',
            'severity': 'WARN',
            'enforce_type': 'legal_mandatory',
            'desc': '绝对化促销承诺（限时抢购/最后一天/仅此一次）',
            'check': 'sv_cta',
            'params': {'patterns': [
                r'最后\s*\d*\s*(?:一天|小时|时刻)', r'仅此一次', r'错过再无',
                r'限时抢购', r'史上最低', r'最后\s*\d+\s*件',
            ]},
            'source': '促销行为合规（价格促销需真实可验证）',
        },
    },
}


def _script(track):
    return track.get('script', {})


def _lines(track):
    out = [l.strip() for l in (_script(track).get('lines') or []) if l.strip()]
    return out or [x for x in (_script(track).get('text') or '').splitlines() if x.strip()]


def sv_limited_term(track, rule, ctx):
    lines = _lines(track)
    if not lines:
        return ('SKIP', '无口播稿')
    for i, ln in enumerate(lines, 1):
        for pat in rule.get('params', {}).get('patterns', []):
            m = re.search(pat, ln)
            if m:
                return ('FAIL', f'第 {i} 行含极限词「{m.group(0)}」')
    return ('PASS', f'{len(lines)} 行无极限词')


def sv_medical_claim(track, rule, ctx):
    if not ctx.get('is_medical', False):
        return ('SKIP', '非医疗类内容，不适用（context.is_medical 未开启）')
    lines = _lines(track)
    for i, ln in enumerate(lines, 1):
        for pat in rule.get('params', {}).get('patterns', []):
            m = re.search(pat, ln)
            if m:
                return ('FAIL', f'第 {i} 行含医疗宣称「{m.group(0)}」——'
                                f'非医疗资质不得涉及疗效')
    return ('PASS', '无医疗疗效宣称')


def sv_comparison(track, rule, ctx):
    lines = _lines(track)
    hits = []
    for i, ln in enumerate(lines, 1):
        for pat in rule.get('params', {}).get('patterns', []):
            m = re.search(pat, ln)
            if m:
                hits.append(f'第{i}行「{m.group(0)}」')
                break
    if hits:
        return ('WARN', f'{len(hits)} 处比较/贬低表述：{"；".join(hits[:3])}')
    return ('PASS', '无贬低性比较')


def sv_rate(track, rule, ctx):
    lines = _lines(track)
    dur = _script(track).get('duration_sec')
    if not lines or not dur:
        return ('SKIP', '缺时长或缺稿，无法核算语速')
    chars = sum(len(re.sub(r'[，。！？、,.!?\s]', '', l)) for l in lines)
    rate = chars / (dur / 60.0)
    p = rule.get('params', {})
    lo, hi, fast = p['per_min_low'], p['per_min_high'], p['fast_high']
    if rate > fast:
        return ('WARN', f'语速 {rate:.0f} 字/分 > {fast}（过快，听不清）')
    if rate < lo:
        return ('WARN', f'语速 {rate:.0f} 字/分 < {lo}（偏慢，时长会超）')
    if rate > hi:
        return ('WARN', f'语速 {rate:.0f} 字/分 超常规上限 {hi}')
    return ('PASS', f'语速 {rate:.0f} 字/分，在 {lo}-{hi} 常规区间')


def sv_subtitle_width(track, rule, ctx):
    subs = _script(track).get('subtitles') or []
    if not subs:
        return ('SKIP', '未提供字幕')
    p = rule.get('params', {})
    bad = []
    for i, s in enumerate(subs, 1):
        n = len(s.strip())
        if n < p['low'] or n > p['high']:
            bad.append(f'第{i}行{n}字')
    if bad:
        return ('WARN', f'{len(bad)}/{len(subs)} 条字幕超出 '
                        f'{p["low"]}-{p["high"]} 字：{"、".join(bad[:3])}')
    return ('PASS', f'{len(subs)} 条字幕行宽合规')


def sv_empty(track, rule, ctx):
    lines = _lines(track)
    chars = sum(len(l) for l in lines)
    need = rule.get('params', {}).get('min_chars', 30)
    if chars < need:
        return ('FAIL', f'口播稿仅 {chars} 字，低于 {need} 字 —— 疑似只有标题')
    return ('PASS', f'{chars} 字，{len(lines)} 行')


def sv_cta(track, rule, ctx):
    lines = _lines(track)
    hits = []
    for i, ln in enumerate(lines, 1):
        for pat in rule.get('params', {}).get('patterns', []):
            m = re.search(pat, ln)
            if m:
                hits.append(f'第{i}行「{m.group(0)}」')
                break
    if hits:
        return ('WARN', f'{len(hits)} 处绝对化促销承诺（需真实可验证）：'
                        f'{"；".join(hits[:3])}')
    return ('PASS', '无绝对化促销承诺')


# ⚠ 键名必须与 POLICY 里的 check 字段【字面一致】，不做任何剥/加前缀处理。
# 这个坑一天踩了 4 次（music/ecommerce/ai-output/shortvideo），
# 每次都表现为「0 条规则」——靠 validate() 与零规则守卫兜住。
CHECKERS = {k: v for k, v in list(globals().items())
            if k.startswith('sv_') and callable(v)}


class RuleSet:
    name = 'shortvideo'
    display = POLICY['display']
    version = POLICY['version']

    @classmethod
    def load(cls):
        rules = []
        for rid, rd in POLICY['rules'].items():
            fn = CHECKERS.get(rd['check'])
            if not fn:
                continue
            meta = {k: v for k, v in rd.items()
                    if k not in ('check', 'severity', 'desc')}
            rules.append(Rule(rid, rd['desc'], rd.get('severity', 'WARN'),
                              fn, **meta))
        return rules

    @classmethod
    def validate(cls):
        """返回 check 字段无法解析的规则 ID 列表（空=全部对得上）"""
        return [rid for rid, rd in POLICY['rules'].items()
                if rd.get('check') not in CHECKERS]

    @classmethod
    def meta(cls):
        return {'display': cls.display, 'red_lines': POLICY['red_lines'],
                'needs_pro_review': [
                    {'rule': 'SCRIPT-RATE', 'risk': 'medium',
                     'question': '语速区间 220-280 字/分取自经验值，未按语速个体差异'
                                 '分层（快节奏带货 vs 知识口播差异很大）。'
                                 '是否应按账号类型设不同区间？',
                     'who': '需用真实账号的完播率/留存数据标定'},
                    {'rule': 'AD-LIMITED-TERM', 'risk': 'low',
                     'question': '极限词表为公开执法口径整理，'
                                 '但各地平台细则可能更严（如医疗类连「最」字都不许用）。',
                     'who': '需按目标平台最新社区规范复核'},
                ]}
