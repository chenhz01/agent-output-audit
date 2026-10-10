# verify_gate 测试夹具

验证引擎「独立复核闸」（发现者≠验证者，v2.0.0）：
- LIAR 规则声称第 999 行有违规（假证据）→ 应被降为 NEEDS_VALIDATION
- HONEST 规则声称第 2 行有 'TBD'（真证据，target.md 第 2 行确有）→ 应保持 FAIL

运行：
    python -c "import sys; sys.path.insert(0,'.'); from engine.engine import Engine; \
rep = Engine('tests/verify_gate','verify_gate','tests/verify_gate/target.md').run(); \
print([(r.rule.id, r.effective_status) for r in rep['results']])"
期望输出：[('LIAR', 'NEEDS_VALIDATION'), ('HONEST', 'FAIL')]
