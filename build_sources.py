import os, json, yaml, requests
from packaging.version import parse as vparse, InvalidVersion

with open("repos.yml", "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

token = os.environ.get("GITHUB_TOKEN")
headers = {"Authorization": f"Bearer {token}"} if token else {}

def find_ipa(rel, pattern="*.ipa"):
    import fnmatch
    pat = pattern or "*.ipa"
    for a in rel.get("assets", []):
        if fnmatch.fnmatch(a["name"].lower(), pat.lower()):
            return a["browser_download_url"], a["size"]
    return None, 0

def tag_match(tag, pattern):
    import fnmatch
    if not pattern or pattern == "*":
        return True
    return fnmatch.fnmatch(tag, pattern)

def sort_key(tag):
    try:
        return (0, vparse(tag.lstrip("vV")))
    except InvalidVersion:
        return (1, tag)   # 解析不了版本号的放后面

def pick_stable(releases, strategy, tag_pattern):
    if strategy == "latest":
        # 调用方单独走 /releases/latest
        return None
    cands = [r for r in releases
             if not r.get("prerelease") and not r.get("draft")
             and tag_match(r["tag_name"], tag_pattern)]
    cands.sort(key=lambda r: r["published_at"], reverse=True)
    return cands[0] if cands else None

def pick_nightly(releases, strategy, tag_pattern):
    cands = [r for r in releases if tag_match(r["tag_name"], tag_pattern)]
    if strategy == "nightly":
        cands = [r for r in cands if r["tag_name"] == "nightly"]
    elif strategy == "prerelease":
        cands = [r for r in cands if r.get("prerelease")]
    else:
        return None
    cands.sort(key=lambda r: r["published_at"], reverse=True)
    return cands[0] if cands else None

stable_apps, nightly_apps = [], []

for r in cfg["repos"]:
    owner, repo = r["owner"], r["repo"]
    print("处理", owner, repo)

    # 拉最近 20 个 release（含 prerelease）
    try:
        releases = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=20",
            headers=headers, timeout=30
        ).json()
    except Exception as e:
        print("  拉取失败:", e)
        continue

    tag_pat = r.get("tag_pattern", "*")
    stable_cfg = r.get("stable", "newest")
    nightly_cfg = r.get("nightly", "prerelease")

    # ---- 正式版 ----
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
        url, size = find_ipa(rel, r.get("asset_pattern"))
        if url:
            stable_apps.append({
                "name": r.get("name", repo),
                "bundleIdentifier": r.get("bundle_id", f"io.github.{owner}.{repo}"),
                "developerName": owner,
                "version": rel["tag_name"].lstrip("v"),
                "versionDate": rel["published_at"][:10],
                "versionDescription": (rel.get("body") or "")[:800],
                "downloadURL": url,
                "size": size,
                "iconURL": r.get("icon", ""),
                "localizedDescription": f"Stable build from {owner}/{repo}",
                "tintColor": "#007AFF",
            })

    # ---- 夜版 ----
    nrel = pick_nightly(releases, nightly_cfg, tag_pat)
    if nrel:
        url, size = find_ipa(nrel, r.get("asset_pattern"))
        if url:
            nightly_apps.append({
                "name": f"{r.get('name', repo)} (Nightly)",
                "bundleIdentifier": f"{r.get('bundle_id', f'io.github.{owner}.{repo}')}.nightly",
                "developerName": owner,
                "version": nrel["tag_name"],
                "versionDate": nrel["published_at"][:10],
                "versionDescription": (nrel.get("body") or "Nightly build")[:800],
                "downloadURL": url,
                "size": size,
                "iconURL": r.get("icon", ""),
                "localizedDescription": f"Nightly/prerelease from {owner}/{repo}",
                "tintColor": "#FF9500",
            })

os.makedirs("public", exist_ok=True)

with open("public/stable.json", "w", encoding="utf-8") as f:
    json.dump({
        "name": "Mimosass LC 正式源",
        "identifier": "me.mimosass.lc.stable",
        "subtitle": "自动同步各仓库最新正式版（支持编号 tag）",
        "tintColor": "#007AFF",
        "apps": stable_apps
    }, f, indent=2, ensure_ascii=False)

with open("public/nightly.json", "w", encoding="utf-8") as f:
    json.dump({
        "name": "Mimosass LC 夜间源",
        "identifier": "me.mimosass.lc.nightly",
        "subtitle": "自动同步各仓库最新预发布/夜版",
        "tintColor": "#FF9500",
        "apps": nightly_apps
    }, f, indent=2, ensure_ascii=False)

print("✅ 生成完成：stable.apps =", len(stable_apps), "nightly.apps =", len(nightly_apps))
