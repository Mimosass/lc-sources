import os, json, yaml, requests, fnmatch
from packaging.version import parse as vparse, InvalidVersion

with open("repos.yml", "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

token = os.environ.get("GITHUB_TOKEN")
headers = {"Authorization": f"Bearer {token}"} if token else {}

# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def match_asset(rel, patterns):
    """匹配 release 里的资源文件，返回 [(name, url, size), ...]"""
    if not patterns or patterns.strip() == "":
        patterns = "*.ipa"
    pats = [p.strip() for p in patterns.split(",")]
    results = []
    for a in rel.get("assets", []):
        for pat in pats:
            if fnmatch.fnmatch(a["name"].lower(), pat.lower()):
                results.append({
                    "name": a["name"],
                    "url": a["browser_download_url"],
                    "size": a["size"],
                })
                break
    return results

def tag_match(tag, pattern):
    if not pattern or pattern == "*":
        return True
    return fnmatch.fnmatch(tag, pattern)

def pick_stable(releases, strategy, tag_pattern):
    """从 releases 列表里挑最新正式版"""
    if strategy == "latest":
        return None  # 调用方单独走 /releases/latest
    cands = [
        r for r in releases
        if not r.get("prerelease") and not r.get("draft")
        and tag_match(r["tag_name"], tag_pattern)
    ]
    cands.sort(key=lambda r: r["published_at"], reverse=True)
    return cands[0] if cands else None

def pick_nightly(releases, strategy, tag_pattern):
    """从 releases 列表里挑夜版/prerelease"""
    cands = [r for r in releases if tag_match(r["tag_name"], tag_pattern)]
    if strategy == "nightly":
        cands = [r for r in cands if r["tag_name"] == "nightly"]
    elif strategy == "prerelease":
        cands = [r for r in cands if r.get("prerelease")]
    else:
        return None
    cands.sort(key=lambda r: r["published_at"], reverse=True)
    return cands[0] if cands else None

# ──────────────────────────────────────────────
# 主逻辑
# ──────────────────────────────────────────────

stable_apps, nightly_apps, tweak_items = [], [], []

for r in cfg["repos"]:
    owner, repo = r["owner"], r["repo"]
    is_tweak = r.get("type") == "tweak"

    print(f"处理 {owner}/{repo}  ({'插件' if is_tweak else 'App'})")

    # 拉最近 20 个 release
    try:
        releases = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=20",
            headers=headers, timeout=30
        ).json()
    except Exception as e:
        print("  ❌ 拉取失败:", e)
        continue

    if not isinstance(releases, list) or len(releases) == 0:
        print("  ⚠️ 没有 Release")
        continue

    tag_pat = r.get("tag_pattern", "*")
    stable_cfg = r.get("stable", "newest")
    nightly_cfg = r.get("nightly", "prerelease")
    asset_pat = r.get("asset_pattern", "*.ipa" if not is_tweak else "*.dylib,*.framework,*.zip")

    # ── 正式版 ──
    rel = pick_stable(releases, stable_cfg, tag_pat)
    if stable_cfg == "latest" and not rel:
        try:
            rel = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/releases/latest",
                headers=headers, timeout=30
            ).json()
        except Exception:
            rel = None

    if rel:
        assets = match_asset(rel, asset_pat)

        if is_tweak:
            # tweak 类型 → 写进 tweak_items
            if assets:
                tweak_items.append({
                    "name": r.get("name", repo),
                    "bundleIdentifier": r.get("bundle_id", f"io.github.{owner}.{repo}"),
                    "developerName": owner,
                    "version": rel["tag_name"].lstrip("v"),
                    "versionDate": rel["published_at"][:10],
                    "versionDescription": (rel.get("body") or "")[:800],
                    "iconURL": r.get("icon", ""),
                    "localizedDescription": r.get("note", "LiveContainer dylib tweak"),
                    "tweakScope": r.get("tweak_scope", "global"),
                    "installHint": "Tweaks 页导入 → 签名 → 绑定 App",
                    "assets": assets,
                    "tintColor": "#AF52DE",
                })
        else:
            # 普通 App → 找 IPA
            ipa_assets = [a for a in assets if a["name"].lower().endswith(".ipa")]
            if ipa_assets:
                a = ipa_assets[0]
                stable_apps.append({
                    "name": r.get("name", repo),
                    "bundleIdentifier": r.get("bundle_id", f"io.github.{owner}.{repo}"),
                    "developerName": owner,
                    "version": rel["tag_name"].lstrip("v"),
                    "versionDate": rel["published_at"][:10],
                    "versionDescription": (rel.get("body") or "")[:800],
                    "downloadURL": a["url"],
                    "size": a["size"],
                    "iconURL": r.get("icon", ""),
                    "localizedDescription": f"Stable build from {owner}/{repo}",
                    "tintColor": "#007AFF",
                })

    # ── 夜版/prerelease ──
    nrel = pick_nightly(releases, nightly_cfg, tag_pat)
    if nrel:
        assets = match_asset(nrel, asset_pat)

        if is_tweak:
            if assets:
                tweak_items.append({
                    "name": f"{r.get('name', repo)} (Nightly)",
                    "bundleIdentifier": f"{r.get('bundle_id', f'io.github.{owner}.{repo}')}.nightly",
                    "developerName": owner,
                    "version": nrel["tag_name"],
                    "versionDate": nrel["published_at"][:10],
                    "versionDescription": (nrel.get("body") or "Nightly build")[:800],
                    "iconURL": r.get("icon", ""),
                    "localizedDescription": f"Nightly tweak from {owner}/{repo}",
                    "tweakScope": r.get("tweak_scope", "global"),
                    "installHint": "Tweaks 页导入 → 签名 → 绑定 App",
                    "assets": assets,
                    "tintColor": "#FF9500",
                })
        else:
            ipa_assets = [a for a in assets if a["name"].lower().endswith(".ipa")]
            if ipa_assets:
                a = ipa_assets[0]
                nightly_apps.append({
                    "name": f"{r.get('name', repo)} (Nightly)",
                    "bundleIdentifier": f"{r.get('bundle_id', f'io.github.{owner}.{repo}')}.nightly",
                    "developerName": owner,
                    "version": nrel["tag_name"],
                    "versionDate": nrel["published_at"][:10],
                    "versionDescription": (nrel.get("body") or "Nightly build")[:800],
                    "downloadURL": a["url"],
                    "size": a["size"],
                    "iconURL": r.get("icon", ""),
                    "localizedDescription": f"Nightly build from {owner}/{repo}",
                    "tintColor": "#FF9500",
                })

