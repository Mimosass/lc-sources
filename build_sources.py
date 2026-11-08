import os, json, yaml, requests, fnmatch, datetime
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
    seen = set()
    for a in rel.get("assets", []):
        for pat in pats:
            if fnmatch.fnmatch(a["name"].lower(), pat.lower()):
                if a["name"] not in seen:
                    results.append({
                        "name": a["name"],
                        "url": a["browser_download_url"],
                        "size": a["size"],
                        "updated_at": a.get("updated_at"),
                    })
                    seen.add(a["name"])
                break
    return results

def tag_match(tag, pattern):
    if not pattern or pattern == "*":
        return True
    return fnmatch.fnmatch(tag, pattern)

def pick_stable(releases, strategy, tag_pattern):
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
    cands = [r for r in releases if tag_match(r["tag_name"], tag_pattern)]
    if strategy == "nightly":
        cands = [r for r in cands if r["tag_name"] == "nightly"]
    elif strategy == "prerelease":
        cands = [r for r in cands if r.get("prerelease")]
    else:
        return None
    cands.sort(key=lambda r: r["published_at"], reverse=True)
    return cands[0] if cands else None

def fetch_latest(owner, repo):
    try:
        return requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/releases/latest",
            headers=headers, timeout=30
        ).json()
    except Exception:
        return None

BJT = datetime.timezone(datetime.timedelta(hours=8))

def asset_datetime(rel, assets):
    """构建时间取资源上传时间——moving tag（如 nightly）的 published_at 是 tag 首次创建时间，可能是几年前。换算到北京时间。"""
    dates = [a["updated_at"] for a in assets if a.get("updated_at")]
    ts = max(dates) if dates else (rel.get("published_at") or "")
    if not ts:
        return None
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(BJT)

def asset_date(rel, assets):
    """AltStore 的 versionDate 用 yyyy-MM-dd（北京时间）。"""
    dt = asset_datetime(rel, assets)
    return dt.strftime("%Y-%m-%d") if dt else ""

def asset_version_date(rel, assets):
    """每夜版把版本号本身写成日期，方便在客户端一眼分辨新旧。"""
    dt = asset_datetime(rel, assets)
    return dt.strftime("%Y.%m.%d") if dt else ""


def build_app_entry(r, rel, assets, suffix=""):
    ipa = assets[0]
    base_bid = r.get("bundle_id", f"io.github.{r['owner']}.{r['repo']}")
    return {
        "name": r.get("name", r["repo"]) + suffix,
        "bundleIdentifier": base_bid,
        "developerName": r["owner"],
        "version": asset_version_date(rel, assets) if r.get("version") == "date" else rel["tag_name"].lstrip("v"),
        "versionDate": asset_date(rel, assets),
        "versionDescription": (rel.get("body") or "")[:800],
        "downloadURL": ipa["url"],
        "size": ipa["size"],
        "iconURL": r.get("icon", ""),
        "localizedDescription": f"{'Nightly' if 'Nightly' in suffix else 'Stable'} build from {r['owner']}/{r['repo']}",
        "tintColor": "#FF9500" if "Nightly" in suffix else "#007AFF",
    }

def build_tweak_entry(r, rel, assets, suffix=""):
    return {
        "name": r.get("name", r["repo"]) + suffix,
        "bundleIdentifier": r.get("bundle_id", f"io.github.{r['owner']}.{r['repo']}"),
        "developerName": r["owner"],
        "version": rel["tag_name"].lstrip("v"),
        "versionDate": asset_date(rel, assets),
        "versionDescription": (rel.get("body") or "Nightly build")[:800],
        "iconURL": r.get("icon", ""),
        "localizedDescription": r.get("note", "LiveContainer dylib tweak"),
        "tweakScope": r.get("tweak_scope", "global"),
        "installHint": "Tweaks 页导入 → 签名 → 绑定 App",
        "assets": assets,
        "tintColor": "#AF52DE",
    }

# ──────────────────────────────────────────────
# 主逻辑
# ──────────────────────────────────────────────

stable_apps, nightly_apps, tweak_items = [], [], []

for r in cfg["repos"]:
    owner, repo = r["owner"], r["repo"]
    is_tweak = r.get("type") == "tweak"
    print(f"处理 {owner}/{repo}  ({'插件' if is_tweak else 'App'})")

    try:
        releases = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=20",
            headers=headers, timeout=30
        ).json()
    except Exception as e:
        print("  ❌ 拉取失败:", e)
        continue

    if not isinstance(releases, list) or not releases:
        print("  ⚠️ 没有 Release")
        continue

    tag_pat = r.get("tag_pattern", "*")
    stable_cfg = r.get("stable", "newest")
    nightly_cfg = r.get("nightly", "prerelease")
    asset_pat = r.get("asset_pattern",
                      "*.dylib,*.framework,*.zip" if is_tweak else "*.ipa")

    # ── 正式版 ──
    rel = pick_stable(releases, stable_cfg, tag_pat)
    if stable_cfg == "latest" and not rel:
        rel = fetch_latest(owner, repo)

    if rel:
        assets = match_asset(rel, asset_pat)
        if not assets:
            print("  ⚠️ 正式版没匹配到资源:", asset_pat)
        elif is_tweak:
            tweak_items.append(build_tweak_entry(r, rel, assets))
        else:
            stable_apps.append(build_app_entry(r, rel, assets))

    # ── 夜版 ──
    nrel = pick_nightly(releases, nightly_cfg, tag_pat)
    if nrel:
        assets = match_asset(nrel, asset_pat)
        if not assets:
            print("  ⚠️ 夜版没匹配到资源:", asset_pat)
        elif is_tweak:
            tweak_items.append(build_tweak_entry(r, nrel, assets, suffix=" (Nightly)"))
        else:
            nightly_apps.append(build_app_entry(r, nrel, assets, suffix=" (Nightly)"))

# ──────────────────────────────────────────────
# 输出
# ──────────────────────────────────────────────

os.makedirs("public", exist_ok=True)

with open("public/stable.json", "w", encoding="utf-8") as f:
    json.dump({
        "name": "Mimosass LC 正式源",
        "identifier": "me.mimosass.lc.stable",
        "subtitle": "自动同步各仓库最新正式版",
        "tintColor": "#007AFF",
        "apps": stable_apps
    }, f, indent=2, ensure_ascii=False)

with open("public/nightly.json", "w", encoding="utf-8") as f:
    json.dump({
        "name": "Mimosass LC 夜间源",
        "identifier": "me.mimosass.lc.nightly",
        "subtitle": "自动同步各仓库最新 nightly 构建",
        "tintColor": "#FF9500",
        "apps": nightly_apps
    }, f, indent=2, ensure_ascii=False)

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
for a in stable_apps:
    print("   [稳定]", a["name"], a["version"])
for a in nightly_apps:
    print("   [夜版]", a["name"], a["version"])
