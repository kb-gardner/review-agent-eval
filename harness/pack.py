import subprocess, json, sys, os
def sh(c): return subprocess.run(c, shell=True, capture_output=True, text=True).stdout
prs=json.load(open('prs.json'))
for p in prs:
    out=f"packs/{p['id']}.md"
    if os.path.exists(out): continue
    repo,num,sha=p['repo'],p['num'],p['sha']
    diff=sh(f"gh pr diff {num} --repo {repo}")
    files=json.loads(sh(f"gh api repos/{repo}/pulls/{num}/files --paginate") or "[]")
    parts=[f"# PR pack: {repo}#{num}\nTitle: {p['title']}\nMerge commit: {sha}\n\n## Diff\n```diff\n{diff}\n```\n\n## Touched files at the merge commit (window of up to 200 lines around the first changed hunk)\n"]
    for f in sorted(files, key=lambda f:-(f.get('additions',0)+f.get('deletions',0)))[:8]:
        path=f['filename']
        if f.get('status')=='removed': continue
        content=sh(f"gh api 'repos/{repo}/contents/{path}?ref={sha}' -H 'Accept: application/vnd.github.raw' 2>/dev/null")
        if not content: continue
        lines=content.split('\n')
        import re
        m=re.search(r'@@ -\d+,?\d* \+(\d+)', f.get('patch','') or '')
        start=max(0,(int(m.group(1)) if m else 1)-60); end=min(len(lines), start+200)
        body='\n'.join(f"{i+1:5d}| {l}" for i,l in enumerate(lines[start:end], start))
        parts.append(f"\n### {path} (lines {start+1} to {end} of {len(lines)})\n```\n{body}\n```\n")
    open(out,'w').write(''.join(parts))
    print(out, len(''.join(parts))//4, "tokens est")
