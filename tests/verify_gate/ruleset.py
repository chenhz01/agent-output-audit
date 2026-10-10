import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.engine import Rule
POLICY = {'display': '复闸验证', 'rules': {
    'LIAR': {'severity': 'BLOCK', 'desc': '伪造证据的规则', 'check': 'chk_liar'},
    'HONEST': {'severity': 'BLOCK', 'desc': '证据可信的规则', 'check': 'chk_honest'},
}}
def chk_liar(track, rule, ctx):
    ctx['_last_evidence'] = [(999, '原文里不存在的一句')]
    return ('FAIL', '声称第999行有违规')
def chk_honest(track, rule, ctx):
    ctx['_last_evidence'] = [(2, 'TBD')]
    return ('FAIL', '声称第2行有 TBD')
CHECKERS = {k: v for k, v in list(globals().items()) if k.startswith('chk_')}
class RuleSet:
    name = 'rs_test'; display = POLICY['display']; version = 'test'
    @classmethod
    def load(cls):
        return [Rule(rid, rd['desc'], rd['severity'], CHECKERS[rd['check']])
                for rid, rd in POLICY['rules'].items()]
