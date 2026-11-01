from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile
import json
import socket
import subprocess
import sys
import pytest
from lxml import etree
from private_contracts.fields import empty_fields,validate,weekday,salary_amount,salary_words
from private_contracts.templates import NS,W,text,parse,replace_range,generate,render_values,registry,paragraph_at
from private_contracts.extract import merge_candidates,allowed_keys,source_pages
from private_contracts.review import review_contract
from private_contracts.readers import read_ods,read_xlsx,checked_zip

def fields(kind='employment'):
    values={'contract_type':kind,'name_ar':'موظف تجريبي غير حقيقي','name_en':'Test Employee Example','gender':'male','identity_type':'passport','identity_number':'00001234','identity_issue_date':'2024-01-15','identity_expiry_date':'2030-01-15','issuer_ar':'عدن','issuer_en':'Aden','execution_date':'2026-10-01','start_date':'2026-10-01','end_date':'2026-12-31','job_title_ar':'مساعد تعليم','job_title_en':'Education Assistant','grade_ar':'المساعدين','grade_en':'Assistants','workplace_ar':'عدن','workplace_en':'Aden','salary_usd':'825.69','manager_title_ar':'ضابط التعليم','manager_title_en':'Education Officer','manager_name_ar':'مدير تجريبي','manager_name_en':'Test Manager','project_ar':'مشروع تجريبي','project_en':'Demonstration Project'}
    result=empty_fields()
    for k,v in values.items():result[k].update(value=v,confirmed=True)
    return result

def test_dates_precision_and_leading_zeros():
    f=fields();assert not validate(f,True)
    assert weekday('2026-10-01')=='Thursday'
    assert weekday('2026-10-16','ar')=='الجمعة'
    v=render_values(f)
    assert '00001234' in v['identity_details_ar'] and 'جواز سفر' in v['identity_details_ar']
    assert 'Passport' in v['identity_details_en']
    assert 'Sixty-Nine' in salary_words('825.69','en')
    assert salary_amount('٨٢٥.٦٩')==salary_amount('825.69')
    for bad in ['NaN','Infinity','-1','0','825.699']:
        with pytest.raises(ValueError):salary_amount(bad)

def test_printed_dates_do_not_guess_numeric_order():
    from private_contracts.dates import printed_date
    assert printed_date('1 October 2026')=='2026-10-01'
    assert printed_date('١ أكتوبر ٢٠٢٦')=='2026-10-01'
    assert printed_date('31-12-2026')=='2026-12-31'
    assert printed_date('2026/10/01')=='2026-10-01'
    assert printed_date('1st of Jan 2026')=='2026-01-01'
    assert printed_date('01/10/2026') is None
    assert printed_date('3112-20-26','End: 31 December 2026')=='2026-12-31'
    assert printed_date('unreadable','Start 1 October 2026 and end 31 December 2026') is None

@pytest.mark.parametrize('key,value,level',[
    ('end_date','2026-01-01','error'),('identity_expiry_date','2024-06-01','warning'),
    ('identity_expiry_date','2023-01-01','error'),('issuer_en','Taiz','error'),
    ('issuer_ar','مركز - عدن-١','error'),('job_title_en','Assistant in the project UNICEF','error'),
    ('identity_type','driver_license','error'),('gender','unknown','error')])
def test_invalid_fields_flagged(key,value,level):
    f=fields();f[key]['value']=value
    assert any(x['field']==key and x['level']==level for x in validate(f,True))

def test_optional_fields_also_require_confirmation():
    f=fields();f['issuer_ar']['confirmed']=False
    assert any(x['field']=='issuer_ar' and x['level']=='error' for x in validate(f,True))
    f['issuer_ar']['value']='';f['issuer_en']['value']=''
    assert not any(x['field'].startswith('issuer') for x in validate(f,True))

