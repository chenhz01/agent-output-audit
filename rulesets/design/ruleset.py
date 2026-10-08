#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
规则集：设计输出体检（design）
==============================
来源：impeccable（pbakaus/impeccable，2026-10-06/07 两轮核真通过）5 个检测器
逐条映射 → 本引擎「能不能写成 if」判据筛选后的静态可判定子集。
接线原则：不改引擎、不改适配器 —— 所有检查器从 ctx['_raw']（原始 HTML 文本）
自行解析内联 style 与 <style> 块，适配器零改动。

覆盖范围（诚实声明，写进 red_lines）：
  · 只检查内联 style="..." 与页面内 <style> 块 —— 外链 .css 文件不查
  · 颜色只查「同一声明块内 color 与 background 同时显式声明」的自洽对，
    跨规则/继承/覆盖情形不查（静态分析无法 100% 判定，不冒充）
  · 间距/字号只认 px（rem 按 16px 基准换算），%/em/auto 跳过
  · D-005 遮挡是静态启发式（absolute/fixed + 负 z-index 组合），
    真实 bbox 遮挡需浏览器渲染，本规则只提示「需人判」
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
from engine.engine import Rule  # noqa: E402

POLICY = {
    'version': '0.1.0',
    'display': '设计输出体检（design）',
    'applies_to': ['html'],
    'red_lines': [
        '本规则集做静态 HTML/CSS 检查，外链 .css 与 JS 动态样式不在覆盖范围',
        '颜色只查同声明块内自洽 color/background 对；继承与覆盖情形需人判',
        'rem 按 16px 基准换算；非 px 单位（%/em）不做网格/步进判定',
        'D-005 是遮挡风险启发式，不是渲染级判定 —— WARN 项需人判断',
    ],
    'rules': {
        'LOW-CONTRAST': {
            'group': '可读性',
            'severity': 'BLOCK',
            'enforce_type': 'legal_standard',
            'desc': '文字/背景对比度不达标（<3:1 为任何字号都违规，BLOCK；3~4.5:1 视字号 WARN）',
            'check': 'chk_low_contrast',
            'params': {'large_min': 3.0, 'normal_min': 4.5, 'report_top': 3},
            'source': 'WCAG 2.1 SC 1.4.3 对比度阈值 + impeccable low-contrast 检测器映射',
        },
        'CRAMPED-SPACING': {
            'group': '布局',
            'severity': 'WARN',
            'enforce_type': 'commercial_practice',
            'desc': '间距过小（非零 padding/margin <4px）—— 元素挤成一团',
            'check': 'chk_cramped_spacing',
            'params': {'min_px': 4},
            'source': '4px/8pt 网格惯例（Material/Polaris）+ impeccable cramped-padding 映射',
        },
        'FLAT-TYPE': {
            'group': '层级',
            'severity': 'WARN',
            'enforce_type': 'project_custom',
            'desc': '字号层级扁平（相邻层级比 <1.125 的比例过高）—— 看不出重点',
            'check': 'chk_flat_type',
            'params': {'min_step': 1.125, 'min_samples': 3, 'warn_ratio': 0.5},
            'source': 'type scale 惯例（≥1.125 major second）+ impeccable flat-type-hierarchy 映射',
        },
        'OVERUSED-FONT': {
            'group': '辨识度',
            'severity': 'WARN',
            'enforce_type': 'commercial_practice',
            'desc': '使用过用默认字体（黑名单可配）—— AI 生成页的「默认脸」',
            'check': 'chk_overused_font',
            'params': {'blacklist': ['Inter', 'Roboto', 'Arial', 'system-ui',
                                     '-apple-system', 'Segoe UI', 'Helvetica Neue']},
            'source': 'impeccable overused-font 检测器映射（黑名单为本项目配置，非标准）',
        },
        'OCCLUSION-RISK': {
            'group': '遮挡',
            'severity': 'WARN',
            'enforce_type': 'project_custom',
            'desc': '遮挡风险组合（absolute/fixed + 负 z-index/负 margin）—— 静态启发式，需人判',
            'check': 'chk_occlusion_risk',
            'source': 'impeccable text-occlusion 检测器降级映射（真实 bbox 需浏览器渲染）',
        },
    },
}

