import json, os, glob
def load(p): return json.load(open(p)) if os.path.exists(p) else None
def base(f): return f.split('/')[-1]
gt = json.load(open('ground-truth.json'))
plants = {}
for g in gt: plants.setdefault(g['pack'].replace('.md',''), []).append(g)
def hits(findings, pid):
    got=set()
    for f in findings or []:
        for g in plants.get(pid, []):
            if base(f['file'])==base(g['file']) and abs(int(f['line'])-int(g['line']))<=25: got.add(g['id'])
    return got
rows=[]; tot={'A_f':0,'A_hit':0,'A_real':0,'A_fp':0,'B_f':0,'B_kept':0,'B_hit':0,'B_real':0,'B_fp':0,'plants':0,'judge_missed':0}
for pid in sorted(plants):
    A=load(f'out-planted/{pid}.A.json'); Ball=load(f'out-planted/{pid}.B.all.json'); V=load(f'out-planted/{pid}.V.json'); J=load(f'out-planted/{pid}.J.json'); K=load(f'out-planted/{pid}.J.key.json')
    kept=[x for x in (V or []) if x.get('verdict')=='keep']
    ah=hits(A,pid); bh=hits(kept,pid)
    a_real=a_fp=b_real=b_fp=0; missed=0
    if J and K:
        src={k['id']:k['src'] for k in K}
        for l in J['labels']:
            s=src.get(l['id'])
            if l['label']=='real': a_real+= s=='A'; b_real+= s=='B'
            elif l['label']=='not_real': a_fp+= s=='A'; b_fp+= s=='B'
        missed=len(J.get('missed',[]))
    n=len(plants[pid])
    rows.append((pid, n, len(A or []), len(ah), a_real, a_fp, len(Ball or []), len(kept), len(bh), b_real, b_fp, missed, 'done' if J else 'pending'))
    for k,v in [('A_f',len(A or [])),('A_hit',len(ah)),('A_real',a_real),('A_fp',a_fp),('B_f',len(Ball or [])),('B_kept',len(kept)),('B_hit',len(bh)),('B_real',b_real),('B_fp',b_fp),('plants',n),('judge_missed',missed)]: tot[k]+=v
print(f"{'pack':22} plants  A:f hit real fp   B:f kept hit real fp  missed  judge")
for r in rows: print(f"{r[0]:22} {r[1]:>6}  {r[2]:>3} {r[3]:>3} {r[4]:>4} {r[5]:>2}   {r[6]:>3} {r[7]:>4} {r[8]:>3} {r[9]:>4} {r[10]:>2}  {r[11]:>6}  {r[12]}")
t=tot; print(f"{'TOTAL':22} {t['plants']:>6}  {t['A_f']:>3} {t['A_hit']:>3} {t['A_real']:>4} {t['A_fp']:>2}   {t['B_f']:>3} {t['B_kept']:>4} {t['B_hit']:>3} {t['B_real']:>4} {t['B_fp']:>2}  {t['judge_missed']:>6}")
print(f"\nrecall (plants hit): A {t['A_hit']}/{t['plants']}  B-kept {t['B_hit']}/{t['plants']}")
if t['A_real']+t['A_fp']: print(f"judge precision: A {t['A_real']}/{t['A_real']+t['A_fp']}", end='  ')
if t['B_real']+t['B_fp']: print(f"B-kept {t['B_real']}/{t['B_real']+t['B_fp']}")
print("\nREAL set (6 merged PRs):")
for pid in ['tailwindcss-20379','tailwindcss-20399','better-auth-11263','vite-23219','express-7366','jetstream-2045']:
    A=load(f'out/{pid}.A.json'); B=load(f'out/{pid}.B.all.json') or []; J=load(f'out/{pid}.J.json')
    print(f"  {pid:22} A={len(A or [])} B={len(B)} judge={'REAL '+str(sum(1 for l in J['labels'] if l['label']=='real'))+' NOTREAL '+str(sum(1 for l in J['labels'] if l['label']=='not_real'))+' missed '+str(len(J.get('missed',[]))) if J else '-'}")
