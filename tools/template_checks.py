"""Test template changes and generation in a disposable fictional workspace."""
import base64
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener, ProxyHandler, HTTPCookieProcessor, Request

ROOT=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_templates import word
from test_core import fields
from private_contracts.template_manager import inspect,digest

results=ROOT/'test-results';results.mkdir(exist_ok=True)
paragraphs=[
    'DEMONSTRATION ONLY · Contract template','Employee: {{name_en}}','الموظف: {{name_ar}}',
    'Date: {{execution_en}} — {{weekday_en}}','التاريخ: {{execution_ar}} — {{weekday_ar}}',
    'Term: {{start_en}} to {{end_en}}','الفترة: {{start_ar}} إلى {{end_ar}}',
    'Identity: {{identity_details_en}}','الهوية: {{identity_details_ar}}',
    'Role: {{job_title_en}} | {{workplace_en}}','الوظيفة: {{job_title_ar}} | {{workplace_ar}}',
    'Grade: {{grade_en}} | {{grade_ar}}','Reports to: {{manager_title_en}} | {{manager_title_ar}}',
    'Salary (English): USD {{salary_usd}}','الراتب: {{salary_usd}} دولار',
    'Signed by: {{name_en}} / {{name_ar}}',
]
with tempfile.TemporaryDirectory(prefix='contract-template-check-') as temporary:
    data=Path(temporary)/'data';entries={}
    for kind in ['employment','service','extension']:
        path=data/'templates'/kind/'template.docx';path.parent.mkdir(parents=True)
        raw=word(paragraphs);path.write_bytes(raw)
        entries[kind]={'label':kind.title(),'path':str(path),'sha256':digest(raw),'placeholders':inspect(raw)['placeholders']}
    (data/'templates/registry.json').write_text(json.dumps(entries))
    replacement=Path(temporary)/'replacement.docx'
    replacement.write_bytes(word([s.replace('DEMONSTRATION ONLY · Contract template','DEMONSTRATION ONLY · Updated approved wording').replace('{{name_ar}}','اسم تجريبي للتعيين') for s in paragraphs]))
    env=dict(os.environ);env['PRIVATE_CONTRACTS_DATA']=str(data)
    client=build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()))
    base=None;boot=None
    with (results/'template-test-server.log').open('w') as log:
        process=subprocess.Popen([sys.executable,str(ROOT/'run.py'),'--no-browser','--port','0'],cwd=ROOT,env=env,stdout=log,stderr=log)
        def post(route,payload):
            return json.load(client.open(Request(base+route,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Origin':base,'X-Private-CSRF':boot['csrf']}),timeout=30))
        def wait(task):
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                item=json.load(client.open(base+'/api/task?id='+task,timeout=5))
                if item['status']=='error':raise RuntimeError(item['message'])
                if item['status']=='complete':return item['result']
                time.sleep(.2)
            raise RuntimeError('The local check timed out.')
        try:
            for _ in range(80):
                if process.poll() is not None:raise RuntimeError('The temporary app could not start.')
                if (data/'app-address.json').exists():
                    base=json.loads((data/'app-address.json').read_text())['url'];break
                time.sleep(.1)
            if not base:raise RuntimeError('The temporary app did not become ready.')
            client.open(base).read();boot=json.load(client.open(base+'/api/bootstrap'))
            (results/'template-ui-config.json').write_text(json.dumps({'data':str(data),'replacement':str(replacement),'base':base}))
            node=shutil.which('node') or str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node')
            subprocess.run([node,str(ROOT/'tools/browser_templates.cjs')],cwd=ROOT,check=True)
            boot=json.load(client.open(base+'/api/bootstrap'))
            entry=boot['templates']['employment']
            job=post('/api/new',{'kind':'employment','mode':'create'})
            done=wait(post('/api/generate',{'job':job['id'],'fields':fields(),'template_sha':entry['sha256']})['task'])
            assert not done.get('pdf_error')
            job=json.load(client.open(base+'/api/job?id='+job['id']))
            assert job['last_generation']['template']['version']==entry['version']
            assert job['last_generation']['template']['sha256']==entry['sha256']
            assert job['last_generation']['template_text_preserved']
            filename=next(n for n in job['outputs'] if n.endswith('.docx'))
            raw=(data/'outputs'/job['id']/filename).read_bytes()
            review=post('/api/new',{'kind':'employment','mode':'review'})
            wait(post('/api/import',{'job':review['id'],'role':'contract','name':'Test generated contract.docx','data':base64.b64encode(raw).decode()})['task'])
            wait(post('/api/review',{'job':review['id'],'fields':fields()})['task'])
            review=json.load(client.open(base+'/api/job?id='+review['id']))
            assert not [f for f in review['findings'] if f['level']=='error']
            report={'generation_after_template_change':'Word and PDF passed','template_version_in_evidence':'passed','review_with_custom_layout':'no errors','workspace':'disposable fictional data only'}
            (results/'template-generation-check.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
        finally:
            if base and boot:
                try:post('/api/shutdown',{})
                except OSError:pass
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=5)
