#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
音乐发行前合规体检器 v2.0.0
============================
定位：只做**确定性政策/元数据/清单**体检，不碰音频识别、不下侵权判定。

v2.0.0 变更（依据 13 条原文核证结果，commit 见 git log）：
  ① 规则 13→19 条，**每条标注 enforce_type**：法律强制 / 法律标准 / 判例 /
     商业惯例 / 平台技术要求 / 平台公开表态 / 本项目自定义。
     —— 纠正 v1 把【商业惯例】当【法律义务】的系统性错误。
  ② A-001 义务主体纠正：显式/隐式标识添加义务在【服务提供者】，用户侧义务是
     【主动声明】。删去杜撰的「双标识缺一即违规」。
  ③ A-005 拆为 A-005a（Art.50(2) 提供者机器可读标记）/ A-005b（Art.50(4)
     部署者披露，仅限 deepfake，艺术品可退化披露）。
  ④ C 组按「法律强制 vs 商业惯例」拆成 C-001a/b、C-002a/b、C-004a/b、C-005a/b。
  ⑤ B 组：CD Baby 查实官方页（拒收+可下架+可能终止）；TuneCore 补「任何环节用
     AI 均受限」无豁免；网易云降为 platform_statement（无官方条款页）；Spotify
     由「要求」纠正为「自愿」（absence of AI credits 不代表未使用）。
  ⑥ E 组拆 E-001a（法律标准）/ E-001b（八小节非安全线）/ E-001c（判例
     (2014)穗中法知民终字第289号，比对对象为《套马杆》而非「美国儿歌」）。

v1.0.1 保留的两个 bug 修复（由夹具回归抓出）：
  ① 句长序列相似度：不得把 list str() 后比 SequenceMatcher（度量的是字面量）。
  ② E 组告警方向：字级重合【高】才是风险，非【低】。
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

# enforce_type → 展示用（用于输出时提示「这是法律强制还是商业惯例」）
ET_LABEL = {
    'legal_mandatory': '法律强制',
    'legal_standard': '法律标准',
    'case_law': '判例',
    'commercial_practice': '商业惯例',
    'platform_technical': '平台技术要求',
    'platform_statement': '平台公开表态',
    'project_custom': '本项目自定义',
}
ET_ICON = {
    'legal_mandatory': '⚖',
    'legal_standard': '§',
    'case_law': '§',
    'commercial_practice': '◇',
    'platform_technical': '◆',
    'platform_statement': '◇',
    'project_custom': '★',
}


def _md(track):
    return track.get('metadata', {})


# ---------- 中国：AI 标识（义务主体已纠正）----------

def check_user_ai_declaration(track, rule, ctx):
    """A-001《标识办法》第十条：用户发布 AI 内容应当主动声明"""
    if ctx.get('ai_generated') is not True:
        return ('SKIP', '非 AI 生成内容，本规则不适用')
    if _md(track).get('user_ai_declaration') is True:
        return ('PASS', '用户已主动声明 AI 生成（第十条义务已履行）')
    return ('FAIL', '未主动声明 AI 生成。注：显式/隐式标识的【添加】义务在服务提供者侧，'
                    '用户侧的法律义务是【主动声明】—— 两者不要混为一谈')


def check_no_malicious_tampering_declaration(track, rule, ctx):
    """A-002《标识办法》第十条第二款：禁止【恶意】删除篡改伪造隐匿标识
    ⚠️ 纠正 v1 杜撰的「双标识缺一即违规」——第九条明文允许无显式标识的合法情形。"""
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
    """A-003 GB 45438-2025 第5.4条 f)：视频文字提示 ≥ 画面最短边 5%"""
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
    """A-004 GB 45438-2025 第5.4条 g)：持续 ≥ 2 秒"""
    if ctx.get('ai_generated') is not True or track.get('type') != 'video':
        return ('SKIP', '非 AI 视频，不适用')
    secs = track.get('video', {}).get('overlay_seconds')
    need = rule.get('params', {}).get('min_seconds', 2.0)
    if secs is None:
        return ('WARN', '未提供 overlay_seconds，无法核验 2 秒门槛')
    if secs >= need:
        return ('PASS', f'持续 {secs}s ≥ {need}s')
    return ('WARN', f'持续 {secs}s < {need}s（低于 GB 45438-2025 第5.4条 g) 建议值）')