# ================= 工具函数 =================

_NAMED = {
    'black': (0, 0, 0), 'white': (255, 255, 255), 'red': (255, 0, 0),
    'green': (0, 128, 0), 'blue': (0, 0, 255), 'gray': (128, 128, 128),
    'grey': (128, 128, 128), 'silver': (192, 192, 192), 'navy': (0, 0, 128),
    'teal': (0, 128, 128), 'orange': (255, 165, 0), 'yellow': (255, 255, 0),
    'gold': (255, 215, 0), 'purple': (128, 0, 128), 'pink': (255, 192, 203),
}

_DECL_RE = re.compile(r'([a-z-]+)\s*:\s*([^;]+)', re.I)
_STYLE_BLOCK_RE = re.compile(r'<style[^>]*>(.*?)</style>', re.S | re.I)
_CSS_RULE_RE = re.compile(r'([^{}]+)\{([^{}]*)\}')
_INLINE_RE = re.compile(r'style\s*=\s*"([^"]*)"|style\s*=\s*\'([^\']*)\'', re.I)


def parse_color(s):
    """解析颜色 → (r,g,b)；不可解析/带透明度 → None"""
    s = s.strip().lower()
    if s in ('transparent', 'inherit', 'initial', 'unset') or 'var(' in s or 'calc(' in s:
        return None
    m = re.fullmatch(r'#([0-9a-f]{6})([0-9a-f]{2})?', s)
    if m:
        if m.group(2) and int(m.group(2), 16) < 255:  # 半透明不判
            return None
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r'#([0-9a-f]{3})', s)
    if m:
        h = m.group(1)
        return tuple(int(c * 2, 16) for c in h)
    m = re.fullmatch(r'rgba?\(([^)]+)\)', s)
    if m:
        parts = [p.strip() for p in m.group(1).split(',')]
        if len(parts) >= 4:
            try:
                if float(parts[3]) < 1:
                    return None
            except ValueError:
                return None
        try:
            vals = [float(p) for p in parts[:3]]
        except ValueError:
            return None
        if any(v > 255 for v in vals):  # 0-1 写法
            vals = [v * 255 for v in vals]
        return tuple(int(round(v)) for v in vals)
    return _NAMED.get(s)