def test_run_replacement_preserves_tabs_breaks_styles_and_wrappers():
    p=parse(('<w:p xmlns:w="'+NS['w']+'"><w:bookmarkStart w:id="1" w:name="x"/><w:r><w:rPr><w:rtl/></w:rPr><w:tab/><w:t>before {{na</w:t></w:r><w:hyperlink w:anchor="x"><w:r><w:rPr><w:i/></w:rPr><w:t>me_ar}} after</w:t><w:br/></w:r></w:hyperlink><w:bookmarkEnd w:id="1"/></w:p>').encode())
    s=text(p);start=s.index('{{');end=s.index('}}')+2
    replace_range(p,start,end,'اسم تجريبي')
    assert text(p)=='before اسم تجريبي after'
    assert len(p.xpath('.//w:tab',namespaces=NS))==1
    assert len(p.xpath('.//w:br',namespaces=NS))==1
    assert len(p.xpath('.//w:bookmarkStart|.//w:bookmarkEnd',namespaces=NS))==2
    marked=p.xpath('.//w:r[w:t="اسم تجريبي"]',namespaces=NS)[0]
    assert marked.find('w:rPr/w:b',NS).get(W+'val')=='1'
    assert marked.find('w:rPr/w:bCs',NS).get(W+'val')=='1'
    assert marked.find('w:rPr/w:rtl',NS) is not None
    assert p.xpath('.//w:hyperlink/w:r/w:rPr/w:i',namespaces=NS)

def test_generation_changes_only_fields(tmp_path):
    source=tmp_path/'template.docx';target=tmp_path/'filled.docx'
    with ZipFile(source,'w') as z:
        z.writestr('word/document.xml',('<w:document xmlns:w="'+NS['w']+'"><w:body><w:p><w:r><w:t>Fixed {{name_ar}} / {{identity_number}} end.</w:t></w:r></w:p></w:body></w:document>').encode())
        z.writestr('word/styles.xml',b'unchanged-styles')
        z.writestr('word/media/example.bin',b'unchanged-image')
    proof=generate(source,fields(),target)
    assert proof['template_text_preserved'] and proof['other_package_parts_unchanged']
    with ZipFile(target) as z:
        assert z.read('word/styles.xml')==b'unchanged-styles'
        assert z.read('word/media/example.bin')==b'unchanged-image'
        assert text(parse(z.read('word/document.xml')))=='Fixed موظف تجريبي غير حقيقي / 00001234 end.'

def test_extension_contains_new_identity_and_no_previous_employee_names(tmp_path):
    entry=registry().get('extension',{})
    if not entry.get('path'):pytest.skip('Extension not configured in this workspace')
    f=fields('extension');f['original_contract_date'].update(value='2026-07-01',confirmed=True)
    output=tmp_path/'extension.docx';generate(entry['path'],f,output)
    with ZipFile(output) as z:root=parse(z.read('word/document.xml'))
    body=text(root)
    assert '{{' not in body and '00001234' in body
    assert 'Test Employee Example' in body and 'موظف تجريبي غير حقيقي' in body
    assert not __import__('re').search(r'\b(a|an)\s+(a|an)\b',body,__import__('re').I)
    bindings=Path(entry['path']).with_name('bindings.json')
    if bindings.exists():
        for index,before,key in json.loads(bindings.read_text()):
            if key in {'name_ar','name_en'}:assert before not in body

def test_sources_and_conflicts():
    assert 'identity_number' not in allowed_keys('offer')
    assert 'salary_usd' not in allowed_keys('identity')
    f=fields();c={'key':'identity_number','value':'9999','source_id':'dummy','source_name':'Dummy ID','page':1,'quote':'9999','text_match':True,'source_role':'identity','method':'local text'}
    conflicts=merge_candidates(f,[c])
    assert conflicts and f['identity_number']['value']=='00001234' and f['identity_number']['confirmed']
    f['identity_number']['confirmed']=False
    merge_candidates(f,[c]);assert f['identity_number']['alternatives'][0]['value']=='9999'
    source={'role':'list','pages':[{'number':1,'text':'Row 1: headings\nRow 6: Sample Employee | Aden'}]}
    assert 'Sample Employee' in source_pages(source,'6')[0]['text']
    with pytest.raises(ValueError):source_pages(source,'7')
    assert 'Row 1: headings' in source_pages(source,'6')[0]['text']
    assert 'Sample Employee' in source_pages(source,'','Sample Employee')[0]['text']
    with pytest.raises(ValueError):source_pages({'role':'list','pages':[{'number':1,'text':'Row 1: heading\nRow 2: Sample Employee\nRow 3: Sample Employee'}]},'','Sample Employee')

def test_template_requirements_cover_computed_fields():
    from private_contracts.templates import template_requirements,validate_template
    entry={'placeholders':['name_ar','identity_details_en','honorific_en','original_ar','manager_base_clause_en']}
    assert template_requirements(entry)=={'name_ar','identity_type','identity_number','identity_issue_date','gender','original_contract_date'}
    f=fields('extension')
    assert any(i['field']=='original_contract_date' for i in validate_template(f,entry,True))