# ---------- 欧盟：Art.50 拆两条 ----------

def check_eu_ai_machine_readable_marking(track, rule, ctx):
    """A-005a Art.50(2)：提供者义务，机器可读标记。⚠️ 不是「主动披露」。"""
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
    """A-005b Art.50(4)：部署者披露义务，仅限 deepfake；艺术品可退化披露"""
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


# ---------- 发行商 ----------

def check_distributor_policy(track, rule, ctx):
    """B-001 发行商 AI 政策判定（各平台定性与强度均已按核证结果纠正）"""
    dist = ctx.get('distributor')
    if not dist:
        return ('WARN', '未指定目标发行商，无法判定')
    d = ctx['policy'].get('distributors', {}).get(dist)
    if not d or not d.get('enabled', True):
        return ('WARN', f'政策表未收录发行商 {dist}，无法判定（请补 data/policy 表）')
    if ctx.get('ai_generated') is not True:
        return ('PASS', f'非 AI 生成，{d.get("display")} 普通流程')

    mode = d.get('ai_generated')
    md = _md(track)

    if mode == 'reject':
        extra = '，且违规可被下架并终止合作' if d.get('no_partial_exemption') else ''
        return ('FAIL', f'{d["display"]} 不接收 AI 生成内容（部分 AI 亦拒）{extra}')
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
                            f'如要披露，当前缺：{", ".join(missing)}。'
                            f'注：未标注 ≠ 未使用 AI（官方原文）')
        return ('INFO', f'{d["display"]} AI credits 已按四类分项填写（自愿披露项，推荐做法）')
    return ('WARN', f'未识别的政策模式：{mode}')


# ---------- C 组：法律强制 vs 商业惯例 分开 ----------

def check_author_credit_legal(track, rule, ctx):
    """C-001a【法律强制】词曲作者署名权（著作权法第十条/第十二条）"""
    md = _md(track)
    missing = [lab for f, lab in (('composer', '作曲'), ('lyricist', '作词'))
               if not md.get(f)]
    if missing:
        return ('FAIL', f'缺法定署名：{"、".join(missing)}。著作权法第十条第二款/第十二条'
                        f'规定作者有表明身份、在作品上署名的权利 —— 此为【法律强制】')
    return ('PASS', '作曲/作词署名完整（法律强制项已履行）')


def check_performer_producer_realname_practice(track, rule, ctx):
    """C-001b【商业惯例】表演者/制作人填法定全名 —— 非法律义务"""
    md = _md(track)
    missing = [lab for f, lab in (('performer', '演唱者'), ('producer', '制作人'))
               if not md.get(f)]
    if missing:
        return ('WARN', f'缺：{"、".join(missing)}。⚠️ 此为【商业惯例 / 平台要求】，'
                        f'非法律义务 —— 中国著作权法未设「制作人」法定权利主体，'
                        f'也未规定发行时必须填实名，但发行商多拒收艺名/化名')
    return ('PASS', '演唱者/制作人均已填法定全名（惯例项）')


def check_isrc_legal_mandatory(track, rule, ctx):
    """C-002a【法律强制】ISRC（新出政发〔2011〕19 号）"""
    isrc = _md(track).get('isrc')
    if not isrc:
        return ('FAIL', '缺 ISRC。⚠️ 此为【法律强制】—— 新出政发〔2011〕19 号规定每一'
                        '可独立使用的录音制品均须分配单独 ISRC。'
                        '注：GB/T 13396-2009 本身是【推荐性】国标，强制力来自该文号')
    if not ISRC_RE.match(isrc.upper()):
        return ('FAIL', f'ISRC 格式非法：{isrc}（应为 12 位：2 字母国别 + 3 登记机构 + 2 年 + 5 序号）')
    return ('PASS', f'ISRC {isrc} 存在且格式合法（法律强制项）')


