"""Final Mac acceptance checks, then open the app with a clean workspace."""
import sys,subprocess,json,time,shutil,sqlite3,os,signal,hashlib
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler,HTTPCookieProcessor
from urllib.error import URLError
from http.cookiejar import CookieJar
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from private_contracts.config import ROOT,DATA,initialize,ENGINE_URL
from private_contracts.engine import start_engine,stop_owned_engine,status
from private_contracts.templates import registry
from private_contracts import __version__
initialize()
results=ROOT/'test-results';results.mkdir(exist_ok=True)
def run_tool(name):
    print('Checking '+name,flush=True)
    subprocess.run([sys.executable,str(ROOT/'tools'/name)],cwd=ROOT,check=True)
def local_client():
    return build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()))
base='http://127.0.0.1:8768'
def shutdown():
    client=local_client()
    try:client.open(base,timeout=2).read()
    except (URLError,OSError):return
    try:
        boot=json.load(client.open(base+'/api/bootstrap'))
        client.open(Request(base+'/api/shutdown',data=b'{}',headers={'Content-Type':'application/json','Origin':base,'X-Private-CSRF':boot['csrf']})).read()
    except URLError:
        owned=json.load(client.open(base+'/api/ping'))
        assert owned.get('application')=='Private Contracts' and owned.get('data_id')==hashlib.sha256(str(DATA).encode()).hexdigest()
        pid=json.loads((DATA/'app-address.json').read_text())['pid']
        command=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True).stdout
        assert 'Private Contracts.app/Contents/MacOS/Private Contracts' in command or 'run.py' in command
        os.kill(pid,signal.SIGTERM)
    time.sleep(1)
def launch():
    binary=ROOT/'Private Contracts.app/Contents/MacOS/Private Contracts'
    log=(DATA/'logs/launcher.log').open('ab')
    process=subprocess.Popen([str(binary),'--no-browser','--port','8768'],cwd=ROOT,stdout=log,stderr=log,start_new_session=True)
    log.close()
    for _ in range(60):
        try:
            client=local_client();client.open(base,timeout=1).read()
            boot=json.load(client.open(base+'/api/bootstrap'))
            assert boot['engine']['model']=='qwen3-vl:2b-instruct'
            return process
        except (URLError,OSError):time.sleep(.25)
    raise RuntimeError('The packaged app did not become ready. See its local launcher log.')
if '--resume' not in sys.argv:
    subprocess.run([sys.executable,'-m','pytest','-q','tests'],cwd=ROOT,check=True)
    run_tool('smoke_ai.py');run_tool('smoke_identity.py')
    assert all(e.get('path') for e in registry().values()),'A template is still unconfigured'
    run_tool('output_checks.py')
with (results/'build.log').open('w') as log:subprocess.run([sys.executable,str(ROOT/'tools/build_mac.py')],cwd=ROOT,stdout=log,stderr=log,check=True)
subprocess.run([str(ROOT/'Private Contracts.app/Contents/MacOS/Private Contracts'),'--diagnose'],cwd=ROOT,check=True)
shutdown();launch()
if '--deploy-only' in sys.argv:
    subprocess.run(['/usr/bin/open',str(ROOT/'Private Contracts.app')],check=True)
    print('Updated local app opened; workspaces preserved.',flush=True)
    sys.exit(0)
node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
subprocess.run([str(node),str(ROOT/'tools/browser_smoke.cjs')],cwd=ROOT,check=True)
run_tool('api_checks.py')
subprocess.run([str(node),str(ROOT/'tools/browser_review.cjs')],cwd=ROOT,check=True)
run_tool('verify_privacy.py')
shutdown()
# Archive only workspaces that are demonstrably fictional development fixtures.
db=sqlite3.connect(DATA/'workspace.sqlite3')
jobs=[json.loads(r[0]) for r in db.execute('SELECT content FROM jobs')]
names=[r[0] for r in db.execute('SELECT name FROM sources')];db.close()
fictional=all((not j['fields']['name_en']['value'] or j['fields']['name_en']['value'].startswith('Test ')) and (not j['fields']['name_ar']['value'] or 'تجريب' in j['fields']['name_ar']['value']) for j in jobs)
fictional=fictional and all(n.lower().startswith(('dummy','fictional','test')) for n in names)
if fictional:
    archive=results/('fictional-workspace-'+time.strftime('%Y%m%d-%H%M%S'));archive.mkdir()
    for name in ['workspace.sqlite3','sources','outputs','cache']:
        p=DATA/name
        if p.exists():shutil.move(str(p),str(archive/name))
    initialize()
# Remove only unused model software downloaded into this app's own namespace.
client=build_opener(ProxyHandler({}))
for model in ['qwen3-vl:2b','qwen3-vl:4b']:
    req=Request(ENGINE_URL+'/api/delete',data=json.dumps({'model':model}).encode(),headers={'Content-Type':'application/json'},method='DELETE')
    try:client.open(req,timeout=15).read()
    except Exception:pass
stop_owned_engine();start_engine(wait=30)
launch()
report={'version':__version__,'date':time.strftime('%Y-%m-%d'),'mac_app':'built and tested','templates':list(registry()),'local_ai':'tested with fictional offer and passport image','privacy':json.loads((results/'privacy-check.json').read_text()),'browser':json.loads((results/'browser-smoke.json').read_text())['browser_errors'],'test_fixtures_archived':fictional,'url':base,'model':status()['model'],'manual_confirmation_required':True}
(results/'acceptance.json').write_text(json.dumps(report,indent=2))
subprocess.run(['/usr/bin/open',str(ROOT/'Private Contracts.app')],check=True)
print(json.dumps(report),flush=True)
