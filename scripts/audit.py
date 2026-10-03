#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
音乐发行前合规体检器 v1.0
==========================
定位：只做**确定性政策/元数据/清单**体检，不碰音频识别、不下侵权判定。

v1.0.1 变更（两项 bug 均由夹具回归抓出，见 SKILL.md 版本记录）：
  ① 句长序列相似度：原把 list str() 后比 SequenceMatcher（度量的是 "[5, 5, 4" 字面量），
     结果为假值；改为直接序列比对。
  ② E-001 告警方向：原把「字级重合率低」当风险，实为「高」才是；改双阈值 high/low。

设计红线（不可越）：
  1. 每条规则必须来自 policy JSON（带 source + enabled），代码里不硬编码政策。
     —— 政策会过期，护城河是「版本化维护表」，不是规则本身。
  2. 只报能写成 if 的确定性问题。需要模型判断的一律不做：
     歌词实质性相似判定 / 音频 AI 检测 / 文案夸大宣传 / 医疗符合指南 / 合同商业合理性。
  3. E 组（歌词）只输出**客观特征**并强制附「是否侵权需人工判断」声明。

零依赖（stdlib only）。只读输入，不改任何外部系统。
退出码：0=通过  1=有 BLOCK  2=只有 WARN
"""
import json
import os
import sys
import re
import difflib

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_POLICY = os.path.join(HERE, '..', 'data', 'policy_2026-10-04.json')

ISRC_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{3}\d{2}[\dA-Z]{5}$')
UPC_RE = re.compile(r'^\d{12}$')


# ---------- 规则实现 ----------

def check_explicit_ai_label(track, rule, ctx):
    """A-001 中国：显式标识"""
    if ctx.get('ai_generated') is not True:
        return ('SKIP', '非 AI 生成内容，本规则不适用')
    if track.get('metadata', {}).get('explicit_ai_label') is True:
        return ('PASS', '已声明显式标识')
    return ('FAIL', '缺显式 AI 标识（中国境内发布强制）')


def check_implicit_metadata_ai_flag(track, rule, ctx):
    """A-002 中国：隐式元数据标识（与显式构成双标识）"""
    if ctx.get('ai_generated') is not True:
        return ('SKIP', '非 AI 生成内容，本规则不适用')
    if track.get('metadata', {}).get('implicit_ai_flag') is True:
        return ('PASS', '元数据已写入隐式标识')
    return ('FAIL', '缺隐式标识（显式+隐式须双标识，缺一即违规）')


def check_video_overlay_min_ratio(track, rule, ctx):
    """A-003 视频文字提示 ≥ 画面最短边 5%"""
    if ctx.get('ai_generated') is not True or track.get('type') != 'video':
        return ('SKIP', '非 AI 视频，不适用')
    ratio = track.get('video', {}).get('overlay_height_ratio')
    need = rule.get('params', {}).get('min_ratio', 0.05)
    if ratio is None:
        return ('FAIL', '未提供 overlay_height_ratio，无法核验 5%% 门槛')
    if ratio >= need:
        return ('PASS', f'提示高度比 {ratio:.1%} ≥ {need:.0%}')
    return ('FAIL', f'提示高度比 {ratio:.1%} < {need:.0%}')


def check_video_overlay_min_seconds(track, rule, ctx):
    """A-004 视频文字提示持续 ≥ 2 秒"""
    if ctx.get('ai_generated') is not True or track.get('type') != 'video':
        return ('SKIP', '非 AI 视频，不适用')
    secs = track.get('video', {}).get('overlay_seconds')
    need = rule.get('params', {}).get('min_seconds', 2.0)
    if secs is None:
        return ('FAIL', '未提供 overlay_seconds，无法核验 2 秒门槛')
    if secs >= need:
        return ('PASS', f'持续 {secs}s ≥ {need}s')
    return ('FAIL', f'持续 {secs}s < {need}s')


def check_eu_ai_disclosure(track, rule, ctx):
    """A-005 欧盟 AI Act Art.50(2) 主动披露"""
    if 'EU' not in ctx.get('target_regions', []):
        return ('SKIP', '未面向欧盟发布，不适用')
    if ctx.get('ai_generated') is not True:
        return ('SKIP', '非 AI 生成内容，不适用')
    if track.get('metadata', {}).get('eu_ai_disclosed') is True:
        return ('PASS', '已主动披露')
    return ('FAIL', '面向欧盟的 AI 生成内容须主动披露（AI Act Art.50(2)）')


def check_distributor_policy(track, rule, ctx):
    """B-001 发行商 AI 政策二元判定"""
    dist = ctx.get('distributor')
    if not dist:
        return ('WARN', '未指定目标发行商，无法判定')
    table = ctx['policy'].get('distributors', {})
    d = table.get(dist)
    if not d or not d.get('enabled', True):
        return ('WARN', f'政策表未收录发行商 {dist}，无法判定（请补 data/policy 表）')
    if ctx.get('ai_generated') is not True:
        return ('PASS', f'非 AI 生成，{d.get("display")} 普通流程')

    mode = d.get('ai_generated')
    md = track.get('metadata', {})

    if mode == 'reject':
        return ('FAIL', f'{d["display"]} 不接收 AI 生成内容 —— 本曲不可在该平台发行')
    if mode == 'conditional':
        if md.get('licensed_dataset_confirmed') is True:
            return ('PASS', f'{d["display"]} 需完全获许可数据集，已确认')
        return ('FAIL', f'{d["display"]} 要求底层模型使用完全获许可数据集，未确认')
    if mode == 'declare':
        if md.get(d.get('declaration_field', 'ai_declaration')):
            return ('PASS', f'{d["display"]} 要求声明，已填写')
        return ('FAIL', f'{d["display"]} 要求创作者主动声明 AI 成分，未填写')
    if mode == 'credit':
        credits = md.get('ai_credits') or {}
        need = d.get('credit_fields', [])
        missing = [f for f in need if not credits.get(f)]
        if missing:
            return ('FAIL', f'{d["display"]} 需分项标注 AI Credits，缺：{", ".join(missing)}')
        return ('PASS', f'{d["display"]} AI Credits 分项齐全')
    return ('WARN', f'未识别的政策模式：{mode}')


def check_rights_holder_realname(track, rule, ctx):
    """C-001 词曲/演唱/制作人实名"""
    md = track.get('metadata', {})
    missing = []
    for field, label in (('composer', '作曲'), ('lyricist', '作词'),
                         ('performer', '演唱'), ('producer', '制作人')):
        if not md.get(field):
            missing.append(label)
    if missing:
        return ('FAIL', f'缺实名：{", ".join(missing)}')
    return ('PASS', '词曲/演唱/制作人均已实名')


def check_isrc_upc_present(track, rule, ctx):
    """C-002 ISRC / UPC 存在且格式合法"""
    md = track.get('metadata', {})
    isrc, upc = md.get('isrc'), md.get('upc')
    if not isrc:
        return ('FAIL', '缺 ISRC（录音编码）')
    if not ISRC_RE.match(isrc.upper()):
        return ('FAIL', f'ISRC 格式非法：{isrc}')
    if not upc:
        return ('WARN', '缺 UPC（发行编码）—— 自发行场景可暂缺')
    if not UPC_RE.match(upc):
        return ('FAIL', f'UPC 格式非法：{upc}')
    return ('PASS', f'ISRC {isrc} / UPC {upc} 格式合法')


def check_split_sum_normalized(track, rule, ctx):
    """C-003 词曲分成归一"""
    splits = track.get('metadata', {}).get('splits') or []
    if not splits:
        return ('WARN', '未提供分成比例，无法核验归一')
    p = rule.get('params', {})
    total = sum(float(s.get('percent', 0)) for s in splits)
    if abs(total - p.get('expected_sum', 100.0)) <= p.get('tolerance', 0.01):
        return ('PASS', f'分成合计 {total:g}%')
    return ('FAIL', f'分成合计 {total:g}%，应归一到 {p.get("expected_sum", 100):g}%')


def check_master_rights_declared(track, rule, ctx):
    """C-004 母带权利人明确"""
    v = track.get('metadata', {}).get('master_rights')
    if not v:
        return ('FAIL', '母带权利人未声明（自录/他人母带必须写明，混用为侵权高发点）')
    return ('PASS', f'母带权利人：{v}')


def check_sample_voice_license(track, rule, ctx):
    """C-005 采样/声线/音色克隆授权"""
    lic = track.get('metadata', {}).get('licenses') or {}
    needs = []
    if track.get('metadata', {}).get('uses_samples'):
        if not lic.get('sample'):
            needs.append('采样授权')
    if track.get('metadata', {}).get('uses_voice_clone'):
        if not lic.get('voice'):
            needs.append('声线/音色克隆授权')
    if needs:
        return ('FAIL', f'缺授权书：{", ".join(needs)}')
    return ('PASS', '无需额外授权或已齐备')


def check_ai_usage_four_elements(track, rule, ctx):
    """D-001 AI 使用说明四要素（本工具的差异点）"""
    if ctx.get('ai_generated') is not True:
        return ('SKIP', '非 AI 生成内容，不适用')
    usage = track.get('metadata', {}).get('ai_usage') or {}
    need = rule.get('params', {}).get('elements', [])
    labels = {'tool': '工具名', 'version': '版本',
              'stage': '参与环节', 'input_source': '输入来源'}
    missing = [labels.get(e, e) for e in need if not usage.get(e)]
    if missing:
        return ('WARN', f'AI 使用说明缺要素：{", ".join(missing)}'
                         f'（多数人只写「AI 生成」，补全才能说清责任边界）')
    return ('PASS', f'四要素齐全：{usage.get("tool")} {usage.get("version")} / '
                    f'{usage.get("stage")} / 输入：{usage.get("input_source")}')


def _split_lyrics(lyrics):
    """按段落切分，每段取非空行"""
    paras, cur = [], []
    for line in (lyrics or '').splitlines():
        s = line.strip()
        if not s:
            if cur:
                paras.append(cur)
                cur = []
            continue
        cur.append(s)
    if cur:
        paras.append(cur)
    return paras


def check_lyrics_objective_features(track, rule, ctx):
    """
    E-001 歌词抄袭客观特征提取
    ⛔ 只输出客观特征，绝不下「侵权/不侵权」结论。
    """
    target = track.get('lyrics')
    ref = ctx.get('reference_lyrics')
    if not target or not ref:
        return ('SKIP', '未提供待检歌词或对照歌词，跳过')

    p = rule.get('params', {})
    n = p.get('ngram', 4)

    t_paras, r_paras = _split_lyrics(target), _split_lyrics(ref)
    t_flat = ''.join(''.join(x) for x in t_paras)
    r_flat = ''.join(''.join(x) for x in r_paras)

    # 1) 字级重合率
    char_ratio = difflib.SequenceMatcher(None, t_flat, r_flat).ratio()

    # 2) 段落结构向量（句数序列 + 每句字数序列）
    #    v1.0.1 修正：原实现把列表 str() 掉再比 SequenceMatcher —— 那是字符串比对，
    #    度量的是 "[5, 5, 4" 这类字面量，得到的相似度是假的。必须直接比序列。
    t_struct = [len(p_) for p_ in t_paras]
    r_struct = [len(p_) for p_ in r_paras]
    t_sent = [len(s) for p_ in t_paras for s in p_]
    r_sent = [len(s) for p_ in r_paras for s in p_]
    struct_sim = difflib.SequenceMatcher(None, t_sent, r_sent).ratio()
    para_sim = difflib.SequenceMatcher(None, t_struct, r_struct).ratio()

    # 3) 押韵表（取每句末字归类，中文近似）
    t_rhyme = [s[-1] for p_ in t_paras for s in p_ if s]
    r_rhyme = [s[-1] for p_ in r_paras for s in p_ if s]
    rhyme_sim = difflib.SequenceMatcher(None, ''.join(t_rhyme), ''.join(r_rhyme)).ratio()

    # 4) 连续相同片段（n-gram 重合）
    t_ng = {t_flat[i:i + n] for i in range(max(0, len(t_flat) - n + 1))}
    r_ng = {r_flat[i:i + n] for i in range(max(0, len(r_flat) - n + 1))}
    overlap = t_ng & r_ng
    ngram_ratio = len(overlap) / max(1, len(t_ng))

    # 5) 独立起句
    t_first = t_paras[0][0][:8] if t_paras and t_paras[0] else ''
    r_first = r_paras[0][0][:8] if r_paras and r_paras[0] else ''
    first_same = bool(t_first) and t_first == r_first

    feats = [
        f'字级重合率 {char_ratio:.1%}',
        f'句长序列相似 {struct_sim:.1%}',
        f'段落句数结构相似 {para_sim:.1%}',
        f'押韵表相似 {rhyme_sim:.1%}',
        f'{n}-gram 重合 {ngram_ratio:.1%}'
        + (f'（重合片段：{"、".join(sorted(overlap)[:5])}）' if overlap else ''),
        f'起句比对：{t_first!r} vs {r_first!r} → {"相同" if first_same else "不同"}',
    ]
    ctx.setdefault('features', []).append({
        'rule': 'E-001',
        'char_ratio': round(char_ratio, 4),
        'struct_sim': round(struct_sim, 4),
        'para_sim': round(para_sim, 4),
        'rhyme_sim': round(rhyme_sim, 4),
        'ngram_ratio': round(ngram_ratio, 4),
        'first_line_same': first_same,
    })

    detail = '；'.join(feats)
    need = []
    # v1.0.1 修正：原实现写反了方向（把「重合率低」当风险）。
    # 风险方向是【高】——字级重合越高越可能构成接触+实质性相似。
    hi_char = p.get('warn_char_ratio_high', 0.45)
    lo_char = p.get('warn_char_ratio_low', 0.10)
    if char_ratio >= hi_char:
        need.append(f'字级重合 {char_ratio:.1%} 偏高（阈值 {hi_char:.0%}）')
    elif char_ratio < lo_char:
        need.append(f'字级重合仅 {char_ratio:.1%}（低于 {lo_char:.0%}，仅结构/韵脚相似——'
                    f'这正是「新套马杆」案的特征）')
    if p.get('warn_structure_match') and struct_sim >= 0.9:
        need.append(f'句长序列高度相似（{struct_sim:.1%}）—— 结构相似是侵权判定的重要因素')
    if p.get('warn_structure_match') and para_sim >= 0.9:
        need.append(f'段落句数结构高度相似（{para_sim:.1%}）')
    if ngram_ratio > 0:
        need.append(f'存在 {n} 字以上连续重合片段')

    if need:
        return ('WARN',
                detail + ' ｜ 触发：' + '；'.join(need) +
                ' ｜ ⛔ 是否构成侵权需人工/法律判断，本工具不做此结论')
    return ('PASS', detail + ' ｜ 未见显著客观特征重合（仍不构成侵权认定）')


CHECKERS = {
    'explicit_ai_label': check_explicit_ai_label,
    'implicit_metadata_ai_flag': check_implicit_metadata_ai_flag,
    'video_overlay_min_ratio': check_video_overlay_min_ratio,
    'video_overlay_min_seconds': check_video_overlay_min_seconds,
    'eu_ai_disclosure': check_eu_ai_disclosure,
    'distributor_policy': check_distributor_policy,
    'rights_holder_realname': check_rights_holder_realname,
    'isrc_upc_present': check_isrc_upc_present,
    'split_sum_normalized': check_split_sum_normalized,
    'master_rights_declared': check_master_rights_declared,
    'sample_voice_license': check_sample_voice_license,
    'ai_usage_four_elements': check_ai_usage_four_elements,
    'lyrics_objective_features': check_lyrics_objective_features,
}


# ---------- 主流程 ----------

def audit(track, policy, ctx=None):
    ctx = dict(ctx or {})
    ctx['policy'] = policy
    ctx.setdefault('features', [])
    results = []
    for rid, rule in policy.get('rules', {}).items():
        if not rule.get('enabled', True):
            results.append((rid, rule, 'SKIP', '规则已停用（enabled=false）'))
            continue
        fn = CHECKERS.get(rule.get('check'))
        if not fn:
            results.append((rid, rule, 'WARN', f'未实现的检查器：{rule.get("check")}'))
            continue
        try:
            status, detail = fn(track, rule, ctx)
        except Exception as e:
            status, detail = 'WARN', f'检查器异常：{type(e).__name__}: {e}'
        results.append((rid, rule, status, detail))
    return results, ctx


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("用法: audit.py <track.json> [--policy policy.json]")
        print("退出码: 0=通过 1=有BLOCK 2=只有WARN")
        return 2
    track_path = sys.argv[1]
    policy_path = DEFAULT_POLICY
    if '--policy' in sys.argv:
        policy_path = sys.argv[sys.argv.index('--policy') + 1]

    with open(policy_path, encoding='utf-8') as f:
        policy = json.load(f)
    with open(track_path, encoding='utf-8') as f:
        track = json.load(f)

    results, ctx = audit(track, policy, track.get('_context', {}))

    print('=' * 70)
    print(f"音乐发行前合规体检 · 政策版本 {policy['policy_version']}")
    print(f"曲目：{track.get('title', '(未命名)')} ｜ 发行商：{ctx.get('distributor', '(未指定)')}")
    print('=' * 70)
    blocks = warns = passes = skips = 0
    for rid, rule, status, detail in results:
        icon = {'FAIL': '✗', 'WARN': '⚠', 'PASS': '✓', 'SKIP': '–'}[status]
        line = f"{icon} [{rid}] {rule['desc']}"
        print(line)
        print(f"      → {detail}")
        if status == 'FAIL':
            blocks += 1
        elif status == 'WARN':
            warns += 1
        elif status == 'PASS':
            passes += 1
        else:
            skips += 1
    print('-' * 70)
    print(f"合计 {len(results)} 条：BLOCK {blocks} ｜ WARN {warns} ｜ PASS {passes} ｜ SKIP {skips}")
    print("红线声明：本工具不做音频 AI 识别，不做歌词实质性相似判定，"
          "不输出任何侵权/合规的终局法律结论。")
    if blocks:
        print("结论：不通过（存在 BLOCK），先修再发行。")
        return 1
    if warns:
        print("结论：无 BLOCK，但有 WARN，需人眼确认。")
        return 2
    print("结论：通过。")
    return 0


if __name__ == '__main__':
    sys.exit(main())