def check_upc_platform_practice(track, rule, ctx):
    """C-002b【商业惯例】UPC —— 无中国法律强制依据"""
    upc = _md(track).get('upc')
    if not upc:
        return ('WARN', '缺 UPC。⚠️ 此为【商业惯例 / DSP 交付必填字段】，'
                        '无中国法律强制依据；但缺失会导致 DSP 拒收或无法进榜')
    if not UPC_RE.match(upc):
        return ('WARN', f'UPC 格式非法：{upc}（应为 GTIN-12，12 位数字）')
    return ('PASS', f'UPC {upc} 格式合法（惯例项）')


def check_split_sum_normalized_practice(track, rule, ctx):
    """C-003【商业惯例】分成归一 100% —— 无法律条文要求"""
    splits = _md(track).get('splits') or []
    if not splits:
        return ('WARN', '未提供分成比例。⚠️ 此为【商业惯例 + 平台交付强制】，'
                        '著作权法第十四条仅规定「收益应当合理分配」，'
                        '无任何条文要求元数据分成登记为 100%')
    p = rule.get('params', {})
    total = sum(float(s.get('percent', 0)) for s in splits)
    if abs(total - p.get('expected_sum', 100.0)) <= p.get('tolerance', 0.01):
        return ('PASS', f'分成合计 {total:g}%（惯例项已满足）')
    return ('WARN', f'分成合计 {total:g}%，平台交付表单通常要求归一到 '
                    f'{p.get("expected_sum", 100):g}%。注：此为惯例而非法律义务，'
                    f'法律仅要求「合理分配」')


def check_master_right_legal(track, rule, ctx):
    """C-004a【法律强制】母带转发须同时取得著作权人+表演者许可"""
    v = _md(track).get('master_rights')
    if not v:
        return ('FAIL', '母带权利人未声明。⚠️ 此为【法律强制】—— 著作权法第四十二条/第四十四条：'
                        '被许可人复制发行录音录像制品，应当同时取得著作权人、表演者许可并支付报酬。'
                        '母带与词曲/表演权分属不同权利主体，混用为侵权高发点')
    return ('PASS', f'母带权利人已明确：{v}（法律强制项）')


def check_master_rights_declared_practice(track, rule, ctx):
    """C-004b【商业惯例】元数据中声明母带权利人"""
    v = _md(track).get('master_rights')
    if not v:
        return ('WARN', '未在元数据中声明母带权利人（惯例项，如 CD Baby 条款要求）')
    return ('PASS', f'已在元数据声明母带权利人：{v}（惯例项）')


def check_sample_license_legal(track, rule, ctx):
    """C-005a【法律强制】采样须取得著作权人许可并支付报酬"""
    if _md(track).get('uses_samples') is not True:
        return ('SKIP', '未使用采样，不适用')
    if (_md(track).get('licenses') or {}).get('sample'):
        return ('PASS', '采样授权已附（著作权法第四十二条第一款/第十六条要求）')
    return ('FAIL', '使用采样但未取得授权。著作权法第四十二条第一款：使用他人作品制作'
                    '录音录像制品，应当取得著作权人许可并支付报酬；改编/汇编还须取得'
                    '原作品著作权人许可（第十六条）—— 此为【法律强制】')


def check_voice_clone_consent_legal(track, rule, ctx):
    """C-005b【法律强制·人格权】声线/音色克隆须留存被授权人书面同意"""
    if _md(track).get('uses_voice_clone') is not True:
        return ('SKIP', '未使用声线/音色克隆，不适用')
    lic = (_md(track).get('licenses') or {}).get('voice')
    if lic:
        return ('PASS', '声线/音色克隆书面同意已留存（民法典第一千零一十九条禁止未经同意使用他人声音）')
    return ('FAIL', '使用声线/音色克隆但未留存被授权人书面同意。⚠️ 法律依据是【人格权与'
                    '禁止仿冒】—— 民法典第一千零一十八条（肖像权）/第一千零二十三条'
                    '（声音权益参照肖像权保护）/第一千零一十九条（禁止以任何方式使用他人声音）。'
                    '法律未规定「授权书格式」，但要求可举证的同意')


# ---------- D 组 ----------

