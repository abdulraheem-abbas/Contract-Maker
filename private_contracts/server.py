from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs,quote
from zipfile import ZipFile,ZIP_DEFLATED
from io import BytesIO
from copy import deepcopy
import base64
import hashlib
import html
import json
import mimetypes
import os
import re
import secrets
import threading
import traceback
import uuid
import webbrowser
import time
from .config import DATA,ROOT,RESOURCES,ALLOWED_EXTENSIONS,initialize
from .fields import FIELDS,FIELD_KEYS,empty_fields,validate,required_fields
from . import store
from .readers import read_file,page_image,tesseract_binary,ocr_image
from .office import office_binary,to_pdf
from .engine import status as engine_status,start_engine,EngineError
from .extract import extract_source,merge_candidates,apply_rules
from .templates import registry,generate,template_requirements,validate_template
from . import __version__
from .review import review_contract
from .privacy import install_network_guard
from . import template_manager

TASKS={}
TASK_LOCK=threading.Lock()
AI_LOCK=threading.Lock()
SESSION=secrets.token_urlsafe(32)
CSRF=secrets.token_urlsafe(32)

def rules():
    path=DATA/'rules.json'
    return json.loads(path.read_text()) if path.exists() else {'job_title_overrides':[]}

def public_source(source):
    result={k:v for k,v in source.items() if k not in {'path'}}
    result['pages']=[{k:v for k,v in p.items() if k not in {'path','pdf'}} for p in source['pages']]
    return result

def full_job(job_id):
    job=store.get_job(job_id)
    job['source_details']=[public_source(store.get_source(s)) for s in job.get('sources',[])]
    return job

def verify_sources(job):
    for source_id in job.get('sources',[]):
        source=store.get_source(source_id)
        if hashlib.sha256(Path(source['path']).read_bytes()).hexdigest()!=source['sha256']:
            raise ValueError('A local source copy changed after import. Re-import that document and confirm its fields again.')

def run_task(label,operation,job_id=None):
    task_id=uuid.uuid4().hex
    cancel=threading.Event()
    with TASK_LOCK:
        if job_id and any(t.get('job')==job_id and t['status']=='running' for t in TASKS.values()):raise ValueError('This workspace already has an operation running. Wait for it to finish.')
        TASKS[task_id]={'id':task_id,'job':job_id,'label':label,'status':'running','message':label,'cancel':cancel,'created':time.time()}
    def progress(message):
        TASKS[task_id]['message']=message
    def work():
        try:
            result=operation(progress,cancel.is_set)
            TASKS[task_id].update(status='cancelled' if cancel.is_set() else 'complete',result=result,message='Cancelled' if cancel.is_set() else 'Complete')
        except Exception as exc:
            TASKS[task_id].update(status='error',message=str(exc) if isinstance(exc,(ValueError,EngineError)) else 'This operation could not finish. Your originals were preserved.')
            # Diagnostic logs deliberately exclude document bodies and prompts.
            with (DATA/'logs/app.log').open('a') as log:
                log.write(f'{store.now()} {type(exc).__name__} in {label}\n')
    threading.Thread(target=work,daemon=True).start()
    return {'task':task_id}

def save_input_fields(job,payload):
    for key,value in payload.get('fields',{}).items():
        if key not in FIELD_KEYS or not isinstance(value,dict):
            continue
        entered=str(value.get('value',''))[:1200]
        existing=job['fields'][key]
        if entered!=existing.get('value',''):
            existing.update(value=entered,origin='entered by you',confirmed=False)
        existing['confirmed']=bool(value.get('confirmed',False))
    job['employee_hint']=str(payload.get('employee_hint',job.get('employee_hint','')))[:200]
    job['list_row']=str(payload.get('list_row',job.get('list_row','')))[:30]
    job['title']=job['fields']['name_en']['value'] or job['fields']['name_ar']['value'] or job.get('title','New contract')
    return store.save_job(job)

def report_html(job,findings):
    name=job['fields']['name_ar']['value'] or job['fields']['name_en']['value'] or job['title']
    rows=''.join('<tr><td>'+html.escape(f['level'].upper())+'</td><td>'+html.escape(f.get('field',''))+'</td><td>'+html.escape(f.get('contract',''))+'</td><td>'+html.escape(str(f.get('page') or f.get('location') or '—'))+'</td><td>'+html.escape(f['message'])+'</td></tr>' for f in findings)
    return '<!doctype html><html><head><meta charset="utf-8"><title>Contract review</title><link rel="stylesheet" href="/report.css"></head><body><h1>Contract review</h1><p dir="auto">'+html.escape(name)+'</p><p>Created locally on '+html.escape(store.now()[:10])+'. Findings compare expected fields and available source text. Unconfirmed expectations and visual layout still need inspection.</p><table><thead><tr><th>Result</th><th>Field</th><th>Contract</th><th>Location</th><th>Finding</th></tr></thead><tbody>'+rows+'</tbody></table></body></html>'

class AppServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True

class Handler(BaseHTTPRequestHandler):
    server_version='PrivateContracts'
    def log_message(self,*args):
        pass

    @property
    def origin(self):
        return f'http://127.0.0.1:{self.server.server_port}'

    def check_host(self):
        return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'

    def send_common_headers(self,content_type='application/json; charset=utf-8',status=200,length=None):
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Cross-Origin-Resource-Policy','same-origin')
        self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; font-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        if length is not None:self.send_header('Content-Length',str(length))

    def respond(self,value,status=200):
        data=json.dumps(value,ensure_ascii=False).encode()
        self.send_common_headers(status=status,length=len(data));self.end_headers();self.wfile.write(data)

    def binary(self,data,content_type,name=None):
        self.send_common_headers(content_type,length=len(data))
        if name:self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(name))
        self.end_headers();self.wfile.write(data)

    def authenticated(self):
        cookie=self.headers.get('Cookie','')
        return any(c.strip()==f'private_contracts={SESSION}' for c in cookie.split(';'))

    def do_GET(self):
        if not self.check_host():
            return self.respond({'error':'Only the local app address is accepted.'},403)
        parts=urlparse(self.path);route=parts.path;q=parse_qs(parts.query)
        arg=lambda key,default='':q.get(key,[default])[0]
        try:
            if route=='/':
                content=(RESOURCES/'web/index.html').read_bytes()
                self.send_common_headers('text/html; charset=utf-8',length=len(content))
                self.send_header('Set-Cookie',f'private_contracts={SESSION}; HttpOnly; SameSite=Strict; Path=/')
                self.end_headers();self.wfile.write(content);return
            if route in {'/app.js','/app.css','/icon.svg','/report.css'}:
                p=RESOURCES/'web'/route[1:]
                return self.binary(p.read_bytes(),mimetypes.guess_type(str(p))[0] or 'application/octet-stream')
            if route=='/favicon.ico':
                return self.binary((RESOURCES/'web/icon.svg').read_bytes(),'image/svg+xml')
            if route=='/api/ping':return self.respond({'application':'Private Contracts','data_id':hashlib.sha256(str(DATA).encode()).hexdigest()})
            if not self.authenticated():
                return self.respond({'error':'Open Private Contracts in its own window first.'},403)
            if route=='/api/bootstrap':
                return self.respond({'csrf':CSRF,'jobs':store.jobs(),'fields':FIELDS,'templates':{k:{**{a:b for a,b in v.items() if a in {'label','sha256','placeholders','ready','version','source_name','saved_at'}},'history_count':len(v.get('history',[])),'required_fields':sorted(template_requirements(v))} for k,v in registry().items()},'engine':engine_status(),'ocr':bool(tesseract_binary()),'pdf_export':bool(office_binary()),'rules':rules(),'version':__version__})
            if route=='/api/status':
                result=engine_status()
                download=DATA/'download-status.json'
                if download.exists():result['download']=json.loads(download.read_text())
                return self.respond(result)
            if route=='/api/job':return self.respond(full_job(arg('id')))
            if route=='/api/task':
                task=TASKS.get(arg('id'))
                if not task:return self.respond({'error':'Task not found.'},404)
                return self.respond({k:v for k,v in task.items() if k!='cancel'})
            if route=='/api/page':
                source=store.get_source(arg('source'))
                index=int(arg('page','1'))-1
                if not 0<=index<len(source['pages']):raise ValueError('Page not found.')
                picture=page_image(source,index,max_side=1800)
                if picture:return self.binary(picture,'image/jpeg')
                return self.respond({'text':source['pages'][index]['text']})
            if route=='/api/file':
                job=store.get_job(arg('job'));name=arg('name')
                if name not in job.get('outputs',[]):raise ValueError('Output not found.')
                p=DATA/'outputs'/job['id']/name
                return self.binary(p.read_bytes(),mimetypes.guess_type(name)[0] or 'application/octet-stream',name if arg('download')=='1' else None)
            if route=='/api/bundle':
                job=store.get_job(arg('job'));buffer=BytesIO()
                with ZipFile(buffer,'w',ZIP_DEFLATED) as z:
                    for name in job.get('outputs',[]):
                        z.write(DATA/'outputs'/job['id']/name,name)
                return self.binary(buffer.getvalue(),'application/zip','Contract package.zip')
            if route=='/api/template-editor':
                return self.respond(template_manager.describe(arg('kind'),arg('draft') or None))
            if route=='/api/template-file':
                kind=arg('kind');pdf=arg('format')=='pdf'
                p=template_manager.file_path(kind,arg('draft') or None,arg('version') or None,pdf,arg('sha') or None)
                return self.binary(p.read_bytes(),'application/pdf' if pdf else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',None if pdf else kind+' template.docx')
            if route=='/api/template-page':
                p=template_manager.file_path(arg('kind'),arg('draft') or None,pdf=True,expected_sha=arg('sha') or None)
                index=int(arg('page','1'))
                if not 1<=index<=120:raise ValueError('Template page not found.')
                picture=p.with_name(f'page-{index:04d}.jpg')
                if not picture.is_file():raise ValueError('Create the template preview first.')
                return self.binary(picture.read_bytes(),'image/jpeg')
            return self.respond({'error':'Not found.'},404)
        except (ValueError,KeyError,IndexError,OSError) as exc:
            return self.respond({'error':str(exc)},400)

    def do_POST(self):
        if not self.check_host() or not self.authenticated() or self.headers.get('Origin')!=self.origin or not secrets.compare_digest(self.headers.get('X-Private-CSRF',''),CSRF):
            return self.respond({'error':'A request from outside this local app was refused.'},403)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<1 or length>48*1024*1024:raise ValueError('Choose files up to 25 MB each.')
            payload=json.loads(self.rfile.read(length))
            if not isinstance(payload,dict):raise ValueError('Invalid request.')
            route=urlparse(self.path).path
            if route=='/api/new':
                fields=empty_fields();kind=payload.get('kind','employment')
                if kind not in {'employment','service','extension'}:raise ValueError('Choose a supported contract type.')
                fields['contract_type']={'value':kind,'confirmed':True,'origin':'chosen by you','evidence':[]}
                job={'id':uuid.uuid4().hex,'title':'New '+kind+' contract','mode':'review' if payload.get('mode')=='review' else 'create','fields':fields,'sources':[],'findings':[],'outputs':[],'created':store.now(),'employee_hint':'','list_row':''}
                store.save_job(job);store.audit(job['id'],'workspace_created',{'mode':job['mode'],'kind':kind})
                return self.respond(job)
            if route=='/api/save':
                return self.respond(save_input_fields(store.get_job(payload['job']),payload))
            if route=='/api/import':
                job_id=payload['job'];store.get_job(job_id)
                name=Path(str(payload['name']).replace('\\','/')).name
                suffix=Path(name).suffix.lower()
                if suffix not in ALLOWED_EXTENSIONS:raise ValueError('Choose a PDF, Word document, image, ODS, XLSX, CSV or text file.')
                role=payload.get('role','offer')
                if role not in {'offer','identity','list','contract'}:raise ValueError('Choose the document role.')
                raw=base64.b64decode(payload['data'],validate=True)
                if len(raw)>25*1024*1024:raise ValueError('Choose files up to 25 MB each.')
                path=DATA/'sources'/(uuid.uuid4().hex+suffix)
                path.write_bytes(raw)
                def import_work(progress,cancelled):
                    progress('Reading your selected file locally')
                    pages=read_file(path)
                    source=store.add_source(name,role,path,pages)
                    job=store.get_job(job_id);job['sources'].append(source['id']);store.save_job(job)
                    store.audit(job_id,'source_added',{'source':source['id'],'sha256':source['sha256'],'role':role})
                    return {'job':job_id,'source':source['id']}
                return self.respond(run_task('Importing document',import_work,job_id))
            if route=='/api/extract':
                job_id=payload['job'];save_input_fields(store.get_job(job_id),payload)
                def extract_work(progress,cancelled):
                    if not AI_LOCK.acquire(blocking=False):raise ValueError('The local model is already working. Wait for that task to finish.')
                    try:
                        job=store.get_job(job_id);all_candidates=[]
                        for source_id in job['sources']:
                            source=store.get_source(source_id)
                            if source['role']=='contract':continue
                            if cancelled():break
                            all_candidates.extend(extract_source(source,job.get('employee_hint',''),job.get('list_row',''),progress,cancelled))
                        job=store.get_job(job_id)
                        conflicts=merge_candidates(job['fields'],all_candidates)
                        apply_rules(job['fields'],rules())
                        job['conflicts']=conflicts
                        job['title']=job['fields']['name_en']['value'] or job['fields']['name_ar']['value'] or job['title']
                        store.save_job(job);store.audit(job_id,'local_extraction',{'candidate_count':len(all_candidates),'conflicts':len(conflicts)})
                        return {'job':job_id,'candidates':len(all_candidates),'conflicts':len(conflicts)}
                    finally:AI_LOCK.release()
                return self.respond(run_task('Reading documents with local AI',extract_work,job_id))
            if route=='/api/cancel':
                task=TASKS.get(payload['task'])
                if task:task['cancel'].set()
                return self.respond({'ok':True})
            if route=='/api/check':
                job=save_input_fields(store.get_job(payload['job']),payload)
                job['findings']=validate(job['fields'])
                existing={i['field'] for i in job['findings']}
                job['findings'].extend(i for i in validate_template(job['fields'],registry().get(job['fields']['contract_type']['value'],{})) if i['field'] not in existing)
                store.save_job(job)
                return self.respond({'findings':job['findings']})
            if route=='/api/review':
                job=save_input_fields(store.get_job(payload['job']),payload);job_id=job['id']
                def review_work(progress,cancelled):
                    job=store.get_job(job_id)
                    verify_sources(job)
                    sources=[store.get_source(s) for s in job['sources']]
                    contracts=[s for s in sources if s['role']=='contract']
                    if not contracts:raise ValueError('Add the existing contract using the Contract to review card.')
                    kind=job['fields']['contract_type']['value'];entry=registry().get(kind,{})
                    findings=[]
                    for source in contracts:
                        progress('Comparing the contract with your expected fields')
                        for index,page in enumerate(source['pages']):
                            if cancelled():return {'job':job_id}
                            if page.get('ocr_needed') and page.get('image'):
                                progress(f'Reading scanned contract page {index+1} locally')
                                picture=page_image(source,index)
                                recognized=ocr_image(picture) if picture else ''
                                if recognized:page.update(text=recognized,ocr_used=True)
                        findings.extend(dict(f,contract=source['name']) for f in review_contract(job,source,entry.get('path')))
                    job['findings']=findings
                    out=DATA/'outputs'/job_id;out.mkdir(exist_ok=True)
                    (out/'Review notes.html').write_text(report_html(job,findings))
                    (out/'Review evidence.json').write_text(json.dumps({'fields':job['fields'],'findings':findings},ensure_ascii=False,indent=2))
                    for name in ['Review notes.html','Review evidence.json']:
                        if name not in job['outputs']:job['outputs'].append(name)
                    store.save_job(job);store.audit(job_id,'contract_reviewed',{'findings':len(findings),'errors':sum(f['level']=='error' for f in findings)})
                    return {'job':job_id}
                return self.respond(run_task('Reviewing contract',review_work,job_id))
            if route=='/api/generate':
                job=save_input_fields(store.get_job(payload['job']),payload);job_id=job['id']
                template_entry,_=template_manager.active(job['fields']['contract_type']['value'],payload.get('template_sha'))
                problems=validate(job['fields'],require_confirmation=True)
                existing={i['field'] for i in problems}
                problems.extend(i for i in validate_template(job['fields'],template_entry,True) if i['field'] not in existing)
                errors=[p for p in problems if p['level']=='error']
                if errors:return self.respond({'error':'Complete and confirm the required fields first.','findings':errors},400)
                warnings=[p for p in problems if p['level']=='warning']
                if warnings and not payload.get('acknowledge_warnings'):
                    return self.respond({'error':'Acknowledge the flagged dates or expiry before creating this contract.','findings':warnings},400)
                confirmed_snapshot=deepcopy(job['fields'])
                def generate_work(progress,cancelled):
                    job=store.get_job(job_id)
                    job['fields']=confirmed_snapshot
                    verify_sources(job)
                    kind=job['fields']['contract_type']['value'];entry=template_entry
                    template=entry.get('path')
                    if not template or not Path(template).exists():raise ValueError('Prepare this template in Templates before generating a contract.')
                    if hashlib.sha256(Path(template).read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('The template has changed outside the app. Re-import it before generation.')
                    # Protect previous output revisions instead of overwriting them.
                    revision=1+sum(name.endswith('.docx') for name in job['outputs'])
                    name=job['fields']['name_ar']['value'] or job['fields']['name_en']['value']
                    name=re.sub(r'[\\/:*?"<>|\x00-\x1f]','-',name).strip()[:120]
                    prefix={'employment':'عقد عمل','service':'عقد خدمة','extension':'خطاب تمديد'}[kind]
                    stem=f'{prefix} - {name} - v{revision}'
                    out=DATA/'outputs'/job_id;out.mkdir(exist_ok=True)
                    docx=out/(stem+'.docx')
                    progress('Filling the approved Word template')
                    verification=generate(template,job['fields'],docx)
                    verification['template']={k:v for k,v in entry.items() if k in {'label','sha256','version','source_name','saved_at'}}
                    outputs=[docx.name];pdf_error=None
                    try:
                        progress('Creating the PDF locally and checking its pages')
                        pdf=to_pdf(docx,out);outputs.append(pdf.name)
                        pages=read_file(pdf)
                        low_text=[p['number'] for p in pages if len(p['text'].strip())<12]
                        verification.update(pdf_pages=len(pages),pages_to_inspect=low_text)
                    except Exception:
                        pdf_error='PDF export did not complete; your Word file was saved.'
                    verification['sources']=[{'name':s['name'],'role':s['role'],'sha256':s['sha256']} for s in [store.get_source(i) for i in job['sources']]]
                    verification['confirmed_fields']=job['fields']
                    verification['visual_review_required']=True
                    verification['pdf_error']=pdf_error
                    audit_name=stem+' - evidence.json'
                    (out/audit_name).write_text(json.dumps(verification,ensure_ascii=False,indent=2));outputs.append(audit_name)
                    job['outputs'].extend(outputs);job['findings']=warnings
                    job['last_generation']=verification;store.save_job(job)
                    store.audit(job_id,'contract_generated',{'revision':revision,'outputs':outputs,'verification':{k:v for k,v in verification.items() if k not in {'confirmed_fields','sources'}}})
                    return {'job':job_id,'pdf_error':pdf_error}
                return self.respond(run_task('Creating contract',generate_work,job_id))
            if route=='/api/start-engine':
                return self.respond(run_task('Starting local AI',lambda progress,cancelled:start_engine(wait=30)))
            if route=='/api/shutdown':
                if any(t['status']=='running' for t in TASKS.values()):raise ValueError('Wait for the current operation to finish before quitting.')
                self.respond({'ok':True})
                threading.Thread(target=self.server.shutdown,daemon=True).start()
                return
            if route=='/api/template-save':
                return self.respond(template_manager.map_fields(payload['kind'],payload.get('draft'),payload['expected_sha'],payload.get('mappings')))
            if route=='/api/template-import':
                raw=base64.b64decode(payload['data'],validate=True)
                return self.respond(template_manager.stage(payload['kind'],str(payload['name']),raw,payload['expected_sha']))
            if route=='/api/template-activate':
                return self.respond(template_manager.activate(payload['kind'],payload['draft'],payload['expected_sha'],payload.get('reviewed')))
            if route=='/api/template-restore':
                return self.respond(template_manager.restore_draft(payload['kind'],payload['version'],payload['expected_sha']))
            if route=='/api/template-preview':
                kind=payload['kind'];draft=payload.get('draft')
                # Capture the path before dispatch; drafts and saved versions are immutable.
                source=template_manager.file_path(kind,draft,expected_sha=payload.get('expected_sha'))
                return self.respond(run_task('Creating template preview',lambda progress,cancelled:template_manager.preview(kind,draft,progress,cancelled,source)))
            return self.respond({'error':'Not found.'},404)
        except (ValueError,KeyError,IndexError,OSError) as exc:
            return self.respond({'error':str(exc)},400)
        except Exception:
            return self.respond({'error':'This action could not finish. Your originals were preserved.'},500)

def serve(port=0,open_browser=True):
    initialize()
    install_network_guard()
    server=AppServer(('127.0.0.1',port),Handler)
    url=f'http://127.0.0.1:{server.server_port}'
    (DATA/'app-address.json').write_text(json.dumps({'url':url,'pid':os.getpid()}))
    if open_browser:threading.Timer(.5,lambda:webbrowser.open(url)).start()
    if __import__('sys').stdout is not None:print(url,flush=True)
    try:server.serve_forever()
    finally:
        server.server_close()
        try:(DATA/'app-address.json').unlink()
        except OSError:pass
