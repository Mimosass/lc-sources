#!/usr/bin/env python3
"""Apply zh-Hans overlay onto an upstream LiveContainer checkout (idempotent)."""
import argparse, json, os, re, sys

def log(*a): print(*a, flush=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--overlay', required=True)
    ap.add_argument('--report')
    a = ap.parse_args()
    catalog = os.path.join(os.path.abspath(a.root), 'Resources', 'Localizable.xcstrings')
    if not os.path.exists(catalog):
        sys.exit(f'ERROR: {catalog} not found')
    with open(catalog, encoding='utf-8') as f:
        d = json.load(f)
    overlay = json.load(open(os.path.join(os.path.abspath(a.overlay), 'zh-Hans.json'), encoding='utf-8'))
    strings = d.setdefault('strings', {})
    injected = created = 0
    for key, zh in overlay.items():
        ent = strings.get(key)
        if ent is None:
            strings[key] = {'extractionState': 'manual', 'localizations': {}}
            ent = strings[key]
            created += 1
        ent.setdefault('localizations', {})['zh-Hans'] = {'stringUnit': {'state': 'translated', 'value': zh}}
        injected += 1
    with open(catalog, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write('\n')
    def has_zh(v):
        zh = v.get('localizations', {}).get('zh-Hans', {})
        if zh.get('stringUnit', {}).get('value'):
            return True
        plural = zh.get('variations', {}).get('plural', {})
        return any(c.get('stringUnit', {}).get('value') for c in plural.values())
    untr = [k for k, v in strings.items() if not has_zh(v) and re.search(r'[A-Za-z]', k)]
    log(f'  catalog keys {len(strings)}, injected {injected} (created {created}), untranslated-after {len(untr)}')
    if injected < 300:
        sys.exit(f'ERROR: only {injected} injected, expected >=300')
    if a.report:
        with open(a.report, 'w', encoding='utf-8') as f:
            json.dump({'catalog_keys': len(strings), 'injected': injected, 'created': created,
                       'untranslated': len(untr), 'untranslated_keys': sorted(untr)[:500]}, f,
                      ensure_ascii=False, indent=2)
    log('done')

if __name__ == '__main__':
    main()
