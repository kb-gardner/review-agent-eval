import csv, re, random, json
rows=list(csv.DictReader(open('../../docs/data/prs.csv')))
skip=re.compile(r'docs|ci\b|ci\(|chore|release|workflow|topic|banner|changeset|readme|typo|translation|bump|version', re.I)
repos=('honojs/hono','expressjs/express','fastapi/fastapi','vitejs/vite','better-auth/better-auth','tailwindlabs/tailwindcss','jetstreamapp/jetstream','drizzle-team/drizzle-orm')
ok=[r for r in rows if r['repo'] in repos and 40<=int(r['changed_lines'])<=400 and int(r['changed_files'])<=8 and not skip.search(r['title'])]
random.seed(11); random.shuffle(ok)
pick=ok[:12]
json.dump([{ 'id': f"{r['repo'].split('/')[1]}-{r['number']}", 'repo': r['repo'], 'num': int(r['number']), 'sha': r['merge_commit_sha'], 'lines': int(r['changed_lines']), 'files': int(r['changed_files']), 'title': r['title']} for r in pick], open('prs.json','w'), indent=1)
for r in pick: print(r['repo'], r['number'], r['changed_lines'], r['changed_files'], r['title'][:70])