def check_ai_usage_four_elements(track, rule, ctx):
    """D-001【本项目自定义】AI 使用说明四要素"""
    if ctx.get('ai_generated') is not True:
        return ('SKIP', '非 AI 生成内容，不适用')
    usage = _md(track).get('ai_usage') or {}
    need = rule.get('params', {}).get('elements', [])
    labels = {'tool': '工具名', 'version': '版本',
              'stage': '参与环节', 'input_source': '输入来源'}
    missing = [labels.get(e, e) for e in need if not usage.get(e)]
    if missing:
        return ('WARN', f'AI 使用说明缺要素：{", ".join(missing)}。'
                        f'⚠️ 此为【本项目自定义披露字段】，非合规要求 —— '
                        f'但多数人只写「AI 生成」，补全才能界定责任边界')
    return ('PASS', f'四要素齐全：{usage.get("tool")} {usage.get("version")} / '
                    f'{usage.get("stage")} / 输入：{usage.get("input_source")}')


# ---------- E 组：法律标准 + 判例 + 客观特征 ----------

def check_lyrics_legal_standard_notice(track, rule, ctx):
    """E-001a 告知法律标准（非检查项，纯告知）"""
    return ('INFO', '认定标准：接触 + 实质性相似。二者缺一不构成剽窃。'
                    '本工具只提取客观特征，⛔ 不下侵权结论')


def check_eight_measure_not_safe_harbor(track, rule, ctx):
    """E-001b 纠正常见误解：八小节不是安全线"""
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


