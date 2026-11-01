"""Loopback-only integration checks; uses fictional employee records only."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from urllib.request import build_opener,HTTPCookieProcessor,Request,ProxyHandler
from urllib.error import HTTPError
from http.cookiejar import CookieJar
from zipfile import ZipFile
from io import BytesIO
import base64,json,time
from private_contracts.templates import parse,paragraph_at,replace_value,text,NS
from lxml import etree

root=Path(__file__).resolve().parent.parent
base='http://127.0.0.1:8768'
client=build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()))
client.open(base).read()
boot=json.load(client.open(base+'/api/bootstrap'))
def post(route,payload,headers=None):
    h={'Content-Type':'application/json','Origin':base,'X-Private-CSRF':boot['csrf']}
    if headers:h.update(headers)
    return json.load(client.open(Request(base+route,data=json.dumps(payload).encode(),headers=h)))
def wait(task):
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        status=json.load(client.open(base+'/api/task?id='+task))
        if status['status']=='error':raise RuntimeError(status['message'])
        if status['status']=='complete':return status
        time.sleep(.25)
    raise RuntimeError('Local integration operation timed out')
def rejected(action,code):
    try:action()
    except HTTPError as exc:assert exc.code==code
    else:raise AssertionError('Request should have been rejected')

rejected(lambda:build_opener(ProxyHandler({})).open(base+'/api/bootstrap'),403)
rejected(lambda:client.open(Request(base+'/api/bootstrap',headers={'Host':'untrusted.example'})),403)
rejected(lambda:post('/api/new',{}, {'Origin':'https://untrusted.example'}),403)
rejected(lambda:post('/api/new',{}, {'X-Private-CSRF':'wrong'}),403)
create=json.loads((root/'test-results/browser-smoke.json').read_text())
job=json.load(client.open(base+'/api/job?id='+create['created_job']))
source_name=next(n for n in job['outputs'] if n.endswith('.docx'))
original=client.open(base+'/api/file?job='+job['id']+'&name='+__import__('urllib.parse',fromlist=['quote']).quote(source_name)).read()
with ZipFile(BytesIO(original)) as z:contents={n:z.read(n) for n in z.namelist()}
document=parse(contents['word/document.xml'])
replace_value(paragraph_at(document,(7,1,4)),'825.69','925.69')
# A deliberate fixed-clause mutation, separate from employee data.
p=paragraph_at(document,(5,0,0))
run=etree.SubElement(p,'{'+NS['w']+'}r');etree.SubElement(run,'{'+NS['w']+'}t').text=' DELIBERATE TEST CHANGE'
contents['word/document.xml']=etree.tostring(document)
buffer=BytesIO()
with ZipFile(buffer,'w') as z:
    for n,b in contents.items():z.writestr(n,b)
review=post('/api/new',{'mode':'review','kind':'employment'})
post('/api/save',{'job':review['id'],'fields':job['fields']})
wait(post('/api/import',{'job':review['id'],'role':'contract','name':'Dummy contract with deliberate errors.docx','data':base64.b64encode(buffer.getvalue()).decode()})['task'])
wait(post('/api/review',{'job':review['id'],'fields':job['fields']})['task'])
review=json.load(client.open(base+'/api/job?id='+review['id']))
assert any(f['level']=='error' and f['field']=='salary_usd' and 'Arabic' in f.get('location','') for f in review['findings'])
assert any(f['field']=='clauses' and f.get('location') for f in review['findings'])
rejected(lambda:client.open(base+'/api/file?job='+review['id']+'&name=../../workspace.sqlite3'),400)
unconfirmed=job['fields'].copy();unconfirmed['identity_number']={**unconfirmed['identity_number'],'confirmed':False}
rejected(lambda:post('/api/generate',{'job':review['id'],'fields':unconfirmed}),400)
expired={k:v.copy() for k,v in job['fields'].items()};expired['identity_expiry_date']['value']='2024-06-01'
rejected(lambda:post('/api/generate',{'job':review['id'],'fields':expired}),400)
reading=post('/api/new',{'mode':'create','kind':'employment'})
fixture=b'DEMONSTRATION ONLY. Employment offer. Offer date: 1 October 2026. Start: 4 October 2026. End: 31 December 2026. Job title: Education Assistant. Gross monthly salary USD 825.69.'
wait(post('/api/import',{'job':reading['id'],'role':'offer','name':'Fictional offer for end-to-end reading.txt','data':base64.b64encode(fixture).decode()})['task'])
wait(post('/api/extract',{'job':reading['id']})['task'])
reading=json.load(client.open(base+'/api/job?id='+reading['id']))
for key,expected in {'execution_date':'2026-10-01','start_date':'2026-10-04','end_date':'2026-12-31','salary_usd':'825.69'}.items():
    assert reading['fields'][key]['value']==expected and not reading['fields'][key]['confirmed']
summary={'origin_host_cookie_csrf_checks':'passed','path_traversal':'blocked','unconfirmed_generation':'blocked','expiry_without_acknowledgement':'blocked','arabic_salary_error':'detected','changed_fixed_clause':'detected','local_reading_through_interface':'passed; suggestions remain unconfirmed','review_job':review['id'],'findings_count':len(review['findings'])}
(root/'test-results/api-checks.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary))
