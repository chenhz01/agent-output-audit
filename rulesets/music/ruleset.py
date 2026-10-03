#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
规则集：音乐垂类发行前合规体检
================================
本文件 = 从旧 scripts/audit.py **原样搬运**的业务逻辑，改的只有签名包装
（check_fn(target, rule, ctx)）与规则注册。业务判定一行未改。

业务数据在同目录 policy.json（带 source / enforce_type / needs_pro_review）。
引擎（engine/engine.py）不认识本文件里的任何东西。
"""
import os
import re
import json
import difflib

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, 'policy.json'), encoding='utf-8') as _f:
    POLICY = json.load(_f)

# ---- 从 engine 借 Rule 类型 ----
import sys
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
from engine.engine import Rule, RuleResult  # noqa: E402

ISRC_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{3}\d{2}[\dA-Z]{5}$')
UPC_RE = re.compile(r'^\d{12}$')

_RHYME_GROUPS = {
    'a': '那啊啦他她它沙发花芽拿家啦马骂大他她卡沙查沙',
    'ai': '哀挨唉爱海白莱来灾采该开才带待呆妹太盖埋拜耐寨哉债',
    'ei': '诶杯美得雷飞黑背非给贼泪贝配推谁灰腿妹',
    'ao': '熬凹袄奥好老高告道咬包毛刀涛桥昭绕到保找早操抱草',
    'ou': '欧呕藕够狗口后走投头柔收周够楼偷手口候',
    'an': '岸山看晚帆还弹干团暖兰男言散三安岸半岸眼现段远山间',
    'en': '恩根门生人真分恨珍笨沉喷奔人本很',
    'in': '因音引金心林深今寻近沉阴新民亲',
    'ang': '昂航杭浪光方唱往茫香荡长常样上放唱浪墙强床光',
    'eng': '疼等冷灯曾朋更城成生能疼层等',
    'ing': '英影明听星行轻静领定经京晴停醒镜影形',
    'ong': '风中空红东同中痛拥龙送种充公',
    'i': '一以已起地提西希衣你米比力记意事世里利息起题低',
    'u': '五无屋土出路图苦孤呼去住书如故路步暮',
    'v': '玉雨绿举鱼女书去雨律',
    'ie': '叶夜别写铁切街爷叶接谢',
    'e': '热呢得而哥可河德么的了这热',
    'er': '儿二而耳热',
    'ia': '呀家下夏架价假牙',
    'ua': '花抓瓜跨挂话',
    'uo': '我多火说国过落活坐',
    've': '雪月学越',
    'ui': '水回追灰泪',
    'iu': '六有牛流九留',
    'van': '远圆元全源园愿',
    'ue': '月雪约',
}
RHYME_LOOKUP = {}
for _k, _chars in _RHYME_GROUPS.items():
    for _c in _chars:
        RHYME_LOOKUP.setdefault(_c, _k)

_RHYME_CLASS = {
    'ang': 'ang', 'ao': 'au', 'ai': 'ai', 'ei': 'ei', 'i': 'i',
    'an': 'an', 'en': 'en', 'in': 'in', 'ing': 'ing', 'eng': 'eng',
    'ong': 'ong', 'u': 'u', 'v': 'v', 'ui': 'ei', 'iu': 'iou',
    'ie': 'ie', 'e': 'e', 'er': 'er', 'ia': 'ia', 'ua': 'ua',
    'uo': 'uo', 've': 've', 'ou': 'au', 'a': 'a', 'van': 'van', 'ue': 've',
}


def _md(track):
    return track.get('metadata', {})


# ================= 业务检查器（逻辑原样搬运） =================

def check_user_ai_declaration(track, rule, ctx):
    if ctx.get('ai_generated') is not True:
        return ('SKIP', '非 AI 生成内容，本规则不适用')
    if _md(track).get('user_ai_declaration') is True:
        return ('PASS', '用户已主动声明 AI 生成（第十条义务已履行）')
    return ('FAIL', '未主动声明 AI 生成。注：显式/隐式标识的【添加】义务在服务提供者侧，'
                    '用户侧的法律义务是【主动声明】—— 两者不要混为一谈')


def check_no_malicious_tampering_declaration(track, rule, ctx):
    md = _md(track)
    if ctx.get('ai_generated') is not True:
        return ('SKIP', '非 AI 生成内容，本规则不适用')
    tampering = md.get('label_tampering')
    if tampering is True:
        return ('FAIL', '声明存在标识删除/篡改/伪造/隐匿行为（第十条第二款禁止【恶意】行为）')
    if tampering is False:
        return ('PASS', '已确认未对标识做恶意删除/篡改/伪造/隐匿')
    return ('WARN', '未声明是否存在标识篡改行为。注：法规禁止的是【恶意】篡改；'
                    '同时第九条允许在用户协议明确责任后提供不含显式标识的内容，'
                    '隐式标识（水印/元数据）属鼓励项而非强制 —— 勿把「双标识」当硬性义务')


def check_video_overlay_min_ratio(track, rule, ctx):
    if ctx.get('ai_generated') is not True or track.get('type') != 'video':
        return ('SKIP', '非 AI 视频，不适用')
    ratio = track.get('video', {}).get('overlay_height_ratio')
    need = rule.get('params', {}).get('min_ratio', 0.05)
    if ratio is None:
        return ('WARN', '未提供 overlay_height_ratio，无法核验 5% 门槛（数值为 GB 45438-2025 强制国标要求）')
    if ratio >= need:
        return ('PASS', f'提示高度比 {ratio:.1%} ≥ {need:.0%}')
    return ('WARN', f'提示高度比 {ratio:.1%} < {need:.0%}（低于 GB 45438-2025 第5.4条 f) 建议值）')


def check_video_overlay_min_seconds(track, rule, ctx):
    if ctx.get('ai_generated') is not True or track.get('type') != 'video':
        return ('SKIP', '非 AI 视频，不适用')
    secs = track.get('video', {}).get('overlay_seconds')
    need = rule.get('params', {}).get('min_seconds', 2.0)
    if secs is None:
        return ('WARN', '未提供 overlay_seconds，无法核验 2 秒门槛')
    if secs >= need:
        return ('PASS', f'持续 {secs}s ≥ {need}s')
    return ('WARN', f'持续 {secs}s < {need}s（低于 GB 45438-2025 第5.4条 g) 建议值）')


def check_eu_ai_machine_readable_marking(track, rule, ctx):
    if 'EU' not in ctx.get('target_regions', []):
        return ('SKIP', '未面向欧盟发布，不适用')
    if ctx.get('ai_generated') is not True:
        return ('SKIP', '非 AI 生成内容，不适用')
    if _md(track).get('eu_machine_readable_marking') is True:
        return ('PASS', '所选服务提供者已提供机器可读标记（Art.50(2) 提供者义务，发布者侧只需确认所选工具合规）')
    return ('WARN', '未确认所选 AI 工具是否提供机器可读标记。注：Art.50(2) 的义务主体是'
                    '【AI 系统提供者】，非部署者；2026-08-02 适用，Omnibus 仅将此项对'
                    '2026-08-02 前已投入使用的系统宽限至 2026-12-02')


def check_eu_ai_deployer_disclosure(track, rule, ctx):
    if 'EU' not in ctx.get('target_regions', []):
        return ('SKIP', '未面向欧盟发布，不适用')
    if ctx.get('ai_generated') is not True:
        return ('SKIP', '非 AI 生成内容，不适用')
    md = _md(track)
    if md.get('is_deepfake') is True:
        if md.get('eu_ai_deployer_disclosed') is True:
            return ('PASS', '构成 deepfake，已履行 Art.50(4) 部署者披露义务')
        return ('WARN', '构成 deepfake 但未披露 —— Art.50(4) 部署者披露义务，'
                        '此项无宽限，2026-08-02 已适用')
    if md.get('is_artistic_work') is True:
        if md.get('eu_ai_disclosed_by_appropriate_means') is True:
            return ('PASS', '属艺术作品，已按『不妨碍作品呈现与欣赏的适当方式』披露存在性（Art.50(4) 末句允许）')
        return ('WARN', '属艺术作品但未做任何形式的 AI 存在性披露（Art.50(4) 允许以'
                        '『适当方式』披露，不强制显著标注）')
    return ('SKIP', '既非 deepfake 亦未标记为艺术作品 —— Art.50(4) 部署者披露义务仅针对 deepfake，'
                    '非全部 AI 生成内容')


def check_distributor_policy(track, rule, ctx):
    dist = ctx.get('distributor')
    if not dist:
        return ('WARN', '未指定目标发行商，无法判定')
    d = POLICY.get('distributors', {}).get(dist)
    if not d or not d.get('enabled', True):
        return ('WARN', f'政策表未收录发行商 {dist}，无法判定（请补 policy.json）')
    if ctx.get('ai_generated') is not True:
        return ('PASS', f'非 AI 生成，{d.get("display")} 普通流程')
    mode = d.get('ai_generated')
    md = _md(track)
    if mode == 'reject':
        return ('FAIL', f'{d["display"]} 不接收 AI 生成内容（部分 AI 亦拒），违规可被下架并终止合作')
    if mode == 'conditional':
        if md.get('licensed_dataset_confirmed') is True:
            return ('PASS', f'{d["display"]} 需全链路使用完全获许可数据集，已确认')
        return ('FAIL', f'{d["display"]} 要求【任何环节】使用 AI 都须依赖完全获许可数据集'
                        f'（无「纯 AI 才受限」豁免；合作方：{d.get("named_partner", "—")}）')
    if mode == 'declare':
        field = d.get('declaration_field', 'ai_declaration')
        if md.get(field):
            return ('PASS', f'{d["display"]} 建议主动声明，已填写（注意：无可引用官方条款页，属风险提示级）')
        return ('WARN', f'{d["display"]} 无官方条款页但客服口径建议主动声明 AI 成分，未填写')
    if mode == 'voluntary_credit':
        credits = md.get('ai_credits') or {}
        need = d.get('credit_fields', [])
        missing = [f for f in need if not credits.get(f)]
        if missing:
            return ('INFO', f'{d["display"]} 的 AI credits 为【自愿披露】，未披露不构成违规。'
                            f'如要披露，当前缺：{", ".join(missing)}。注：未标注 ≠ 未使用 AI（官方原文）')
        return ('INFO', f'{d["display"]} AI credits 已按四类分项填写（自愿披露项，推荐做法）')
    return ('WARN', f'未识别的政策模式：{mode}')


def check_author_credit_legal(track, rule, ctx):
    md = _md(track)
    missing = [lab for f, lab in (('composer', '作曲'), ('lyricist', '作词')) if not md.get(f)]
    if missing:
        return ('FAIL', f'缺法定署名：{"、".join(missing)}。著作权法第十条第二款/第十二条'
                        f'规定作者有表明身份、在作品上署名的权利 —— 此为【法律强制】')
    return ('PASS', '作曲/作词署名完整（法律强制项已履行）')


def check_performer_producer_realname_practice(track, rule, ctx):
    md = _md(track)
    missing = [lab for f, lab in (('performer', '演唱者'), ('producer', '制作人')) if not md.get(f)]
    if missing:
        return ('WARN', f'缺：{"、".join(missing)}。⚠️ 此为【商业惯例 / 平台要求】，'
                        f'非法律义务 —— 中国著作权法未设「制作人」法定权利主体')
    return ('PASS', '演唱者/制作人均已填法定全名（惯例项）')


def check_isrc_legal_mandatory(track, rule, ctx):
    isrc = _md(track).get('isrc')
    if not isrc:
        return ('FAIL', '缺 ISRC。⚠️ 此为【法律强制】—— 新出政发〔2011〕19 号规定每一'
                        '可独立使用的录音制品均须分配单独 ISRC。'
                        '注：GB/T 13396-2009 本身是【推荐性】国标，强制力来自该文号')
    if not ISRC_RE.match(isrc.upper()):
        return ('FAIL', f'ISRC 格式非法：{isrc}（应为 12 位：2 字母国别 + 3 登记机构 + 2 年 + 5 序号）')
    return ('PASS', f'ISRC {isrc} 存在且格式合法（法律强制项）')


def check_upc_platform_practice(track, rule, ctx):
    upc = _md(track).get('upc')
    if not upc:
        return ('WARN', '缺 UPC。⚠️ 此为【商业惯例 / DSP 交付必填字段】，'
                        '无中国法律强制依据；但缺失会导致 DSP 拒收或无法进榜')
    if not UPC_RE.match(upc):
        return ('WARN', f'UPC 格式非法：{upc}（应为 GTIN-12，12 位数字）')
    return ('PASS', f'UPC {upc} 格式合法（惯例项）')


def check_split_sum_normalized_practice(track, rule, ctx):
    splits = _md(track).get('splits') or []
    if not splits:
        return ('WARN', '未提供分成比例。⚠️ 此为【商业惯例 + 平台交付强制】，'
                        '著作权法第十四条仅规定「收益应当合理分配」')
    p = rule.get('params', {})
    total = sum(float(s.get('percent', 0)) for s in splits)
    if abs(total - p.get('expected_sum', 100.0)) <= p.get('tolerance', 0.01):
        return ('PASS', f'分成合计 {total:g}%（惯例项已满足）')
    return ('WARN', f'分成合计 {total:g}%，平台交付表单通常要求归一到 '
                    f'{p.get("expected_sum", 100):g}%。注：此为惯例而非法律义务')


def check_master_right_legal(track, rule, ctx):
    v = _md(track).get('master_rights')
    if not v:
        return ('FAIL', '母带权利人未声明。⚠️ 此为【法律强制】—— 著作权法第四十二条/第四十四条：'
                        '被许可人复制发行录音录像制品，应当同时取得著作权人、表演者许可并支付报酬。')
    return ('PASS', f'母带权利人已明确：{v}（法律强制项）')


def check_master_rights_declared_practice(track, rule, ctx):
    v = _md(track).get('master_rights')
    if not v:
        return ('WARN', '未在元数据中声明母带权利人（惯例项，如 CD Baby 条款要求）')
    return ('PASS', f'已在元数据声明母带权利人：{v}（惯例项）')


def check_sample_license_legal(track, rule, ctx):
    if _md(track).get('uses_samples') is not True:
        return ('SKIP', '未使用采样，不适用')
    if (_md(track).get('licenses') or {}).get('sample'):
        return ('PASS', '采样授权已附（著作权法第四十二条第一款/第十六条要求）')
    return ('FAIL', '使用采样但未取得授权。著作权法第四十二条第一款：使用他人作品制作'
                    '录音录像制品，应当取得著作权人许可并支付报酬 —— 此为【法律强制】')


def check_voice_clone_consent_legal(track, rule, ctx):
    if _md(track).get('uses_voice_clone') is not True:
        return ('SKIP', '未使用声线/音色克隆，不适用')
    lic = (_md(track).get('licenses') or {}).get('voice')
    if lic:
        return ('PASS', '声线/音色克隆书面同意已留存（民法典第一千零一十九条禁止未经同意使用他人声音）')
    return ('FAIL', '使用声线/音色克隆但未留存被授权人书面同意。⚠️ 法律依据是【人格权与'
                    '禁止仿冒】—— 民法典第一千零一十八条/第一千零二十三条/第一千零一十九条')


def check_ai_usage_four_elements(track, rule, ctx):
    if ctx.get('ai_generated') is not True:
        return ('SKIP', '非 AI 生成内容，不适用')
    usage = _md(track).get('ai_usage') or {}
    need = rule.get('params', {}).get('elements', [])
    labels = {'tool': '工具名', 'version': '版本',
              'stage': '参与环节', 'input_source': '输入来源'}
    missing = [labels.get(e, e) for e in need if not usage.get(e)]
    if missing:
        return ('WARN', f'AI 使用说明缺要素：{", ".join(missing)}。'
                        f'⚠️ 此为【本项目自定义披露字段】，非合规要求')
    return ('PASS', f'四要素齐全：{usage.get("tool")} {usage.get("version")} / '
                    f'{usage.get("stage")} / 输入：{usage.get("input_source")}')


def check_lyrics_legal_standard_notice(track, rule, ctx):
    return ('INFO', '认定标准：接触 + 实质性相似。二者缺一不构成剽窃。'
                    '本工具只提取客观特征，⛔ 不下侵权结论')


def check_eight_measure_not_safe_harbor(track, rule, ctx):
    return ('INFO', '⚠️ 「八小节 / 四句」是司法实践的【经验参考线，不构成免责安全线】—— '
                    '即使相似部分未达八小节、或占比不大，只要足以使听者感知来源于'
                    '特定作品，仍可能构成实质性相似')


def _split_lyrics(lyrics):
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


def _rhyme_of(ch):
    f = RHYME_LOOKUP.get(ch)
    if not f:
        return None
    return _RHYME_CLASS.get(f, f)


def _rhyme_profile(sentences):
    classes, total = [], 0
    for s in sentences:
        if not s:
            continue
        total += 1
        c = _rhyme_of(s[-1])
        if c:
            classes.append(c)
    return classes, (len(classes) / total if total else 0.0)


def check_lyrics_objective_features(track, rule, ctx):
    target = track.get('lyrics')
    ref = ctx.get('reference_lyrics')
    if not target or not ref:
        return ('SKIP', '未提供待检歌词或对照歌词，跳过')
    p = rule.get('params', {})
    n = p.get('ngram', 4)
    t_paras, r_paras = _split_lyrics(target), _split_lyrics(ref)
    t_flat = ''.join(''.join(x) for x in t_paras)
    r_flat = ''.join(''.join(x) for x in r_paras)
    char_ratio = difflib.SequenceMatcher(None, t_flat, r_flat).ratio()
    t_sent = [len(s) for x in t_paras for s in x]
    r_sent = [len(s) for x in r_paras for s in x]
    struct_sim = difflib.SequenceMatcher(None, t_sent, r_sent).ratio()
    t_struct = [len(x) for x in t_paras]
    r_struct = [len(x) for x in r_paras]
    para_sim = difflib.SequenceMatcher(None, t_struct, r_struct).ratio()
    t_sentences = [s for x in t_paras for s in x if s]
    r_sentences = [s for x in r_paras for s in x if s]
    rhyme_char_sim = difflib.SequenceMatcher(
        None, ''.join(s[-1] for s in t_sentences),
        ''.join(s[-1] for s in r_sentences)).ratio()
    t_rhyme, t_cov = _rhyme_profile(t_sentences)
    r_rhyme, r_cov = _rhyme_profile(r_sentences)
    rhyme_sim = (difflib.SequenceMatcher(None, ''.join(t_rhyme),
                                         ''.join(r_rhyme)).ratio()
                 if (t_rhyme and r_rhyme) else 0.0)
    cov_min = min(t_cov, r_cov)
    t_ng = {t_flat[i:i + n] for i in range(max(0, len(t_flat) - n + 1))}
    r_ng = {r_flat[i:i + n] for i in range(max(0, len(r_flat) - n + 1))}
    overlap = t_ng & r_ng
    ngram_ratio = len(overlap) / max(1, len(t_ng))
    t_first = t_paras[0][0][:8] if t_paras and t_paras[0] else ''
    r_first = r_paras[0][0][:8] if r_paras and r_paras[0] else ''
    first_same = bool(t_first) and t_first == r_first

    feats = [
        f'字级重合率 {char_ratio:.1%}',
        f'句长序列相似 {struct_sim:.1%}',
        f'段落句数结构相似 {para_sim:.1%}',
        f'韵脚相似（韵母归一） {rhyme_sim:.1%}  ← 判例采信要点（覆盖率 {cov_min:.0%}）',
        f'　韵脚字面相似（仅末字） {rhyme_char_sim:.1%}  ← 对照用',
        f'{n}-gram 重合 {ngram_ratio:.1%}',
        f'起句比对：{t_first!r} vs {r_first!r} → {"相同" if first_same else "不同"}',
    ]
    need = []
    hi = p.get('warn_char_ratio_high', 0.45)
    lo = p.get('warn_char_ratio_low', 0.10)
    if char_ratio >= hi:
        need.append(f'字级重合 {char_ratio:.1%} 偏高（阈值 {hi:.0%}）')
    elif char_ratio < lo:
        need.append(f'字级重合仅 {char_ratio:.1%}（低于 {lo:.0%}）')
    if struct_sim >= 0.9:
        need.append(f'句长序列高度相似（{struct_sim:.1%}）')
    if para_sim >= 0.9:
        need.append(f'段落句数结构高度相似（{para_sim:.1%}）')
    if cov_min >= 0.6:
        if rhyme_sim >= 0.9:
            need.append(f'韵脚韵类高度一致（{rhyme_sim:.1%}，覆盖率 {cov_min:.0%}）')
        elif rhyme_sim >= 0.7:
            need.append(f'韵脚韵类较一致（{rhyme_sim:.1%}，覆盖率 {cov_min:.0%}）')
    else:
        need.append(f'韵脚指标因识别覆盖率仅 {cov_min:.0%} 暂不采信（需补映射表）')
    if ngram_ratio > 0:
        need.append(f'存在 {n} 字以上连续重合片段')
    if first_same:
        need.append('起句完全相同')
    detail = '；'.join(feats)
    if need:
        return ('WARN', detail + ' ｜ 触发：' + '；'.join(need) +
                ' ｜ ⛔ 是否构成侵权需人工/法律判断。判例提示：(2014)穗中法知民终字第289号'
                '法院采信的是【结构+句式+起句+韵脚全面雷同】')
    return ('PASS', detail + ' ｜ 未见显著客观特征重合（仍不构成侵权认定）')


# ================= 规则注册 =================

CHECKERS = {
    'user_ai_declaration': check_user_ai_declaration,
    'no_malicious_tampering_declaration': check_no_malicious_tampering_declaration,
    'video_overlay_min_ratio': check_video_overlay_min_ratio,
    'video_overlay_min_seconds': check_video_overlay_min_seconds,
    'eu_ai_machine_readable_marking': check_eu_ai_machine_readable_marking,
    'eu_ai_deployer_disclosure': check_eu_ai_deployer_disclosure,
    'distributor_policy': check_distributor_policy,
    'author_credit_legal': check_author_credit_legal,
    'performer_producer_realname_practice': check_performer_producer_realname_practice,
    'isrc_legal_mandatory': check_isrc_legal_mandatory,
    'upc_platform_practice': check_upc_platform_practice,
    'split_sum_normalized_practice': check_split_sum_normalized_practice,
    'master_right_legal': check_master_right_legal,
    'master_rights_declared_practice': check_master_rights_declared_practice,
    'sample_license_legal': check_sample_license_legal,
    'voice_clone_consent_legal': check_voice_clone_consent_legal,
    'ai_usage_four_elements': check_ai_usage_four_elements,
    'lyrics_legal_standard_notice': check_lyrics_legal_standard_notice,
    'eight_measure_not_safe_harbor': check_eight_measure_not_safe_harbor,
    'lyrics_objective_features': check_lyrics_objective_features,
}


class RuleSet:
    name = 'music'
    display = '音乐发行前合规体检'
    version = POLICY.get('policy_version', '0')

    @classmethod
    def load(cls):
        rules = []
        for rid, rd in POLICY.get('rules', {}).items():
            fn = CHECKERS.get(rd.get('check'))
            if not fn:
                continue
            meta = {k: v for k, v in rd.items()
                    if k not in ('check', 'severity', 'desc')}
            meta['group'] = rd.get('group')
            rules.append(Rule(rid, rd.get('desc', ''),
                              rd.get('severity', 'WARN'), fn, **meta))
        return rules

    @classmethod
    def validate(cls):
        """返回 check 字段无法解析的规则 ID 列表（空=全部对得上）"""
        return [rid for rid, rd in POLICY.get('rules', {}).items()
                if rd.get('check') not in CHECKERS]

    @classmethod
    def meta(cls):
        return {
            'display': cls.display,
            'enforce_types': POLICY.get('enforce_types', {}),
            'red_lines': POLICY.get('red_lines', []),
            'needs_pro_review': POLICY.get('needs_pro_review', []),
            'review_metadata': POLICY.get('review_metadata', {}),
        }
