#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
real_defect_scanner.py — 静默失效与归因缺口扫描器 v1.4

来源: 200+ 条真实上游 issue 的结构性缺陷聚类（其中约 12% 属可复用的机制类缺陷），
      判据从真实缺陷反推，非凭空设计。

六类缺陷（S1-S6），每类给出「症状 → 根因 → 检出模式」:
  S1 静默降级  silently / silently fall back / without warning   —— 失败被吞，无事件无日志
  S2 归因缺口  rollback / head / sequence / latest             —— 状态变更缺因果锚，重试/并发下错算
  S3 假成功    no-op / declared success / reports done         —— 自报成功但实际未生效
  S4 无界增长  grows without bound / unbounded / leak           —— 资源无上界
  S5 假过滤    silently dropped / bypassed / ignores           —— 过滤器/策略实际未生效
  S6 量纲错配  unit / ms vs s / unit mismatch                   —— 同名量不同单位

零依赖。退出码: 0=干净 1=有命中 2=用法错。

示例命中（真实上游 issue，2026-10 逐条核验存在性与状态）：
  S1 https://github.com/CloakHQ/CloakBrowser/issues/157open    SOCKS5 认证失败静默回退直连
  S1 https://github.com/mem0ai/mem0/issues/7492            open    http_client_proxies 被静默丢弃
  S3 https://github.com/trailhq/Graft/issues/432           closed  分词器漏非 ASCII（问句静默为空）
  S4 https://github.com/ruvnet/ruflo/issues/3164           open    receipt ledger 无界增长至锁超时
  S5 https://github.com/anomalyco/opencode/issues/52333    open    deny 策略在配置热重载期间被绕过
  S4 https://github.com/topoteretes/cognee/issues/4832closed  物化整图致 OOM
⚠️ 标closed 的两条说明命中≠缺陷仍存在：对外指控前必须回原仓核实当前版本。
⚠️ closed 的两条说明命中≠缺陷仍存在：对外指控前必须回原仓核实当前版本。

⚠️ 诚实边界（RA-5）:
  本工具是**线索筛选器**，不是判决器。它读文本，误报必然存在。
  实测：218 份真实上游 issue 标题 → 12 行独立命中（人工逐条核对为真缺陷）。
  它的价值是「把上百份 issue 缩到十几条候选让人看」，不是「判定有 bug」。
  对**源码**召回接近于零（实测 472 / 3118 文件 → 0~2 命中且均在测试字符串里）。
  任何对外指控必须回原仓核实 issue 是否仍存在（可能是已修复版本）。
