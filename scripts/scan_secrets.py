#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
敏感字段扫描器 v1.1（push 前必跑）
=================================
v1.0 的教训：纯正则扫描把 URL 里的工单号/文号/文件名当成手机号与身份证
（`.../articles/46914166185236-...`、`c_1743654684782215.htm`、PDF 文件名），
产生误报。开源项目里「狼来了」的检查器比没有检查器更糟——它训练人忽略告警。

v1.1 修法：命中后做**上下文判定**，只有脱离 URL/文件路径语境才算真命中。

退出码：0=干净  1=发现真实敏感字段（阻塞 push）
零依赖、只读。
"""
import re
import sys
import os

PATTERNS = {
    '邮箱': r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}',
    'sk-key': r'sk-[A-Za-z0-9]{16,}',
    '手机号': r'(?<![0-9])1[3-9]\d{9}(?![0-9])',
    '身份证': r'(?<![0-9A-Za-z])\d{17}[\dXx](?![0-9A-Za-z])',
    '银行卡': r'(?<![0-9])[1-9]\d{14}(?![0-9])',
}

# 允许误报的语境：URL、文件路径、版本号、日期
SAFE_CONTEXT = re.compile(
    r'(https?://|www\.|support\.|/hc/en-us/|/upload/|\.pdf|\.html?\b|\.md\b|'
    r'\.json\b|articles/|v\d+\.\d+)',
    re.I,
)

# 邮箱白名单：项目/文档用途的公共地址不算泄露
EMAIL_ALLOW = {
    'noreply@github.com',
}


def strip_safe(text):
    """把 URL 与路径片段替换成占位符，避免其内部数字被当作敏感字段"""
    t = re.sub(r'https?://\S+', lambda m: '@@URL@@' * (len(m.group(0)) // 7 + 1), text)
    t = re.sub(r'\b[\w\-/\.]+\.(?:pdf|html?|md|json|py|js|ts|txt)\b', '@@PATH@@', t, flags=re.I)
    t = re.sub(r'\b[1-9]\d{2}-\d{2}-\d{2}\b', '@@DATE@@', t)
    return t


def scan(path, verbose=True):
    findings = []
    with open(path, encoding='utf-8', errors='ignore') as f:
        raw = f.read()
    cleaned = strip_safe(raw)
    for label, pat in PATTERNS.items():
        for m in re.finditer(pat, cleaned):
            val = m.group(0)
            if label == '邮箱' and val.lower() in EMAIL_ALLOW:
                continue
            # 上下文若仍带 URL/路径特征，判为误报
            ctx = cleaned[max(0, m.start() - 40):m.end() + 40]
            if SAFE_CONTEXT.search(ctx):
                continue
            # 尝试在原文中定位真实内容，供人工复核
            idx = raw.find(val)
            findings.append((label, val, raw[max(0, idx - 50):idx + len(val) + 20]
                             if idx >= 0 else ctx))
    if verbose and not findings:
        print(f'  ✓ {path}')
    elif verbose and findings:
        for label, val, ctx in findings:
            print(f'  ⚠ {path}  [{label}] {val}')
            print(f'      上下文: {ctx.strip()[:110]}')
    return findings


def main():
    targets = sys.argv[1:]
    if not targets:
        print(__doc__)
        return 2
    files = []
    for t in targets:
        if os.path.isdir(t):
            for root, dirs, fs in os.walk(t):
                dirs[:] = [d for d in dirs if d != '.git']
                files += [os.path.join(root, f) for f in fs
                          if f.endswith(('.md', '.py', '.json', '.txt', '.yaml', '.yml'))]
        elif os.path.isfile(t):
            files.append(t)
        else:
            print(f'  ✗ 路径不存在: {t}')
            return 1

    print('=' * 66)
    print('敏感字段扫描 v1.1（已过滤 URL/路径/日期语境）')
    print('=' * 66)
    all_f = []
    for p in files:
        all_f += scan(p)
    print('-' * 66)
    if all_f:
        print(f'发现 {len(all_f)} 处待人工复核：')
        for label, val, ctx in all_f:
            print(f'  ✗ [{label}] {val}  ←  {ctx.strip()[:90]}')
        print('\n结论：存在疑似敏感字段，人工复核后再 push。')
        return 1
    print(f'✅ 扫描 {len(files)} 个文件，未发现真实敏感字段。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
