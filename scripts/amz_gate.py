#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
amz_gate · Amazon listing 出口闸（最小可卖版 v0.1）
====================================================
一句话：在 listing 被上架之前拦住它。

用法：
    python scripts/amz_gate.py <listing.json>            # 终端报告
    python scripts/amz_gate.py <listing.json> --sarif    # GitHub Code Scanning
    python scripts/amz_gate.py <listing.json> --json     # 机读

退出码（与引擎一致，绝不让「规则坏了」混同于「内容有问题」）：
    0 放行    1 必须修（BLOCK）    2 人看一眼（WARN）    3 规则/引擎故障

设计约束（v0.1 立下的，后面不许破）：
  1. **本文件不写任何一条检查逻辑。** 检查全在 rulesets/ecommerce/。
     加规则改规则集，不碰这里 —— 否则「加垂类=放个目录」就废了。
  2. 判定分档沿用引擎铁律：BLOCK 只给机器能 100% 判定「一定错」的；
     WARN 只给需要人眼的。绝不用 WARN 冒充 BLOCK。
  3. 政策会变。本闸的阈值来自 Amazon Seller Central 公开规范，
     使用前须核对 source 是否为最新版本 —— 本工具不替你背政策变更。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, ROOT)

from engine.engine import Engine, EXIT_CODES  # noqa: E402
from engine import report as R  # noqa: E402

RULESET = 'ecommerce'
VERSION = '0.1.1'

# 三条「上架硬阈值」—— 卖家最常踩、也最容易自动化的三条。
# 这里只做展示，判定逻辑在规则集里（AMZ-TITLE-LEN / AMZ-BULLET-TOTAL / AMZ-TITLE-BANNED）
HARD = [
    ('AMZ-TITLE-LEN', '标题字符数：美国站 ≤75、欧洲站 ≤200'),
    ('AMZ-BULLET-TOTAL', '五点描述总字节 ≤1000'),
    ('AMZ-TITLE-BANNED', '标题禁词（促销语/榜单位/表情符号）'),
]


def _verdict(rep):
    """把引擎报告压成一句人话。不新增判定，只重述。"""
    if rep is None or isinstance(rep, int):
        return '引擎故障，未出判定', EXIT_CODES['error']
    c = rep.get('counts') or {}
    if c.get('ERROR'):
        return f"规则集出错了（ERROR {c['ERROR']}），这不是内容问题", EXIT_CODES['error']
    if c.get('BLOCK'):
        return f"拦下：{c['BLOCK']} 项硬伤必须修完才能上架", EXIT_CODES['block']
    if c.get('WARN'):
        return f"放行（带 caution）：{c['WARN']} 项需人眼确认", EXIT_CODES['warn']
    return '放行：未检出硬伤', EXIT_CODES['clean']


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog='amz_gate',
        description='Amazon listing 出口闸 —— 上架前拦住坏 listing')
    ap.add_argument('target', help='listing 文件（.json / .md / .html）')
    ap.add_argument('--format', default='text',
                    choices=['text', 'json', 'sarif', 'junit'])
    ap.add_argument('--sarif', action='store_true',
                    help='简写：输出 SARIF（GitHub Code Scanning 直接消费）')
    args = ap.parse_args(argv)

    fmt = 'sarif' if args.sarif else args.format

    if not os.path.exists(args.target):
        print(f'✗ 文件不存在: {args.target}', file=sys.stderr)
        return EXIT_CODES['error']

    rs_dir = os.path.join(ROOT, 'rulesets', RULESET)
    if not os.path.isdir(rs_dir):
        print(f'✗ 规则集缺失: {rs_dir}', file=sys.stderr)
        return EXIT_CODES['error']

    rep = Engine(rs_dir, RULESET, args.target).run()
    if isinstance(rep, int):
        return rep

    if fmt == 'text':
        print(f'\n{"=" * 74}')
        print(f'amz_gate v{VERSION} · Amazon listing 出口闸')
        print(f"目标：{rep.get('target')}")
        print('=' * 74)
        print('上架硬阈值（判定逻辑在规则集内，此处只列）：')
        for rid, desc in HARD:
            print(f'  · {rid:18} {desc}')
        print('-' * 74)
        print(R.RENDERERS['text'](rep))
    else:
        print(R.RENDERERS[fmt](rep))

    msg, code = _verdict(rep)
    print(f'\n结论：{msg}   [exit={code}]')
    return code


if __name__ == '__main__':
    sys.exit(main())
