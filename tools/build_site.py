"""Build a single-file, strictly synthetic demo. Never opens a DB or .env."""
from pathlib import Path
import argparse,json,re
ROOT=Path(__file__).resolve().parents[1]

def build(destination=None):
    source=ROOT/'dashboard/static'
    html=(source/'index.html').read_text(encoding='utf-8')
    scripts=re.findall(r'<script src="([^"]+)" defer></script>',html)
    html=re.sub(r'<script src="[^"]+" defer></script>','',html)
    html=html.replace('<link rel="stylesheet" href="style.css">','<style>\n'+(source/'style.css').read_text(encoding='utf-8')+'\n</style>')
    fixture=(source/'fixtures.js').read_text(encoding='utf-8')
    payload=json.loads(fixture.split('window.SCM_FIXTURES=',1)[1].strip().rstrip(';'))
    if payload.get('synthetic') is not True:raise ValueError('Only reviewed synthetic fixtures may be published')
    code='<script>window.SCM_PREVIEW=true;</script>\n'
    for name in scripts:
        if name=='runtime-config.js':continue
        text=(source/name).read_text(encoding='utf-8').replace('</script','<\\/script')
        code+='<script>\n'+text+'\n</script>\n'
    html=html.replace('</body>',code+'</body>')
    # Strong static-demo policy: no network access, forms, iframes or remote code.
    policy="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src 'none'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
    html=html.replace('<head>','<head><meta http-equiv="Content-Security-Policy" content="'+policy+'">')
    dst=Path(destination) if destination else ROOT/'site/index.html';dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_text(html,encoding='utf-8')
    (dst.parent/'.nojekyll').write_text('')
    return dst
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');a=parser.parse_args();print(build(a.output))