def _lum(rgb):
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(c1, c2):
    l1, l2 = sorted((_lum(c1), _lum(c2)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def _iter_decl_blocks(raw):
    """产出 (来源标签, 声明dict)。来源：inline@lineN / css:selector"""
    for m in _INLINE_RE.finditer(raw):
        line = raw[:m.start()].count('\n') + 1
        body = m.group(1) or m.group(2) or ''
        decls = {}
        for d in _DECL_RE.finditer(body):
            decls[d.group(1).strip().lower()] = d.group(2).strip()
        if decls:
            yield f'inline@L{line}', decls
    for sb in _STYLE_BLOCK_RE.finditer(raw):
        for cr in _CSS_RULE_RE.finditer(sb.group(1)):
            sel = cr.group(1).strip().splitlines()[-1].strip()[:40] if cr.group(1).strip() else '?'
            decls = {}
            for d in _DECL_RE.finditer(cr.group(2)):
                decls[d.group(1).strip().lower()] = d.group(2).strip()
            if decls:
                yield f'css:{sel}', decls


_PX_RE = re.compile(r'^(-?\d+(?:\.\d+)?)px$', re.I)


def _px(v):
    m = _PX_RE.match((v or '').strip())
    return float(m.group(1)) if m else None


# ================= 检查器 =================

def chk_low_contrast(target, rule, ctx):
    if target.get('kind') != 'html':
        return ('SKIP', '非 HTML，不适用')
    raw = ctx.get('_raw', '')
    p = rule.get('params', {})
    block_hits, warn_hits, skipped = [], [], 0
    for where, decls in _iter_decl_blocks(raw):
        fg = parse_color(decls.get('color', ''))
        bg = parse_color(decls.get('background') or decls.get('background-color') or '')
        if fg is None and bg is None:
            continue
        if fg is None or bg is None:
            skipped += 1
            continue
        r = contrast(fg, bg)
        if r < p.get('large_min', 3.0):
            block_hits.append((where, r))
        elif r < p.get('normal_min', 4.5):
            warn_hits.append((where, r))
    if block_hits:
        top = p.get('report_top', 3)
        shown = '；'.join(f'{w} {r:.2f}:1' for w, r in block_hits[:top])
        tail = f'（共 {len(block_hits)} 对）' if len(block_hits) > top else ''
        return ('FAIL', f'{len(block_hits)} 对颜色对比度 <3:1（任何字号都不达标）：{shown}{tail}'
                        f'。另有 {len(warn_hits)} 对处于 3~4.5:1 需按字号判断，'
                        f'{skipped} 对因信息不足跳过')
    if warn_hits:
        top = p.get('report_top', 3)
        shown = '；'.join(f'{w} {r:.2f}:1' for w, r in warn_hits[:top])
        return ('WARN', f'{len(warn_hits)} 对颜色对比度 3~4.5:1（正文不达标、大字可过，'
                        f'需按实际字号判断）：{shown}')
    if skipped and not block_hits and not warn_hits:
        return ('PASS', f'对比度达标（{skipped} 对颜色因半透明/变量未判定）')
    return ('PASS', '显式 color/background 对均达标或无需判定')


def chk_cramped_spacing(target, rule, ctx):
    if target.get('kind') != 'html':
        return ('SKIP', '非 HTML，不适用')
    raw = ctx.get('_raw', '')
    min_px = rule.get('params', {}).get('min_px', 4)
    bad, grid_miss = [], 0
    for where, decls in _iter_decl_blocks(raw):
        for k, v in decls.items():
            if not re.match(r'(padding|margin)(-(top|right|bottom|left))?$', k):
                continue
            for tok in v.split():
                px = _px(tok)
                if px is None:
                    continue
                if 0 < px < min_px:
                    bad.append((where, k, px))
                elif px % 4 != 0:
                    grid_miss += 1
    if bad:
        shown = '；'.join(f'{w} {k}={px:g}px' for w, k, px in bad[:3])
        tail = f'（共 {len(bad)} 处）' if len(bad) > 3 else ''
        return ('WARN', f'{len(bad)} 处非零间距 <{min_px}px（确定性拥挤信号）：{shown}{tail}'
                        f'。另有 {grid_miss} 处不在 4px 网格上（惯例项，供参考）')
    return ('PASS', f'无 <{min_px}px 间距（{grid_miss} 处不在 4px 网格，属惯例项不告警）')


def chk_flat_type(target, rule, ctx):
    if target.get('kind') != 'html':
        return ('SKIP', '非 HTML，不适用')
    raw = ctx.get('_raw', '')
    p = rule.get('params', {})
    sizes = set()
    for _, decls in _iter_decl_blocks(raw):
        v = decls.get('font-size')
        if not v:
            continue
        px = _px(v)
        if px is None:
            m = re.fullmatch(r'([\d.]+)rem', v.strip(), re.I)
            px = float(m.group(1)) * 16 if m else None
        if px:
            sizes.add(round(px, 1))
    if len(sizes) < p.get('min_samples', 3):
        return ('SKIP', f'仅 {len(sizes)} 个不同字号，样本不足（扁平/单一布局无法判定层级）')
    ss = sorted(sizes, reverse=True)
    # 步进 = 大字号/相邻小字号（a/b）。v0.1.0 初版写成 b/a（小/大）恒 <1.125，
    # 把 1.75 倍正常层级也判扁平 —— 由 design_pass 夹具（必过却 WARN）当场抓出，
    # 与引擎 v1.0.1 E 组方向 bug 同类，夹具法的直接收益。
    flat = sum(1 for a, b in zip(ss, ss[1:]) if a / b < p.get('min_step', 1.125))
    ratio = flat / (len(ss) - 1)
    if ratio >= p.get('warn_ratio', 0.5):
        return ('WARN', f'{flat}/{len(ss) - 1} 个相邻字号对步进 <{p.get("min_step")}'
                        f'（{ratio:.0%}）。字号序列：{ss} —— 层级扁平，重点不突出')
    return ('PASS', f'{len(ss)} 个字号层级步进达标（{ss}）')


def chk_overused_font(target, rule, ctx):
    if target.get('kind') != 'html':
        return ('SKIP', '非 HTML，不适用')
    raw = ctx.get('_raw', '')
    bl = [f.lower() for f in rule.get('params', {}).get('blacklist', [])]
    hits = []
    for where, decls in _iter_decl_blocks(raw):
        ff = decls.get('font-family')
        if not ff:
            continue
        first = re.split(r'[,\n]', ff)[0].strip().strip('"\'').lower()
        if first in bl:
            hits.append((where, first))
    uniq = sorted({f for _, f in hits})
    if uniq:
        return ('WARN', f'{len(hits)} 处使用过用字体 {uniq}（黑名单前 2 列）—— '
                        f'AI 生成页默认脸，建议换标识字体')
    return ('PASS', '未检出黑名单字体')


def chk_occlusion_risk(target, rule, ctx):
    if target.get('kind') != 'html':
        return ('SKIP', '非 HTML，不适用')
    raw = ctx.get('_raw', '')
    hits = []
    for where, decls in _iter_decl_blocks(raw):
        pos = decls.get('position', '').lower()
        if pos not in ('absolute', 'fixed'):
            continue
        z = None
        zv = decls.get('z-index', '')
        try:
            z = float(zv)  # z-index 是无单位整数，不能走 _px（要求 px 后缀）
        except (TypeError, ValueError):
            z = None
        neg_margin = any((_px(v) or 0) < 0
                         for k, v in decls.items()
                         if re.match(r'margin(-top|-right|-bottom|-left)?$', k))
        if (z is not None and z < 0) or neg_margin:
            why = '负 z-index' if (z is not None and z < 0) else '负 margin'
            hits.append(f'{where}({pos}+{why})')
    if hits:
        return ('WARN', f'{len(hits)} 处遮挡风险组合：{"；".join(hits[:3])} —— '
                        f'静态启发式，是否真的盖住文字需浏览器渲染后人判')
    return ('PASS', '无 absolute/fixed + 负 z-index/负 margin 组合')


CHECKERS = {k: v for k, v in list(globals().items())
            if k.startswith('chk_') and callable(v)}


class RuleSet:
    name = 'design'
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
    def meta(cls):
        return {'display': cls.display, 'red_lines': POLICY['red_lines'],
                'needs_pro_review': [
                    {'rule': 'CRAMPED-SPACING', 'risk': 'medium',
                     'question': '<4px 阈值与 4px 网格未在真实设计语料上标定，'
                                 '部分设计系统刻意用 2px 微调（边框间隙）。',
                     'who': '需按交付类型标定'},
                    {'rule': 'FLAT-TYPE', 'risk': 'low',
                     'question': 'rem 基准假设 16px，页面改 html{font-size} 时误判。',
                     'who': '静态分析固有局限，声明即可'},
                    {'rule': 'OCCLUSION-RISK', 'risk': 'medium',
                     'question': '启发式假阳性率未知，真实 bbox 判定需浏览器渲染。',
                     'who': '如需精确判定应接 Playwright 截图比对'}]}

    @classmethod
    def validate(cls):
        """返回 check 字段无法解析的规则 ID 列表（空=全部对得上）"""
        return [rid for rid, rd in POLICY['rules'].items()
                if rd.get('check') not in CHECKERS]
