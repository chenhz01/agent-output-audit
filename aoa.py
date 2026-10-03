#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
agent-output-audit · 统一入口
==============================
用法：
  python aoa.py list
  python aoa.py <ruleset> <target.json> [--format text|json|sarif|junit]

设计：引擎不认识业务；这里只做参数解析与规则集发现。
"""
import os
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from engine.engine import Engine, EXIT_CODES  # noqa: E402
from engine import report as R  # noqa: E402


def cmd_list():
    found = Engine.discover(HERE)
    if not found:
        print('（未发现任何规则集）')
        return 0
    print('可用规则集：')
    for name, path in found:
        try:
            eng = Engine(path, name, None)
            rs = eng._load_ruleset()
            n = len(rs.load())
            print(f'  {name:14} {getattr(rs, "display", ""):24} '
                  f'{n:3} 条规则  v{getattr(rs, "version", "?")}')
        except Exception as e:
            print(f'  {name:14} ⚠ 加载失败: {type(e).__name__}: {e}')
    return 0


def main():
    ap = argparse.ArgumentParser(prog='aoa', description='Agent 输出体检引擎')
    sub = ap.add_subparsers(dest='cmd')

    sub.add_parser('list', help='列出可用规则集')

    p = sub.add_parser('run', help='执行检查')
    p.add_argument('ruleset')
    p.add_argument('target')
    p.add_argument('--format', default='text',
                   choices=['text', 'json', 'sarif', 'junit'])

    args = ap.parse_args()

    if args.cmd == 'list' or args.cmd is None:
        return cmd_list()
    if args.cmd == 'run':
        rs_dir = os.path.join(HERE, 'rulesets', args.ruleset)
        if not os.path.isdir(rs_dir):
            print(f'✗ 未知规则集: {args.ruleset}（用 list 查看）', file=sys.stderr)
            return EXIT_CODES['error']
        rep = Engine(rs_dir, args.ruleset, args.target).run()
        if isinstance(rep, int):
            return rep
        print(R.RENDERERS[args.format](rep))
        return rep['exit_code']

    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
