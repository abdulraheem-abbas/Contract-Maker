"""Minimal, run-preserving Word field replacement.

Only word/document.xml is edited during generation. Template preparation removes
stale document bindings and custom XML before any employee is filled in.
"""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from copy import deepcopy
import hashlib
import json
import re
from lxml import etree
from .config import DATA
from .fields import normalize, compact, date_display, identity_date, weekday, salary_words, salary_amount,FIELD_KEYS,LABELS

NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W='{'+NS['w']+'}'
XML_SPACE='{http://www.w3.org/XML/1998/namespace}space'
TOKEN=re.compile(r'\{\{([a-z][a-z0-9_]*)\}\}')

def template_requirements(entry):
    result=set()
    dependencies={'honorific_en':{'gender'},'honorific_ar':{'gender'},'nationality_ar':{'gender'},'refer_ar':{'gender'}}
    optional={'issuer_ar','issuer_en','manager_base_ar','manager_base_en','identity_expiry_date'}
    for key in entry.get('placeholders',[]):
        if key in FIELD_KEYS and key not in optional:result.add(key)
        elif key.startswith('identity_details_'):result|={'identity_type','identity_number','identity_issue_date'}
        elif key.startswith('salary_words_'):result.add('salary_usd')
        elif key.startswith(('execution_','weekday_')):result.add('execution_date')
        elif key in {'start_ar','start_en'}:result.add('start_date')
        elif key in {'end_ar','end_en'}:result.add('end_date')
        elif key in {'original_ar','original_en'}:result.add('original_contract_date')
        else:result|=dependencies.get(key,set())
    return result

def validate_template(fields,entry,require_confirmation=False):
    issues=[]
    for key in sorted(template_requirements(entry)):
        field=fields.get(key,{})
        if not field.get('value','').strip():issues.append({'level':'error','field':key,'message':LABELS.get(key,key)+' is required by this template.'})
        elif require_confirmation and not field.get('confirmed'):issues.append({'level':'error','field':key,'message':'Confirm '+LABELS.get(key,key)+' against its source.'})
    return issues

def parse(data):
    return etree.fromstring(data,parser=etree.XMLParser(resolve_entities=False,no_network=True))

def text(node):
    return ''.join(node.xpath('.//w:t/text()',namespaces=NS))

def canonical_offsets(value):
    chars=[];offsets=[]
    for i,char in enumerate(value):
        if char not in '\u200e\u200f\u2060' and not char.isspace():
            chars.append(char);offsets.append(i)
    return ''.join(chars),offsets

def locate(haystack,needle):
    if not needle:
        raise ValueError('An empty template binding was refused.')
    h,offsets=canonical_offsets(haystack)
    n,_=canonical_offsets(needle)
    start=h.find(n)
    if start<0:
        raise ValueError('A configured template field no longer matches its approved reference. Re-import the template.')
    if h.find(n,start+len(n))>=0:
        raise ValueError('A template binding is ambiguous. Use a more specific field mapping.')
    return offsets[start],offsets[start+len(n)-1]+1

def replace_range(paragraph,start,end,replacement,bold=True):
    """Split only affected text runs; retain wrappers and all other run properties."""
    runs=[];cursor=0
    for run in paragraph.xpath('.//w:r',namespaces=NS):
        run_text=''.join(t.text or '' for t in run.findall('w:t',NS))
        if run_text:
            runs.append((run,cursor,cursor+len(run_text),run_text))
            cursor+=len(run_text)
    if not (0<=start<end<=cursor):
        raise ValueError('Invalid template field boundary.')
    inserted=False
    for run,lo,hi,run_text in runs:
        if hi<=start or lo>=end:
            continue
        parent=run.getparent();index=parent.index(run)
        pieces=[]
        def make(children,mark=False):
            new=deepcopy(run)
            for child in list(new):
                if child.tag!=W+'rPr':
                    new.remove(child)
            if mark:
                props=new.find('w:rPr',NS)
                if props is None:
                    props=etree.Element(W+'rPr');new.insert(0,props)
                for tag in ['b','bCs']:
                    existing=props.find('w:'+tag,NS)
                    if existing is None:
                        existing=etree.SubElement(props,W+tag)
                    existing.set(W+'val','1')
            for child in children:new.append(child)
            return new
        left_children=[];right_children=[];position=lo
        def text_child(child,value):
            result=deepcopy(child);result.set(XML_SPACE,'preserve');result.text=value;return result
        for child in run:
            if child.tag==W+'rPr':continue
            if child.tag!=W+'t':
                (left_children if position<=start else right_children).append(deepcopy(child))
                continue
            value=child.text or '';child_end=position+len(value)
            if position<start:
                before=value[:min(len(value),start-position)]
                if before:left_children.append(text_child(child,before))
            if child_end>end:
                after=value[max(0,end-position):]
                if after:right_children.append(text_child(child,after))
            position=child_end
        if left_children:
            pieces.append(make(left_children))
        if not inserted:
            replacement_child=etree.Element(W+'t');replacement_child.set(XML_SPACE,'preserve');replacement_child.text=replacement
            pieces.append(make([replacement_child],bold));inserted=True
        if right_children:
            pieces.append(make(right_children))
        parent.remove(run)
        for offset,piece in enumerate(pieces):
            parent.insert(index+offset,piece)

def replace_value(paragraph,before,after,bold=True):
    lo,hi=locate(text(paragraph),before)
    replace_range(paragraph,lo,hi,after,bold)

def paragraph_at(root,slot):
    row,col,index=slot
    table=root.find('w:body/w:tbl',NS)
    return table.findall('w:tr',NS)[row].findall('w:tc',NS)[col].findall('w:p',NS)[index]

