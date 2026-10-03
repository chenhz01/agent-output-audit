# music-release-audit

音乐发行前合规体检器 · v1.0.1

**只做能写成 if 的确定性检查，不下法律结论。**

## 快速开始

```bash
P=<managed python>
S=~/.workbuddy/skills/music-release-audit
"$P" $S/scripts/audit.py <track.json>     # 退出码 0=通过 1=有BLOCK 2=只有WARN
```

## 回归（三夹具，各对应一档退出码）

```bash
"$P" $S/scripts/audit.py $S/fixtures/track_fail.json           # → 1（9 BLOCK）
"$P" $S/scripts/audit.py $S/fixtures/track_pass.json           # → 0（无问题）
"$P" $S/scripts/audit.py $S/fixtures/track_lyrics_similar.json # → 2（E-001 触发）
```

## 覆盖

- **AI 标识合规**：中国《人工智能生成合成内容标识办法》显式+隐式双标识、视频文字提示 ≥5% 且 ≥2 秒；欧盟 AI Act Art.50(2)
- **发行商 AI 政策二元判定**：CD Baby（拒绝）/ TuneCore（需完全获许可数据集）/ 网易云（需主动声明）/ Spotify（需分项 AI Credits）
- **著作权元数据五层清单**：实名 / ISRC·UPC 格式 / 分成归一 / 母带权利人 / 采样与声线授权
- **AI 使用说明四要素**：工具名 / 版本 / 参与环节 / 输入来源
- **歌词抄袭客观特征**：字级重合率、句长序列、段落结构、押韵表、4-gram 片段、起句

## 红线

- ❌ 不做音频 AI 生成检测 / 人声克隆识别
- ❌ 不下「侵权 / 不侵权」结论——法律标准是「接触 + 实质性相似」，必须人判
- ❌ 不做文案夸大宣传、医疗符合指南、合同商业合理性判断

## 扩展

**加规则改 `data/policy_*.json`，不改代码。** 每条规则须带 `check` / `source` / `severity` / `enabled`。
政策会过期——这张版本化维护表本身就是护城河。

详见 `SKILL.md`。
