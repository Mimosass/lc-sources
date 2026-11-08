# lc-sources

SideStore / LiveContainer 订阅源（自动生成，每 6 小时刷新一次）。

| 源 | 地址 | 内容 |
|---|---|---|
| 正式源 | https://mimosass.github.io/lc-sources/stable.json | 各仓库最新正式版 |
| 夜间源 | https://mimosass.github.io/lc-sources/nightly.json | 各仓库最新 nightly 构建（含简体中文版） |
| 插件源 | https://mimosass.github.io/lc-sources/tweaks.json | dylib / framework 插件 |

在 SideStore（Sources → 加号 → 粘贴地址）或 LiveContainer（Add AltSource）里添加即可。

## 简体中文每夜版

`zh-sidestore-nightly` / `zh-livecontainer-nightly` 两个预发布 Release，由本仓库的
`.github/workflows/zh-sidestore.yml`、`zh-livecontainer.yml` 每天自动构建：

- 上游代码：`SideStore/SideStore@localization`、`LiveContainer/LiveContainer@main`，构建时现拉，仓库里不存源码；
- 汉化：`zh/sidestore/zh-Hans.json`（+ `AltWidget.xcstrings`）、`zh/livecontainer/zh-Hans.json` 由 `zh/scripts/apply_zh_*.py` 注入 String Catalog；
- 产物：`SideStore-zh-unsigned.ipa`、`LiveContainer-zh-unsigned.ipa`，未签名（adhoc 都不打），装的时候由 SideStore 用你自己的证书签；
- 每天覆盖同一个 Release，下载地址恒定；未汉化的 key 数写在 Release 说明里。

`repos.yml` 里那两条 `name: ... 简体中文` 的条目就是喂给 `build_sources.py` 的，所以源里能直接看到并安装。