# ---- 韵脚归一（v2.1.0 新增，v2.1.1 修正）----
# 为什么要做：判例 (2014)穗中法知民终字第289号 的采信理由之一是
# 「韵脚统一押 ang」——两句末字不同（湖海/这里/世道 vs 阴凉/这里/归途）但**韵母相同**。
# 只比较末字字符，测不出这件事，属于「测了但测不到点上」。
#
# ⚠ v2.1.1 修正：v2.1.0 以为用「末两字后缀匹配」就能取到韵母，那是错的——
#   绝大多数汉字是单字，「海」的两字后缀就是「海」本身，取不到韵母。
#   结果：韵脚相似度恒等于字面相似度 = **一个看起来合理、实则毫无信息量的假数字**。
#   修法：内嵌「汉字→韵母」映射表（按韵母分组的常用字），未覆盖的字标 unknown
#   并在输出中**报告识别覆盖率**，覆盖率过低时该指标降权而非沉默。
_RHYME_GROUPS = {
    'a': '那啊啦他她它沙发花芽拿家啦马骂大他她卡沙查沙',  # 开口呼 a
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
        # 首次出现优先（避免被后面的组覆盖，如「去」应归 u 而非 v）
        RHYME_LOOKUP.setdefault(_c, _k)

# 韵类合并（近韵归并，用于相似度比较）
_RHYME_CLASS = {
    'ang': 'ang', 'ao': 'au', 'ai': 'ai', 'ei': 'ei', 'i': 'i',
    'an': 'an', 'en': 'en', 'in': 'in', 'ing': 'ing', 'eng': 'eng',
    'ong': 'ong', 'u': 'u', 'v': 'v', 'ui': 'ei', 'iu': 'iou',
    'ie': 'ie', 'e': 'e', 'er': 'er', 'ia': 'ia', 'ua': 'ua',
    'uo': 'uo', 've': 've', 'ou': 'au', 'a': 'a', 'van': 'van', 'ue': 've',
}


def _rhyme_of(ch):
    """单字 → 韵类；未覆盖返回 None（计入覆盖率分母）"""
    f = RHYME_LOOKUP.get(ch)
    if not f:
        return None
    return _RHYME_CLASS.get(f, f)


def _rhyme_profile(sentences):
    """一批句子的韵类序列 + 识别覆盖率"""
    classes, total = [], 0
    for s in sentences:
        if not s:
            continue
        total += 1
        c = _rhyme_of(s[-1])
        if c:
            classes.append(c)
    cov = len(classes) / total if total else 0.0
    return classes, cov


def check_lyrics_objective_features(track, rule, ctx):
    """
    E-001c 歌词抄袭客观特征提取
    ⛔ 只输出客观特征，绝不下「侵权 / 不侵权」结论。
    判例：(2014)穗中法知民终字第289号 —— 法院采信的是结构+句式+起句+韵脚的
    全面雷同，而非「相同字数占比高」。
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

    # 2) 段落结构向量（直接比序列，不 str() —— v1.0.1 修复）
    t_struct = [len(x) for x in t_paras]
    r_struct = [len(x) for x in r_paras]
    t_sent = [len(s) for x in t_paras for s in x]
    r_sent = [len(s) for x in r_paras for s in x]
    struct_sim = difflib.SequenceMatcher(None, t_sent, r_sent).ratio()
    para_sim = difflib.SequenceMatcher(None, t_struct, r_struct).ratio()

    # 3) 押韵表
    #    v2.1.0：双轨输出 —— 末字字面相似 + 韵母韵类相似。
    #    判例采信的是「韵脚统一押 ang」，末字不同但韵母相同才是关键信号，
    #    只比末字会把真正的押韵雷同判成「不相似」。
    t_sentences = [s for x in t_paras for s in x if s]
    r_sentences = [s for x in r_paras for s in x if s]
    t_rhyme_chars = [s[-1] for s in t_sentences]
    r_rhyme_chars = [s[-1] for s in r_sentences]
    rhyme_char_sim = difflib.SequenceMatcher(None, ''.join(t_rhyme_chars),
                                             ''.join(r_rhyme_chars)).ratio()
    t_rhyme, t_cov = _rhyme_profile(t_sentences)
    r_rhyme, r_cov = _rhyme_profile(r_sentences)
    rhyme_sim = difflib.SequenceMatcher(None, ''.join(t_rhyme), ''.join(r_rhyme)).ratio() \
        if (t_rhyme and r_rhyme) else 0.0
    cov_min = min(t_cov, r_cov)

    # 4) n-gram 连续重合
    t_ng = {t_flat[i:i + n] for i in range(max(0, len(t_flat) - n + 1))}
    r_ng = {r_flat[i:i + n] for i in range(max(0, len(r_flat) - n + 1))}
    overlap = t_ng & r_ng
    ngram_ratio = len(overlap) / max(1, len(t_ng))

    # 5) 起句
    t_first = t_paras[0][0][:8] if t_paras and t_paras[0] else ''
    r_first = r_paras[0][0][:8] if r_paras and r_paras[0] else ''
    first_same = bool(t_first) and t_first == r_first

    feats = [
        f'字级重合率 {char_ratio:.1%}',
        f'句长序列相似 {struct_sim:.1%}',
        f'段落句数结构相似 {para_sim:.1%}',
        f'韵脚相似（韵母归一） {rhyme_sim:.1%}  ← 判例采信要点'
        f'（韵类识别覆盖率 {cov_min:.0%}）',
        f'　韵脚字面相似（仅末字） {rhyme_char_sim:.1%}  ← 对照用',
        f'{n}-gram 重合 {ngram_ratio:.1%}'
        + (f'（重合片段：{"、".join(sorted(overlap)[:5])}）' if overlap else ''),
        f'起句比对：{t_first!r} vs {r_first!r} → {"相同" if first_same else "不同"}',
        f'韵类序列：待检 {"".join(t_rhyme)[:16]} vs 对照 {"".join(r_rhyme)[:16]}',
    ]
    if cov_min < 0.6:
        feats.append(f'⚠ 韵类识别覆盖率仅 {cov_min:.0%}（映射表未覆盖部分末字），'
                     f'韵脚指标可信度下降 —— 需补 _RHYME_GROUPS 或人工核对')
    ctx.setdefault('features', []).append({
        'rule': 'E-001c', 'char_ratio': round(char_ratio, 4),
        'struct_sim': round(struct_sim, 4), 'para_sim': round(para_sim, 4),
        'rhyme_sim': round(rhyme_sim, 4), 'rhyme_char_sim': round(rhyme_char_sim, 4),
        'rhyme_coverage': round(cov_min, 4),
        'ngram_ratio': round(ngram_ratio, 4), 'first_line_same': first_same,
        'rhyme_seq_target': ''.join(t_rhyme), 'rhyme_seq_reference': ''.join(r_rhyme),
    })

    need = []
    hi = p.get('warn_char_ratio_high', 0.45)
    lo = p.get('warn_char_ratio_low', 0.10)
    if char_ratio >= hi:
        need.append(f'字级重合 {char_ratio:.1%} 偏高（阈值 {hi:.0%}）')
    elif char_ratio < lo:
        need.append(f'字级重合仅 {char_ratio:.1%}（低于 {lo:.0%}）—— '
                    f'但若结构/韵脚雷同，仍可能构成实质性相似')
    if p.get('warn_structure_match') and struct_sim >= 0.9:
        need.append(f'句长序列高度相似（{struct_sim:.1%}）')
    if p.get('warn_structure_match') and para_sim >= 0.9:
        need.append(f'段落句数结构高度相似（{para_sim:.1%}）')
    # 韵脚：判例采信要点，独立设阈；覆盖率不足时降权
    if cov_min >= 0.6:
        if rhyme_sim >= 0.9:
            need.append(f'韵脚韵类高度一致（{rhyme_sim:.1%}，覆盖率 {cov_min:.0%}）—— '
                        f'判例中「韵脚统一」是采信的独立理由，非辅证')
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
                '法院采信的是【结构+句式+起句+韵脚全面雷同】，而非单纯字数占比')
    return ('PASS', detail + ' ｜ 未见显著客观特征重合（仍不构成侵权认定）')


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
        print("退出码: 0=通过(无BLOCK) 1=有BLOCK 2=无BLOCK但有WARN")
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

    print('=' * 74)
    print(f"音乐发行前合规体检 · 政策版本 {policy['policy_version']}  "
          f"（{len(policy.get('rules', {}))} 条规则）")
    print(f"曲目：{track.get('title', '(未命名)')} ｜ 发行商：{ctx.get('distributor', '(未指定)')}")
    print("强度图例：⚖ 法律强制 · § 法律标准/判例 · ◆ 平台技术要求 · ◇ 商业惯例/平台表态 · ★ 本项目自定义")
    print('=' * 74)
    blocks = warns = passes = skips = infos = 0
    for rid, rule, status, detail in results:
        icon = {'FAIL': '✗', 'WARN': '⚠', 'PASS': '✓', 'SKIP': '–', 'INFO': 'ℹ'}[status]
        et = rule.get('enforce_type', '')
        print(f"{icon} [{rid}]({ET_ICON.get(et, '?')} {ET_LABEL.get(et, et)}) {rule['desc'][:70]}")
        print(f"      → {detail}")
        if status == 'FAIL':
            blocks += 1
        elif status == 'WARN':
            warns += 1
        elif status == 'PASS':
            passes += 1
        elif status == 'INFO':
            infos += 1
        else:
            skips += 1
    print('-' * 74)
    print(f"合计 {len(results)} 条：BLOCK {blocks} ｜ WARN {warns} ｜ PASS {passes} "
          f"｜ INFO {infos} ｜ SKIP {skips}")
    print("红线声明：")
    for r in policy.get('red_lines', []):
        print("  ⛔ " + r)

    # 需专业复核提示（v2.1.0 新增）—— 让工具自己说清哪几条不敢保证
    npr = policy.get('needs_pro_review') or []
    if npr:
        high = [x for x in npr if x.get('risk') == 'high']
        md = policy.get('review_metadata', {})
        print('-' * 74)
        print(f"⚠ 需专业复核 {len(npr)} 条（其中高风险 {len(high)} 条）"
              f"｜ 核证于 {md.get('reviewed_at', '—')}")
        for x in high:
            print(f"  ⚠ [{x.get('rule')}] {x.get('question', '')[:88]}")
        print(f"  详情见 policy 表 needs_pro_review 字段（{md.get('who', '建议律师复核')}）")
        if md.get('reviewer_note'):
            print(f"  {md['reviewer_note'][:100]}")

    if blocks:
        print("结论：不通过（存在法律强制/平台技术 BLOCK 项），先修再发行。")
        return 1
    if warns:
        print("结论：无 BLOCK，但有 WARN（含商业惯例项），需人眼确认。")
        return 2
    print("结论：通过。")
    return 0


if __name__ == '__main__':
    sys.exit(main())