def prepare_template(source,destination,bindings):
    """bindings = [(slot, old literal, token key), ...], never model-generated."""
    with ZipFile(source) as z:
        contents={i.filename:z.read(i.filename) for i in z.infolist()}
        infos=z.infolist()
    root=parse(contents['word/document.xml'])
    for slot,before,key in bindings:
        replace_value(paragraph_at(root,slot),before,'{{'+key+'}}')
    for binding in root.xpath('//w:dataBinding',namespaces=NS):
        binding.getparent().remove(binding)
    contents['word/document.xml']=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
    # Remove custom XML data retained from the source employee, and relationships
    # pointing at it. This is template preparation, not a change to legal text.
    removed={n for n in contents if n.startswith('customXml/')}
    for name,data in list(contents.items()):
        if name.endswith('.rels'):
            r=parse(data)
            for child in list(r):
                if '/customXml' in child.get('Type','') or 'customXml/' in child.get('Target',''):
                    r.remove(child)
            contents[name]=etree.tostring(r,xml_declaration=True,encoding='UTF-8',standalone=True)
    types=parse(contents['[Content_Types].xml'])
    for child in list(types):
        if child.get('PartName','').lstrip('/') in removed:
            types.remove(child)
    contents['[Content_Types].xml']=etree.tostring(types,xml_declaration=True,encoding='UTF-8',standalone=True)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(destination,'w',ZIP_DEFLATED) as out:
        for info in infos:
            if info.filename not in removed:
                out.writestr(info,contents[info.filename])
    return {'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'placeholders':sorted(set(TOKEN.findall(text(root))))}

def identity_details(values,language):
    kind=values.get('identity_type','id_card')
    number=values['identity_number']
    issued=identity_date(values['identity_issue_date'])
    city=values.get('issuer_'+language,'').strip()
    if language=='ar':
        label='جواز سفر' if kind=='passport' else 'بطاقة شخصية بالرقم الوطني' if kind=='national_id' else 'بطاقة شخصية'
        verb='صادر' if kind=='passport' else 'صادرة'
        return f'{label}'+(' ' if kind=='national_id' else ' رقم ')+f'\u200e{number}\u200e {verb}'+(f' من {city}' if city else '')+f' بتاريخ \u200e{issued}\u200e'
    label='a Passport' if kind=='passport' else 'an ID Card with National Number' if kind=='national_id' else 'an ID Card'
    return f'{label}'+(' ' if kind=='national_id' else ' number ')+number+(' issued in '+city if city else ' issued')+' on '+issued

def render_values(fields):
    values={key:str(value.get('value','')).strip() for key,value in fields.items()}
    for prefix,key in [('execution','execution_date'),('start','start_date'),('end','end_date'),('original','original_contract_date')]:
        if values.get(key):
            for lang in ['ar','en']:
                values[prefix+'_'+lang]=date_display(values[key],lang)
    if values.get('execution_date'):
        values['weekday_ar']=weekday(values['execution_date'],'ar')
        values['weekday_en']=weekday(values['execution_date'],'en')
    if values.get('identity_number') and values.get('identity_issue_date'):
        values['identity_details_ar']=identity_details(values,'ar')
        values['identity_details_en']=identity_details(values,'en')
    if values.get('salary_usd'):
        number=salary_amount(values['salary_usd'])
        values['salary_usd']=format(number,'f')
        for lang in ['ar','en']:
            values['salary_words_'+lang]=salary_words(values['salary_usd'],lang)
    female=values.get('gender')=='female'
    for lang in ['ar','en']:
        base=values.get('manager_base_'+lang,'').strip()
        values['manager_base_clause_'+lang]=('، ومقره في '+base if lang=='ar' else ', based in '+base) if base else ''
    values.update({'honorific_en':'Ms.' if female else 'Mr.','honorific_ar':'الأخت' if female else 'الأخ','nationality_ar':'يمنية' if female else 'يمني','refer_ar':'إليها' if female else 'إليه'})
    return values

def generate(template,fields,destination):
    values=render_values(fields)
    with ZipFile(template) as z:
        infos=z.infolist();original={i.filename:z.read(i.filename) for i in infos}
    root=parse(original['word/document.xml'])
    count=0
    original_text=text(root)
    expected=TOKEN.sub(lambda m:values.get(m.group(1),m.group(0)),original_text)
    for paragraph in root.xpath('//w:p',namespaces=NS):
        matches=list(TOKEN.finditer(text(paragraph)))
        for match in reversed(matches):
            key=match.group(1)
            if key not in values:
                raise ValueError(f'The template requires a field that is not configured: {key}.')
            replace_range(paragraph,match.start(),match.end(),values[key],True)
            count+=1
    if TOKEN.search(text(root)) or text(root)!=expected:
        raise ValueError('The final Word text failed the template-preservation check.')
    changed=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(destination,'w') as out:
        for info in infos:
            out.writestr(info,changed if info.filename=='word/document.xml' else original[info.filename])
    with ZipFile(destination) as out:
        assert set(out.namelist())==set(original)
        assert all(out.read(n)==original[n] for n in original if n!='word/document.xml')
    return {'filled_occurrences':count,'other_package_parts_unchanged':True,'template_text_preserved':True,'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}

def registry():
    path=DATA/'templates/registry.json'
    entries=json.loads(path.read_text()) if path.exists() else {}
    for kind,entry in entries.items():
        for key,filename in [('path','template.docx'),('original','original.docx')]:
            local=DATA/'templates'/kind/filename
            if key in entry:
                saved=Path(entry[key])
                if not saved.is_absolute():entry[key]=str(DATA/saved)
                elif not entry.get('version') and local.exists():entry[key]=str(local)
    return entries
