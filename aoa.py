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
            # list 也要跑 validate：键名不匹配应在列目录时就暴露，
            # 而不是等到 run 时才发现「0 条规则」。
            miss = rs.validate() if hasattr(rs, 'validate') else []
            flag = f'   ⚠ {len(miss)} 条 check 未解析' if miss else ''
            print(f'  {name:14} {getattr(rs, "display", ""):24} '
                  f'{n:3} 条规则  v{getattr(rs, "version", "?")}{flag}')
        except Exception as e:
            print(f'  {name:14} ⚠ 加载失败: {type(e).__name__}: {e}')
    return 0


def _ledger(args, rep):
    """v2.0.0 coverage ledger：跨次运行增量对比。

    只在入口层做（引擎不认识「上次跑过什么」这种时间态）。
    原子写（.tmp + os.replace），与趋势战情室台账同规程。
    返回 (newly_failed, resolved, first_run)。
    """
    import json
    import time
    key = f'{args.ruleset}::{os.path.abspath(args.target)}'
    data = {}
    if args.ledger and os.path.exists(args.ledger):
        try:
            data = json.load(open(args.ledger, encoding='utf-8'))
        except Exception as e:
            print(f'⚠ ledger 文件损坏，按首次运行处理: {e}', file=sys.stderr)
            data = {}
    old = data.get(key, {}).get('verdicts', {})
    new = {r.rule.id: r.effective_status for r in rep['results']}
    newly_failed = sorted(rid for rid, st in new.items()
                          if st == 'FAIL' and old.get(rid) != 'FAIL')
    resolved = sorted(rid for rid, st in old.items()
                      if st == 'FAIL' and new.get(rid) != 'FAIL')
    first_run = not old
    if args.ledger:
        data[key] = {'last_run': time.strftime('%Y-%m-%d %H:%M:%S'),
                     'verdicts': new}
        tmp = args.ledger + '.tmp'
        json.dump(data, open(tmp, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        os.replace(tmp, args.ledger)
    return newly_failed, resolved, first_run


def main():
    ap = argparse.ArgumentParser(prog='aoa', description='Agent 输出体检引擎')
    sub = ap.add_subparsers(dest='cmd')

    sub.add_parser('list', help='列出可用规则集')

    p = sub.add_parser('run', help='执行检查')
    p.add_argument('ruleset')
    p.add_argument('target')
    p.add_argument('--format', default='text',
                   choices=['text', 'json', 'sarif', 'junit'])
    p.add_argument('--ledger', default=None,
                   help='coverage ledger 文件路径（v2.0.0：记录每次运行的'
                        '逐规则判定，下次运行自动对比「新增 FAIL / 已解决」——'
                        '对标 cloudflare 六阶段的 coverage-ledger 思想的最小落地）')

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
        if args.ledger:
            newly, resolved, first = _ledger(args, rep)
            if first:
                print(f'\n📌 ledger：首次记录基线（{len(rep["results"])} 条判定），无对比')
            else:
                parts = []
                if newly:
                    parts.append(f'新增 FAIL {len(newly)} 条（{", ".join(newly)}）')
                if resolved:
                    parts.append(f'已解决 {len(resolved)} 条（{", ".join(resolved)}）')
                print('\n📌 ledger 对比上次运行：'
                      + ('；'.join(parts) if parts else '无变化'))
        return rep['exit_code']

    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
