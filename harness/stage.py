import json, glob, random, sys
# usage: stage.py <outdir> <pid> merge|judge
outdir, pid, mode = sys.argv[1], sys.argv[2], sys.argv[3]
if mode == 'merge':
    allf = []
    for f in sorted(glob.glob(f'{outdir}/{pid}.B.*.json')):
        if '.B.all.' in f: continue
        for x in json.load(open(f)):
            x['source_lens'] = f.split('.B.')[1].split('.json')[0]; allf.append(x)
    for i, x in enumerate(allf, 1): x['id'] = f'B{i}'
    json.dump(allf, open(f'{outdir}/{pid}.B.all.json', 'w'), indent=1)
    print(pid, 'A=', len(json.load(open(f'{outdir}/{pid}.A.json'))), 'B=', len(allf))
else:
    a = json.load(open(f'{outdir}/{pid}.A.json'))
    v = [x for x in json.load(open(f'{outdir}/{pid}.V.json')) if x.get('verdict') == 'keep']
    items = []
    for i, x in enumerate(a): items.append(('A', f'A{i+1}', x))
    for x in v: items.append(('B', x.get('id', '?'), x))
    random.seed(hash(pid) & 0xffff); random.shuffle(items)
    key, blind = [], []
    for i, (src, oid, x) in enumerate(items, 1):
        key.append({'id': f'F{i}', 'src': src, 'orig_id': oid})
        blind.append({'id': f'F{i}', 'file': x['file'], 'line': x['line'], 'severity': x.get('severity'), 'claim': x['claim'], 'evidence': x['evidence']})
    json.dump(blind, open(f'{outdir}/{pid}.J.in.json', 'w'), indent=1)
    json.dump(key, open(f'{outdir}/{pid}.J.key.json', 'w'), indent=1)
    print(pid, 'judge items', len(blind), 'A=', len(a), 'Bkept=', len(v))
