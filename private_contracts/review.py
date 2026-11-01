from datetime import date
import hashlib
import re
from .fields import validate,compact,normalize,LABELS,date_display,identity_date,weekday,required_fields
from .readers import docx_paragraphs
from .templates import parse,text,NS,TOKEN,render_values,paragraph_at,template_requirements
from zipfile import ZipFile

def variations(key,value):
    results=[value]
    if key.endswith('_date'):
        try:
            results.extend([date_display(value,'ar'),date_display(value,'en'),identity_date(value),date.fromisoformat(value).strftime('%Y/%m/%d')])
        except ValueError:
            pass
    return [compact(v) for v in results if v]

def find_value(source,key,value):
    needles=variations(key,value)
    found=[]
    for page in source['pages']:
        body=compact(page['text'])
        for needle in needles:
            # PDF native extraction sometimes reverses Arabic reading order.
            if needle in body or (re.search('[\u0600-\u06ff]',value) and needle[::-1] in body):
                found.append(page['number']);break
    return found

def review_contract(job,source,template_path=None):
    fields=job['fields'];findings=[]
    kind=fields.get('contract_type',{}).get('value','employment')
    text_source='\n'.join(p['text'] for p in source['pages'])
    native_text=''.join(docx_paragraphs(source['path'])) if source['path'].lower().endswith('.docx') else ''
    if max(len(text_source.strip()),len(native_text.strip()))<60:
        findings.append({'level':'warning','field':'document','page':1,'message':'This contract is scanned. Read it with local AI first, then compare its fields and page images. Text absence is not proof that a field is missing.'})
    for issue in validate(fields):
        findings.append(dict(issue,page=None))
    pending=[LABELS.get(k,k) for k in required_fields(kind) if fields.get(k,{}).get('value') and not fields[k].get('confirmed')]
    if pending:
        findings.append({'level':'warning','field':'sources','page':None,'message':'Expected values still need confirmation against their sources: '+', '.join(pending)+'.'})
    if any(p.get('ocr_used') for p in source['pages']):
        findings.append({'level':'warning','field':'document','page':None,'message':'Some comparisons use local OCR. Inspect those page images for recognition errors, especially names and identity numbers.'})
    keyset=required_fields(kind)|{'issuer_ar','issuer_en'}
    if template_path:
        with ZipFile(template_path) as z:configured=parse(z.read('word/document.xml'))
        keyset|=template_requirements({'placeholders':TOKEN.findall(text(configured))})
    keyset-={'contract_type','identity_type','gender'}
    if max(len(text_source.strip()),len(native_text.strip()))<60:keyset=set()
    if source['path'].lower().endswith('.pdf'):
        findings.append({'level':'warning','field':'document','page':None,'message':'PDF text matches are document-wide. Inspect both language columns and repeated signature fields. Upload the Word version for language-specific field checks and fixed-wording comparisons.'})
    for key in sorted(keyset):
        value=fields.get(key,{}).get('value','')
        if not value:
            continue
        hits=find_value(source,key,value)
        native_match=bool(native_text) and any(v in compact(native_text) for v in variations(key,value))
        if not hits and native_match:
            findings.append({'level':'pass','field':key,'page':None,'message':f'{LABELS.get(key,key)} found in the original Word text; page not determined.','expected':value})
        elif not hits:
            findings.append({'level':'error','field':key,'page':None,'message':f'{LABELS.get(key,key)} does not match the expected value in the readable contract text.','expected':value})
        else:
            findings.append({'level':'pass','field':key,'page':hits[0],'pages':hits,'message':f'{LABELS.get(key,key)} found.','expected':value})
    execution=fields.get('execution_date',{}).get('value','')
    if execution:
        try:
            for language in ['ar','en']:
                day=weekday(execution,language)
                if not find_value(source,'weekday',day):
                    findings.append({'level':'warning','field':'execution_date','page':1,'message':f'The expected weekday {day} was not found. Check the contract date line.'})
        except ValueError:
            pass
    for page in source['pages']:
        if page.get('kind')=='pdf' and len(page['text'].strip())<12:
            findings.append({'level':'warning','field':'layout','page':page['number'],'message':'This page has little readable text. Inspect it for a blank page or a scanned signature.'})
    if kind=='employment':
        for language in ['ar','en']:
            manager=fields.get('manager_name_'+language,{}).get('value','')
            if manager and find_value(source,'manager',manager):
                findings.append({'level':'warning','field':'manager_name_'+language,'page':2,'message':'A reporting manager personal name appears. Employment contracts should show the manager title only.'})
        if re.search(r'في مشروع',text_source):
            findings.append({'level':'warning','field':'job_title_ar','page':2,'message':'A project phrase appears. Check that clause 3.1 contains only the employee job title.'})
    # Verify each language and repeated signature fields independently when the
    # known NMO Word table structure is present. A correct salary on one side
    # must not hide an incorrect salary on the other side.
    if source['path'].lower().endswith('.docx'):
        with ZipFile(source['path']) as z:document=parse(z.read('word/document.xml'))
        rows=document.findall('w:body/w:tbl/w:tr',NS)
        if kind in {'employment','service'} and len(rows) in {9,22}:
            actual_kind='service' if len(rows)==9 else 'employment'
            if actual_kind!=kind:
                findings.append({'level':'error','field':'contract_type','page':1,'message':'The contract uses the other template type.'})
            def check_slot(key,slot,location,expected=None):
                value=expected if expected is not None else fields.get(key,{}).get('value','')
                if not value:return
                body=text(paragraph_at(document,slot))
                if not any(v in compact(body) for v in variations(key,value)):
                    findings.append({'level':'error','field':key,'page':None,'location':location,'message':f'{LABELS.get(key,key)} differs in {location}.','expected':value})
            for col,lang in ([(0,'en'),(1,'ar')] if actual_kind=='employment' else [(0,'ar'),(1,'en')]):
                identity=(0,col,8 if lang=='ar' and actual_kind=='employment' else 4 if actual_kind=='employment' else 3)
                language='Arabic' if lang=='ar' else 'English'
                for key in ['name_'+lang,'identity_number','identity_issue_date','issuer_'+lang]:
                    check_slot(key,identity,f'{language} employee identity paragraph')
                identity_value=fields.get('identity_type',{}).get('value','')
                if lang=='en':
                    check_slot('gender',identity,'English employee honorific','Ms.' if fields.get('gender',{}).get('value')=='female' else 'Mr.')
                label=({'passport':'جواز سفر','id_card':'بطاقة شخصية','national_id':'الرقم الوطني'} if lang=='ar' else {'passport':'Passport','id_card':'ID Card','national_id':'National Number'}).get(identity_value,'')
                check_slot('identity_type',identity,f'{language} employee document type',label)
                for key in ['execution_date','start_date','end_date']:
                    check_slot(key,(0,col,1) if key=='execution_date' else (1,col,1),f'{language} '+('contract date' if key=='execution_date' else 'contract term'))
                if execution:
                    try:check_slot('weekday',(0,col,1),f'{language} weekday',weekday(execution,lang))
                    except ValueError:pass
                check_slot('job_title_'+lang,(2,col,1) if actual_kind=='employment' else (2,col,2 if lang=='ar' else 3),f'{language} job title')
                check_slot('workplace_'+lang,(4,col,1) if actual_kind=='employment' else (2,col,1),f'{language} employee workplace')
                check_slot('manager_title_'+lang,(2,col,2) if actual_kind=='employment' else (2,col,3 if lang=='ar' else 4),f'{language} reporting line')
                check_slot('salary_usd',(7,col,4 if lang=='ar' else 2) if actual_kind=='employment' else (4,col,1),f'{language} salary clause')
                if actual_kind=='employment':
                    check_slot('grade_'+lang,(3,col,0),f'{language} grade')
                    dates=[2,7];name_index=5;signrow=21
                else:
                    check_slot('project_'+lang,(2,col,2 if lang=='ar' else 3),f'{language} project')
                    check_slot('manager_name_'+lang,(2,col,3 if lang=='ar' else 4),f'{language} manager name')
                    dates=[5,8] if lang=='ar' else [3,6];name_index=6 if lang=='ar' else 5;signrow=8
                check_slot('name_'+lang,(signrow,col,name_index),f'{language} signature block name')
                for index in dates:check_slot('execution_date',(signrow,col,index),f'{language} signature date')
    # Exact fixed-text comparison is available for Word contracts generated from
    # the configured template. PDFs cannot prove unchanged Word formatting.
    if source['path'].lower().endswith('.docx') and template_path:
        with ZipFile(template_path) as z:
            tr=parse(z.read('word/document.xml'))
        expected=TOKEN.sub(lambda m:render_values(fields).get(m.group(1),m.group(0)),text(tr))
        actual=''.join(docx_paragraphs(source['path']))
        if compact(expected)==compact(actual):
            findings.append({'level':'pass','field':'clauses','page':None,'message':'All fixed template text matches the generated Word contract.'})
        else:
            findings.append({'level':'warning','field':'clauses','page':None,'message':'The Word contract differs from the configured template. Review the fixed clauses and formatting; matching employee fields alone does not prove the remaining text is unchanged.'})
            template_paragraphs=tr.xpath('//w:p',namespaces=NS)
            actual_paragraphs=document.xpath('//w:p',namespaces=NS)
            if len(template_paragraphs)==len(actual_paragraphs):
                for index,(before,after) in enumerate(zip(template_paragraphs,actual_paragraphs)):
                    pattern='^'+'.*?'.join(re.escape(compact(s)) for s in TOKEN.split(text(before))[::2])+'$' if TOKEN.search(text(before)) else '^'+re.escape(compact(text(before)))+'$'
                    if not re.fullmatch(pattern,compact(text(after)),flags=re.S):
                        findings.append({'level':'warning','field':'clauses','page':None,'location':f'Word paragraph {index+1}','message':f'Fixed wording differs in Word paragraph {index+1}. Compare this paragraph with the approved template.'})
            else:
                findings.append({'level':'warning','field':'layout','page':None,'message':'The paragraph structure differs from the approved template. Check inserted or deleted clauses and page breaks.'})
        with ZipFile(template_path) as reference,ZipFile(source['path']) as actual_package:
            parts=[n for n in reference.namelist() if n=='word/styles.xml' or n=='word/numbering.xml' or n.startswith(('word/header','word/footer'))]
            if any(n not in actual_package.namelist() or reference.read(n)!=actual_package.read(n) for n in parts):
                findings.append({'level':'warning','field':'layout','page':None,'message':'Document styles, numbering, headers or footers differ from the configured template. Inspect the visual layout.'})
    error_fields={finding['field'] for finding in findings if finding['level']=='error'}
    return [finding for finding in findings if not(finding['level']=='pass' and finding['field'] in error_fields)]