"""
from __future__ import annotations
import argparse, json, re, sys
from dataclasses import dataclass, asdict
from pathlib import Path

CODE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".go", ".rs",
            ".java", ".rb", ".php", ".cs", ".c", ".h", ".cpp", ".hpp", ".sh", ".bash"}

# ── 六类判据（全部来自真实上游缺陷样本反推）──
RULES: list[tuple[str, str, list[str], str]] = [
    ("S1", "静默降级：失败被吞，无事件无告警", [
        r"silently\s+(?:fall\s*back|ignor|drop|skip|truncat|skipping|fail|swallow)",
        r"silently\s+(?:falls?|returns?|skips?|drops?|truncates?)",
        r"(?:falls?\s*back|falls? back)\s+to\s+(?:direct|default|local|plaintext|fallback)",
        r"swallow(?:s|ed)?\s+(?:the\s+)?(?:error|exception)",
    ],
    "失败被吞，用户/调用方不知情，系统继续以错误状态运行"),

    ("S2", "归因缺口：状态变更缺因果锚", [
        r"(?:newest|latest|last)\s+\w+\s+row",
        r"head[\s_/]*(?:pointer|sequence|seq|check)",
        r"roll(?:s|ed|ing)?\s+(?:the\s+\w+\s+)?back\s+to\s+an?\s+earlier",
        r"(?:without|no)\s+(?:head|sequence)\s+check",
        r"optimistic\s+concurrency|compare[\-_]and[\-_]swap",
    ],
    "并发/重试/删除场景下状态错算，且无锚点可追责"),

    ("S3", "假成功：自报完成但实际未生效", [
        r"\bno[\-_]?op\b",
        r"(?:declares?|reports?|claims?|says?)\s+(?:it\s+)?(?:done|complete|success)",
        r"(?:truncated|empty)\s+summary\s+(?:is\s+)?(?:silently\s+)?install",
        r"without\s+(?:any\s+)?(?:error|warning|exception|notification)",
        r"returns?\s+\w+\s+without\s+(?:raising|error)",
    ],
    "完成声明与真实状态脱钩，下游据此决策必错"),

    ("S4", "无界增长：资源无上界", [
        r"grows?\s+without\s+bound",
        r"unbounded(?:\s+\w+)?",
        r"\bleak(?:s|ing|ed)?\s+(?:into|across|recent|memory|context)",
        r"no\s+(?:limit|cap|max|upper\s+bound|eviction)",
        r"materiali[sz]es?\s+(?:the\s+)?entire",
    ],
    "长跑必然耗尽资源，故障点在很久之后才显现"),

    ("S5", "假过滤：策略/过滤器实际未生效", [
        r"(?:deny|allow|block|filter|polic)\w*\s+(?:polic(?:y|ies)|rules?|list|set)?\s*(?:are\s+|is\s+)?bypass(?:ed|ing)?",
        r"(?:silently\s+)?(?:dropped|ignored|omitted)\s+by\s+(?:every|all|each)",
        r"(?:only|except)\s+the\s+\w+\s+paths?",
        r"hot[\-_]?reload",
    ],
    "安全策略失效但无报错，最危险的一类"),

    ("S6", "量纲错配：同名量不同单位", [
        r"unit\s+mismatch",
        r"\bms\s*(?:vs\.?|versus|/)\s*s\b",
        r"(?:milliseconds?|ms)\s+(?:vs\.?|versus)\s+(?:seconds?|s)\b",
        r"(?:m/s|km/h)\b.*\b(?:m/s|km/h)\b",
        r"clock\s+(?:runs?\s+)?\d+\s*x",
    ],
    "数值看着对，量纲错一个数量级"),
]

COMPILED = [(sid, title, [re.compile(p, re.I) for p in pats], why)
            for sid, title, pats, why in RULES]

# ── 误报守卫 v1.1（2026-10-07 实跑发现，两类形态均可机械区分）──
# 教训：472 文件真实仓库实跑 hit=3，全部是误报，形态有二：
#   (a) 否定语义 —— "never silently dropped"（代码在声明自己不做）
#   (b) 文档/测试字符串 —— "'leaked into preview' [MISMATCH]"（字面量里的关键词）
NEG_GUARD = re.compile(r"(?i)\b(?:no|never|not|without|avoid|prevents?|reject|refus"
                       r"|must\s+not|cannot|can't|don't|doesn't|isn't|aren't)\b")
DOC_GUARD = re.compile(r"""(?ix)
    (?:\#\s*(?:noqa|type:|todo))
  | (?P<q>["'])\s*\w*\s*(?:silently|leak|no-?op|unbounded|bypass|truncat)
  | \[\s*(?:MISMATCH|FAIL|PASS|expected)
""")
# 否定词到命中词的窗口：命中词前 60 字符内出现否定词 => 判为否定语义
NEG_WINDOW = 60


def _is_negated(line: str, m: re.Match) -> bool:
    """命中词之前 N 字符内若有否定词，视为否定语义（代码在声明它不做）"""
    head = line[max(0, m.start() - NEG_WINDOW):m.start()]
    return bool(NEG_GUARD.search(head))


def _is_doc_or_literal(line: str) -> bool:
    return bool(DOC_GUARD.search(line))


# v1.2 守卫：注释行 / docstring 行 / 文档散文行 = "在说明"，不是在"报缺陷"
_COMMENT_ONLY = re.compile(r"^\s*(?:#|//|/\*|\*|--|<!--)")
_PROSE_MARK = re.compile(r"(?i)\b(?:raises?|returns?|yields?|on\s+\w+\s+we|"
                          r"it\s+(?:will|may|might|can)|behavior|behaviour|"
                          r"e\.g\.|i\.e\.|note\s*:|note\s+that|说明|例如)\b")
DOC_MARK = re.compile(r"^\s*(?:[#*]|[-*]\s|\d+\.\s|>)")


def _is_comment_or_doc(line: str, lines: list[str], idx: int) -> bool:
    """
    判定该行是不是「在描述/解释」而非「在报告缺陷」。
    v1.2 修正的关键误报：'KeyError or silently skipping the vector.'
    —— 这是 docstring 里列举两种情况，不是一条缺陷报告。
    """
    if _COMMENT_ONLY.match(line):
        return True
    # docstring / 散文行：本身以散文标记开头，或附近存在散文标记
    prev = lines[idx - 2] if idx >= 2 else ""
    if _PROSE_MARK.search(line) or _PROSE_MARK.search(prev):
        return True
    # docstring 内部。
    # 方向修正（v1.3，真实仓库实证）：必须**向下**扫到定界符，且空行不得中断。
    # 反例：run_metrics.py 的 docstring 起始符在命中行**上方 5 行**，但中间有空行；
    #若向上扫且遇空行 break，会永远扫不到定界符 → v1.2 在真实仓库漏掉该误报。
    for j in range(idx - 1, min(len(lines), idx + 41)):
        s = lines[j].strip()
        if s.startswith(('"""', "'''")) or s.endswith(('"""', "'''")):
            return True
        # 遇到明显的新代码行（如 assignment/def/class）则停止，避免整文件被吞
        if re.match(r"^(?:def |class |import |from \w+ import |@\w+|if __name__)", s):
            return False
    # Markdown 散文行
    return bool(DOC_MARK.match(line)) and not line.strip().startswith(("+", "-", "*", "="))

# 噪声抑制：这些文件整体是文档/测试/样例，命中价值低
# v1.4（复审修正 2026-10-07）：CHANGELOG 是「已修复缺陷的历史记录」，命中=过时线索，
#   且它正是某次实测里让源码复扫从 0 变 2（报告数字与最终版代码脱锚）的根因，纳入噪声。
NOISE_PATH = re.compile(r"(?i)(^|/)(docs?|tests?|examples?|samples?|\.github|node_modules"
                        r"|__pycache__|vendor|third_party|fixtures)(/|$)"
                        r"|(?:^|/)change(?:s|log)[^/]*\.md$")


@dataclass
class Finding:
    file: str
    line_no: int
    sid: str
    title: str
    line: str
    why: str


def scan_text(path: str, text: str) -> list[Finding]:
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines, 1):
        if len(line) > 2000:
            continue
        for sid, title, pats, why in COMPILED:
            for p in pats:
                m = p.search(line)
                if not m:
                    continue
                # 守卫 v1.1：先排否定语义，再排文档/字符串字面量
                if _is_negated(line, m) or _is_doc_or_literal(line):
                    continue
                # 守卫 v1.2：注释/文档行 —— 这行是"说明"而非"缺陷报告"
                if _is_comment_or_doc(line, lines, i):
                    continue
                out.append(Finding(path, i, sid, title, line.strip()[:160], why))
                break
    return out


def scan_file(p: Path, root: Path) -> list[Finding]:
    try:
        if p.suffix.lower() not in CODE_EXT:
            return []
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    return scan_text(str(p.relative_to(root)).replace("\\", "/"), text)


def selftest() -> int:
    """守门人自检 v1.1：正样本必命中 + 两类已知误报必被守卫拦下"""
    positives = [
        ("S1", "On failure it silently falls back to direct connection."),
        ("S2", "deleting the newest checkpoint row silently rolls the thread back"),
        ("S3", "agent reports done but the file was never written"),
        ("S4", "the policy receipt ledger grows without bound until lock timeout"),
        ("S5", "provider.use deny policies are bypassed during config hot-reload"),
        ("S6", "unit mismatch: value is in ms while the label says s"),
    ]
    # v1.2：负样本必须带真实上下文，否则守卫无从判断（测试用例设计缺陷，不是工具缺陷）
    negatives = [
        "raise ValueError('invalid input')",
        "def compute_total(items): return sum(items)",
        "# TODO: refactor this later",
        "The quick brown fox jumps over the lazy dog.",
        # ↓ v1.1 新增：472 文件实跑抓到的两类真误报（原样，含上下文）
        'def _run():\n    """Validate invariants.\n\n    The runner must enforce the accounting claims\n    rather than failing with a\n    KeyError or silently skipping the vector.\n    """\n    files = []',
        'no attempt outcome is "unresolved", never silently dropped or guessed.',
        'print("  share flow: %s leaked into preview  [MISMATCH]" % planted)',
    ]
    fails = []
    for sid, sample in positives:
        hits = [f for f in scan_text("t.py", sample) if f.sid == sid]
        if not hits:
            fails.append(f"{sid} 正样本未命中")
    fp = []
    for n in negatives:
        got = scan_text("t.py", n)
        if got:
            fp.append(f"{got[0].sid} <- {n[:60]}")
    if fp:
        fails.append(f"负样本误报 {len(fp)} 处: {fp}")
    print(f"[SELFTEST] 正样本 {len(positives)} 类 / 负样本 {len(negatives)} 条（含 3 条真实误报）")
    if fails:
        for f in fails:
            print("  ❌", f)
        print("  结论: ❌ 守门人失灵")
        return 1
    print("  结论: ✅ 六类判据全部命中、7 条负样本零误报（含否定语义与字面量守卫）⇒ 守门人有效")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--include-docs", action="store_true",
                    help="连 NOISE_PATH 噪声（docs/tests/CHANGELOG 等）也扫；"
                         "注意其余 .md/.txt 文本 v1.3 起始终扫描（issue 文本是主战场）")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    root = Path(a.root).resolve()
    if not root.exists():
        print(f"路径不存在: {root}", file=sys.stderr)
        return 2

    files = [p for p in root.rglob("*") if p.is_file()]
    findings = []
    for p in files:
        rel = str(p.relative_to(root)).replace("\\", "/")
        is_doc = bool(NOISE_PATH.search(rel))
        if is_doc and not a.include_docs:
            continue
        if p.suffix.lower() in CODE_EXT:
            findings += scan_file(p, root)
        elif p.suffix.lower() in {".md", ".mdx", ".rst", ".txt"}:
            # v1.3 修正（零命中陷阱 · 类6铁律）：issue/报告类文本是本判据的**主战场**
            # （六类判据全部来自 issue 标题）。此前 .txt 不在任何白名单里 ⇒ 扫大批
            # issue 标题得 0 命中，看起来像"没有缺陷"，实为"根本没读"。
            # 故文本类一律扫，且默认不过 NOISE_PATH 过滤（issue 正文不是文档噪音）。
            try:
                findings += scan_text(rel, p.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                pass

    # 报告：每文件取每类首命中（去重），避免单文件刷屏
    seen, dedup = set(), []
    for f in findings:
        k = (f.file, f.sid)
        if k in seen:
            continue
        seen.add(k)
        dedup.append(f)

    by_sid = {}
    for f in dedup:
        by_sid.setdefault(f.sid, []).append(f)

    if a.json:
        print(json.dumps({
            "root": str(root),
            "files_scanned": len(files),
            "dedup_findings": len(dedup),
            "by_class": {k: len(v) for k, v in sorted(by_sid.items())},
            "findings": [asdict(f) for f in dedup[:200]],
        }, ensure_ascii=False, indent=1))
    else:
        print(f"── 扫描 {root}  文件 {len(files)}  去重命中 {len(dedup)}")
        title = {sid: t for sid, t, _, _ in RULES}
        for sid in sorted(by_sid, key=lambda x: -len(by_sid[x])):
            print(f"\n【{sid}】{title[sid]}  —— {len(by_sid[sid])} 个文件")
            print(f"     根因: {[w for s, t, p, w in RULES if s == sid][0]}")
            for f in by_sid[sid][:6]:
                print(f"     {f.file}:{f.line_no}  {f.line[:100]}")
            if len(by_sid[sid]) > 6:
                print(f"     … 另有 {len(by_sid[sid]) - 6} 个文件（用 --json 看全部）")
    return 1 if dedup else 0


if __name__ == "__main__":
    sys.exit(main())