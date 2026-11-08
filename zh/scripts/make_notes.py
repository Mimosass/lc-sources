#!/usr/bin/env python3
"""Compose release notes for the nightly zh-Hans build.

Usage: make_notes.py <zh-report.json> <upstream desc> <sha> <date>
"""
import json, sys

report, upstream_desc, sha, date = sys.argv[1:5]
with open(report, encoding='utf-8') as f:
    rep = json.load(f)
n = rep.get('main', {}).get('untranslated', rep.get('untranslated', -1))
lines = [
    f'**每夜版 {date}（北京时间）** — 由 {upstream_desc} (`{sha}`) + 本仓库简体中文 overlay 自动构建。',
    '',
    '- 未签名 IPA：无 embedded.mobileprovision，adhoc 签名，可直接用 LiveContainer 等工具安装。',
    f'- 界面语言：简体中文（上游新增但尚未汉化的 key：{n} 个，缺的会回退显示英文，隔天由维护者补齐）。',
    '- 构建方式：每次都拉上游最新代码，再把本仓库 `localization/` overlay 注入 String Catalog，不依赖镜像源码树。',
    '- 同一个 Release 每天覆盖，文件名不变，下载地址恒定。',
]
print('\n'.join(lines))