def test_unsupported_language_and_grade_are_left_unconfirmed(monkeypatch):
    import private_contracts.extract as module
    response={'fields':{'job_title_ar':{'value':'Education Assistant','quote':'Education Assistant'},'grade_en':{'value':'Assistants','quote':'Education Assistant'},'original_contract_date':{'value':'1 October 2026','quote':'Offer date: 1 October 2026'},'execution_date':{'value':'1 October 2026','quote':'Offer date: 1 October 2026'}}}
    monkeypatch.setattr(module,'chat',lambda *args,**kwargs:response)
    result=module.extract_source({'id':'dummy','name':'Dummy offer','role':'offer','pages':[{'number':1,'kind':'text','image':False,'text':'Offer date: 1 October 2026. Education Assistant.'}]})
    values={i['key']:i for i in result}
    assert values['job_title_ar']['uncertain'] and not values['job_title_ar']['value']
    assert values['grade_en']['uncertain'] and not values['grade_en']['value']
    assert 'original_contract_date' not in values
    assert values['execution_date']['value']=='2026-10-01'

def test_ods_and_xlsx_preserve_row_numbers(tmp_path):
    p=tmp_path/'list.ods'
    with ZipFile(p,'w') as z:
        z.writestr('content.xml','<root xmlns:o="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:t="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><o:table o:name="List"><o:table-row o:number-rows-repeated="5"><o:table-cell/></o:table-row><o:table-row><o:table-cell><t:p>Sample Employee</t:p></o:table-cell></o:table-row></o:table></root>')
    assert read_ods(p)[0]['text'].startswith('Row 6: Sample Employee')
    p=tmp_path/'list.xlsx'
    with ZipFile(p,'w') as z:z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="6"><c r="A6" t="inlineStr"><is><t>Sample Employee</t></is></c></row></sheetData></worksheet>')
    assert read_xlsx(p)[0]['text'].startswith('Row 6: A6: Sample Employee')

@pytest.mark.parametrize('kind',['employment','service'])
def test_real_template_structure_review_detects_one_language_mistakes(tmp_path,kind):
    reference=registry().get(kind,{}).get('path')
    if not reference:pytest.skip('NMO template not configured in this test workspace')
    f=fields(kind);target=tmp_path/'dummy.docx';generate(reference,f,target)
    def source():
        with ZipFile(target) as z:r=parse(z.read('word/document.xml'))
        return {'path':str(target),'pages':[{'number':1,'text':text(r),'kind':'text'}]}
    initial=review_contract({'fields':f},source(),reference)
    assert not [i for i in initial if i['level']=='error']
    poor_extraction={**source(),'pages':[{'number':1,'kind':'text','text':'PDF column reading order is unreliable in this deliberately degraded test. '*4}]}
    fallback=review_contract({'fields':f},poor_extraction,reference)
    assert not [i for i in fallback if i['level']=='error']
    with ZipFile(target) as z:contents={n:z.read(n) for n in z.namelist()}
    r=parse(contents['word/document.xml'])
    col=1 if kind=='employment' else 0
    slot=(7,col,4) if kind=='employment' else (4,col,1)
    from private_contracts.templates import replace_value
    replace_value(paragraph_at(r,slot),'825.69','925.69')
    # Deliberately alter only the Arabic salary, leaving the English side correct.
    contents['word/document.xml']=etree.tostring(r)
    with ZipFile(target,'w') as z:
        for n,b in contents.items():z.writestr(n,b)
    findings=review_contract({'fields':f},source(),reference)
    assert any(i['level']=='error' and i['field']=='salary_usd' and 'Arabic' in i.get('location','') for i in findings)
    assert not any(i['level']=='pass' and i['field']=='salary_usd' for i in findings)

def test_network_guard_denies_external_connections():
    code='''from private_contracts.privacy import install_network_guard,LocalOnlyError
import socket
install_network_guard()
for action in [lambda:socket.getaddrinfo("example.com",443),lambda:socket.socket().connect(("1.1.1.1",443)),lambda:socket.socket(socket.AF_INET,socket.SOCK_DGRAM).sendto(b"dummy",("1.1.1.1",53))]:
    try:action()
    except LocalOnlyError:pass
    else:raise AssertionError("External connection was allowed")
print("blocked")'''
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
    assert result.returncode==0 and result.stdout.strip()=='blocked'