# ──────────────────────────────────────────────
# 输出 JSON
# ──────────────────────────────────────────────

os.makedirs("public", exist_ok=True)

# stable.json
with open("public/stable.json", "w", encoding="utf-8") as f:
    json.dump({
        "name": "Mimosass LC 正式源",
        "identifier": "me.mimosass.lc.stable",
        "subtitle": "自动同步各仓库最新正式版",
        "tintColor": "#007AFF",
        "apps": stable_apps
    }, f, indent=2, ensure_ascii=False)

# nightly.json
with open("public/nightly.json", "w", encoding="utf-8") as f:
    json.dump({
        "name": "Mimosass LC 夜间源",
        "identifier": "me.mimosass.lc.nightly",
        "subtitle": "自动同步各仓库最新预发布/夜版",
        "tintColor": "#FF9500",
        "apps": nightly_apps
    }, f, indent=2, ensure_ascii=False)

# tweaks.json
with open("public/tweaks.json", "w", encoding="utf-8") as f:
    json.dump({
        "name": "Mimosass LC 插件源",
        "identifier": "me.mimosass.lc.tweaks",
        "subtitle": "dylib / framework 插件下载",
        "tintColor": "#AF52DE",
        "tweaks": tweak_items
    }, f, indent=2, ensure_ascii=False)

print(f"\n✅ 生成完成:")
print(f"   stable.json  → {len(stable_apps)} 个 App")
print(f"   nightly.json → {len(nightly_apps)} 个 App")
print(f"   tweaks.json  → {len(tweak_items)} 个插件")
