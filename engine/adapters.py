#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
适配器：把任意 AI 产出转成统一中间结构
=========================================
引擎不读文件、不解析文本，只接受一个 dict。
所以需要一个转换层。**加一种产出形态 = 在此加一个适配器，引擎与规则零改动。**

已支持：
  .md / .markdown  → markdown 适配器（日报、报告、方案）
  .html / .htm    → html 适配器（交付页面）
  .py / .js / .ts → code 适配器（AI 生成代码）
  .json           → 视为已适配的结构，原样返回
"""
import os
import re
import json

from engine import schema as S

_ADAPTERS = {}


def register(exts):
    """扩展名 → 适配器函数的注册装饰器"""
    def deco(fn):
        for e in exts:
            _ADAPTERS[e] = fn
        return fn
    return deco


# ---------- markdown ----------
@register(['.md', '.markdown'])
def _md(path, text):
    d = S.empty_schema('markdown')
    d['title'] = next((l.lstrip('# ').strip() for l in text.splitlines()
                       if l.strip().startswith('# ')), '')
    # 标题层级
    for i, line in enumerate(text.splitlines(), 1):
        m = re.match(r'^(#{1,6})\s+(.+?)\s*$', line)
        if m:
            d['sections'].append({'level': len(m.group(1)),
                                  'heading': m.group(2), 'line': i})
    # 代码块闭合
    fence = 0
    start = 0
    for i, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith('```'):
            if fence == 0:
                fence, start = 1, i
            else:
                d['code_blocks'].append({
                    'lang': text.splitlines()[start].strip().strip('`') or '',
                    'start_line': start, 'end_line': i, 'closed': True})
                fence = 0
    if fence == 1:                       # 未闭合
        d['code_blocks'].append({'lang': '', 'start_line': start,
                                 'end_line': None, 'closed': False})
    d['todos'] = re.findall(r'^\s*[-*]\s+\[([ xX])\]\s+(.+)$', text, flags=re.M)
    d['tables'] = len(re.findall(r'^\|.*\|\s*$', text, flags=re.M))
    d['links'] = [{'url': m.group(2), 'line': text[:m.start()].count('\n') + 1,
                   'text': m.group(1)}
                  for m in re.finditer(r'\[([^\]]{0,60})\]\(([^)]+)\)', text)]
    d['claims'] = S.find_claims(text)
    d['numbers'] = S.find_numbers(text)
    # 围栏代码块内的行不参与占位符扫描：`validate()` / `r.items()` 里的
    # 空半角括号、示例代码里的 `{k: v}` 都不是占位符（实测误报，v1.1.0 修）。
    _fenced = set()
    for _b in d.get('code_blocks') or []:
        if _b.get('end_line'):
            _fenced.update(range(_b['start_line'], _b['end_line'] + 1))
    d['placeholders'] = S.find_placeholders(text, skip_lines=_fenced)
    d['absolute'] = S.find_absolute(text)
    d['raw_lines'] = len(text.splitlines())
    d['raw_chars'] = len(text)
    return d


# ---------- html ----------
@register(['.html', '.htm'])
def _html(path, text):
    d = S.empty_schema('html')
    m = re.search(r'<title[^>]*>(.*?)</title>', text, flags=re.S | re.I)
    d['title'] = m.group(1).strip() if m else ''
    for i, mt in enumerate(re.finditer(r'<h([1-6])[^>]*>(.*?)</h\1>',
                                       text, flags=re.S | re.I), 1):
        d['sections'].append({'level': int(mt.group(1)),
                              'heading': re.sub(r'<[^>]+>', '', mt.group(2)).strip()[:60],
                              'line': text[:mt.start()].count('\n') + 1})
    d['links'] = [{'url': u, 'line': text[:m.start()].count('\n') + 1, 'text': ''}
                  for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)', text, flags=re.I)]
    d['todos'] = re.findall(r'<li[^>]*>(.*?)</li>', text, flags=re.S | re.I)[:50]
    # ⚠ v1.0.1 修正：原先把整页 body 去标签后交给 find_claims，
    # 结果 UI 装饰性文本全被当成论断 —— metric 卡片的裸数字
    # （<div class="v">0</div>）、页头元信息行、表格分隔线，
    # 一份正常报告能产出 60+ 条「无源数字断言」，假阳性率 >80%。
    # 修法：只从语义正文标签提取（p / li / td / th / blockquote / h1-h6），
    # 跳过 div / span 等纯布局容器。
    prose = []          # [(原文行号, 文本)]
    for mt in re.finditer(
            r'<(p|li|td|th|blockquote|figcaption|h[1-6])[^>]*>(.*?)</\1>',
            text, flags=re.S | re.I):
        chunk = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', mt.group(2),
                       flags=re.S | re.I)
        chunk = re.sub(r'<[^>]+>', '', chunk)
        for a, b in (('&nbsp;', ' '), ('&amp;', '&'), ('&lt;', '<'),
                     ('&gt;', '>'), ('&quot;', '"')):
            chunk = chunk.replace(a, b)
        # 原文起始行号 —— 扫描时报的行号必须对得上原文
        line = text[:mt.start()].count('\n') + 1
        # 标题加 '# ' 前缀：让 schema._HEADING 能识别并排除标题行
        # （否则「0 · 费曼层」这类章节编号会被当成无源数字断言）
        prefix = '# ' if re.match(r'h[1-6]$', mt.group(1), re.I) else ''
        # 记录【原文起始行号】，扫描时报的行号才对得上原文
        prose.append((line, prefix + chunk))
    d['claims'] = S._claims_from_lines(prose)
    d['placeholders'] = S.find_placeholders_lines(prose)
    d['absolute'] = S.find_absolute_lines(prose)
    body = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', text,
                  flags=re.S | re.I)
    body = re.sub(r'<[^>]+>', '\n', body)
    d['numbers'] = S.find_numbers(body)
    d['tables'] = len(re.findall(r'<table', text, flags=re.I))
    d['raw_lines'] = len(text.splitlines())
    d['raw_chars'] = len(text)
    return d


# ---------- code ----------
@register(['.py', '.js', '.ts', '.tsx', '.jsx'])
def _code(path, text):
    d = S.empty_schema('code')
    d['title'] = os.path.basename(path)
    # 未闭合的引号/括号（按行累计，末行仍不平衡即报）
    depth = {'(': 0, '[': 0, '{': 0}
    pairs = {')': '(', ']': '[', '}': '{'}
    for i, line in enumerate(text.splitlines(), 1):
        s = re.sub(r'#.*$|//.*$', '', line)
        s = re.sub(r'["\'].*?["\']', '', s)
        for ch in s:
            if ch in depth:
                depth[ch] += 1
            elif ch in pairs:
                depth[pairs[ch]] -= 1
    d['bracket_balance'] = depth
    d['todos'] = re.findall(r'^\s*#\s*(TODO|FIXME|XXX|HACK)\b.*$', text, flags=re.M)
    d['claims'] = S.find_claims(re.sub(r'#.*$', '', text, flags=re.M))
    d['numbers'] = S.find_numbers(text)
    d['placeholders'] = S.find_placeholders(text)
    d['absolute'] = S.find_absolute(text)
    d['raw_lines'] = len(text.splitlines())
    d['raw_chars'] = len(text)
    return d


def adapt(path):
    """主入口：任意文件 → 统一结构"""
    ext = os.path.splitext(path)[1].lower()
    if ext == '.json':
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    fn = _ADAPTERS.get(ext)
    if not fn:
        raise ValueError(f'无适配器支持该扩展名: {ext}（支持: '
                         f'{", ".join(sorted(_ADAPTERS))}）')
    with open(path, encoding='utf-8', errors='replace') as f:
        return fn(path, f.read())


def supported():
    return sorted(_ADAPTERS)
