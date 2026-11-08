#!/usr/bin/env python3
"""Apply zh-Hans overlay onto an upstream SideStore checkout.

Usage: apply_zh.py --root <upstream checkout> --overlay <overlay dir> [--report <json>]

Idempotent. Fails loudly when upstream layout changes in a way we do not expect.
"""
import argparse, json, os, re, sys

def log(*a): print(*a, flush=True)

def load_json(p):
    with open(p, encoding='utf-8') as f: return json.load(f)

def dump_json(obj, p):
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)

def inject(catalog_path, overlay):
    d = load_json(catalog_path)
    strings = d.setdefault('strings', {})
    injected = missing_in_upstream = created = 0
    for key, zh in overlay.items():
        ent = strings.get(key)
        if ent is None:
            # key only exists as a hardcoded SwiftUI literal upstream: create it explicitly
            strings[key] = {'extractionState': 'manual', 'localizations': {}}
            ent = strings[key]
            created += 1
        ent.setdefault('localizations', {})['zh-Hans'] = {
            'stringUnit': {'state': 'translated', 'value': zh}
        }
        injected += 1
    def has_zh(v):
        zh = v.get('localizations', {}).get('zh-Hans', {})
        if zh.get('stringUnit', {}).get('value'):
            return True
        plural = zh.get('variations', {}).get('plural', {})
        return any(c.get('stringUnit', {}).get('value') for c in plural.values())
    untranslated = [k for k, v in strings.items() if not has_zh(v) and re.search(r'[A-Za-z]', k)]
    with open(catalog_path, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write('\n')
    log(f'  {os.path.relpath(catalog_path)}: injected {injected}, created-manual {created}, '
        f'untranslated-after {len(untranslated)}')
    return injected, created, len(untranslated), untranslated

def ensure_known_region(pbxproj_path):
    s = open(pbxproj_path, encoding='utf-8').read()
    m = re.search(r'knownRegions = \((.*?)\);', s, re.S)
    if not m:
        sys.exit('ERROR: knownRegions not found in project.pbxproj')
    if re.search(r'"zh-Hans"|\bzh-Hans\b', m.group(1)):
        log('  knownRegions already contains zh-Hans')
        return False
    body = m.group(1)
    new_body = body.rstrip() + '\n\t\t\t\tzh-Hans,\n\t\t\t'
    new_body = re.sub(r'\n[ \t]*$', '\n\t\t\t', new_body) if False else new_body
    s = s[:m.start(1)] + new_body + s[m.end(1):]
    open(pbxproj_path, 'w', encoding='utf-8').write(s)
    log('  knownRegions += zh-Hans')
    return True

def disable_string_symbols(pbxproj_path, target_name):
    """Insert STRING_CATALOG_GENERATE_SYMBOLS = NO into a target's Debug/Release configs."""
    s = open(pbxproj_path, encoding='utf-8').read()
    tm = re.search(r'([0-9A-F]{24}) /\* ' + re.escape(target_name) + r' \*/ = \{\s*isa = PBXNativeTarget;.*?buildConfigurationList = ([0-9A-F]{24})', s, re.S)
    if not tm:
        sys.exit(f'ERROR: target {target_name} not found in project.pbxproj')
    lc = re.search(r'([0-9A-F]{24}) /\* Build configuration list for PBXNativeTarget "' + re.escape(target_name) + r'" \*/ = \{.*?buildConfigurations = \((.*?)\);', s, re.S)
    if not lc:
        sys.exit(f'ERROR: build configuration list for {target_name} not found')
    ids = re.findall(r'([0-9A-F]{24})', lc.group(2))
    changed = 0
    for cid in ids:
        cm = re.search(r'(' + cid + r' /\* (?:Debug|Release) \*/ = \{\s*isa = XCBuildConfiguration;(?:(?!\};).)*?buildSettings = \{\n)', s, re.S)
        if not cm:
            sys.exit(f'ERROR: XCBuildConfiguration {cid} not found')
        start = cm.end()
        end = s.find('};', start)
        block = s[start:end]
        if 'STRING_CATALOG_GENERATE_SYMBOLS' in block:
            continue
        indent = '\t\t\t\t'
        s = s[:start] + f'{indent}STRING_CATALOG_GENERATE_SYMBOLS = NO;\n' + s[start:]
        changed += 1
    if changed:
        open(pbxproj_path, 'w', encoding='utf-8').write(s)
    log(f'  {target_name}: STRING_CATALOG_GENERATE_SYMBOLS=NO added in {changed} config(s)')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--overlay', required=True)
    ap.add_argument('--report')
    a = ap.parse_args()
    root, ov = os.path.abspath(a.root), os.path.abspath(a.overlay)
    result = {}

    main_catalog = os.path.join(root, 'SideStore', 'Localizable.xcstrings')
    if not os.path.exists(main_catalog):
        cands = [os.path.join(dp, f) for dp, _, fs in os.walk(root) for f in fs if f.endswith('.xcstrings')]
        sys.exit('ERROR: SideStore/Localizable.xcstrings not found; xcstrings in tree: %s' % cands)
    inj, created, untr, untr_keys = inject(main_catalog, load_json(os.path.join(ov, 'zh-Hans.json')))
    result['main'] = {'injected': inj, 'created': created, 'untranslated': untr}
    if inj < 1000:
        sys.exit(f'ERROR: only {inj} strings injected, expected >1000')

    widget_src = os.path.join(ov, 'AltWidget.xcstrings')
    widget_dir = os.path.join(root, 'AltWidget')
    if os.path.isdir(widget_dir) and os.path.exists(widget_src):
        dump_json(load_json(widget_src), os.path.join(widget_dir, 'Localizable.xcstrings'))
        log('  AltWidget/Localizable.xcstrings written from overlay')

    pbx = os.path.join(root, 'AltStore.xcodeproj', 'project.pbxproj')
    ensure_known_region(pbx)
    disable_string_symbols(pbx, 'AltWidgetExtension')

    lproj = os.path.join(root, 'SideStore', 'zh-Hans.lproj')
    os.makedirs(lproj, exist_ok=True)
    with open(os.path.join(lproj, 'InfoPlist.strings'), 'w', encoding='utf-8') as f:
        f.write('"CFBundleDisplayName" = "SideStore";\n'
                '"CFBundleName" = "SideStore";\n'
                '"NSLocalNetworkUsageDescription" = "SideStore 需要访问本地网络，以发现您网络上的 Bonjour（mDNS）服务。核心功能不依赖此权限。";\n')
    log('  SideStore/zh-Hans.lproj/InfoPlist.strings written')

    if a.report:
        result['untranslated_keys'] = sorted(untr_keys)[:500]
        with open(a.report, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    log('done')

if __name__ == '__main__':
    main()
