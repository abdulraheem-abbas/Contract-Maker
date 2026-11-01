"""Template changes use fictional Word packages and an isolated local store."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import base64
import json
import threading
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import build_opener, ProxyHandler, HTTPCookieProcessor, Request
import pytest
from lxml import etree
from private_contracts import template_manager as manager, templates
from private_contracts.templates import W, NS, parse, text, generate
from private_contracts.fields import empty_fields


def word(paragraphs=None, extra=None):
    paragraphs=paragraphs or ['Fixed approved wording.', '{{name_ar}}', '{{name_en}}', '{{execution_ar}} / {{execution_en}}', '{{start_ar}} / {{end_ar}}']
    root=etree.Element(W+'document',nsmap={'w':NS['w']})
    body=etree.SubElement(root,W+'body')
    for value in paragraphs:
        p=etree.SubElement(body,W+'p');r=etree.SubElement(p,W+'r')
        etree.SubElement(r,W+'t').text=value
    data={'[Content_Types].xml':b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
          '_rels/.rels':b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
          'word/document.xml':etree.tostring(root), **(extra or {})}
    out=BytesIO()
    with ZipFile(out,'w') as z:
        for name,raw in data.items():z.writestr(name,raw)
    return out.getvalue()


@pytest.fixture
def workspace(tmp_path,monkeypatch):
    monkeypatch.setattr(manager,'DATA',tmp_path)
    monkeypatch.setattr(templates,'DATA',tmp_path)
    folder=tmp_path/'templates/employment';folder.mkdir(parents=True)
    raw=word();path=folder/'template.docx';path.write_bytes(raw)
    entry={'label':'Test employment','path':str(path),'sha256':manager.digest(raw),'placeholders':manager.inspect(raw)['placeholders']}
    (tmp_path/'templates/registry.json').write_text(json.dumps({'employment':entry}))
    return tmp_path,entry,raw


def test_template_draft_activation_and_restore_preserve_originals(workspace):
    root,entry,original=workspace
    updated=word(['Updated approved clause.','{{name_ar}}','{{name_en}}','{{execution_ar}}','{{start_ar}} — {{end_ar}}'])
    draft=manager.stage('employment','updated.docx',updated,entry['sha256'])
    assert manager.active('employment')[1]==original
    assert not draft['errors']
    manager.activate('employment',draft['draft'],draft['sha256'],True)
    active,raw=manager.active('employment')
    assert raw==updated and active['version']
    assert (root/'templates/employment/template.docx').read_bytes()==original
    history=manager.describe('employment')['history']
    assert len(history)==1 and 'path' not in history[0]
    restore=manager.restore_draft('employment',history[0]['version'],active['sha256'])
    assert manager.active('employment')[1]==updated
    manager.activate('employment',restore['draft'],restore['sha256'],True)
    assert manager.active('employment')[1]==original
    assert len(manager.describe('employment')['history'])==2
    assert manager.file_path('employment',version=active['version']).read_bytes()==updated


def test_mapping_changes_draft_only_and_retains_other_package_parts(workspace):
    _,entry,original=workspace
    raw=word(['Fixed approved wording.','اسم تجريبي','{{name_en}}','{{execution_ar}}','{{start_ar}} / {{end_ar}}'],{'word/media/test.bin':b'unchanged image'})
    draft=manager.stage('employment','new.docx',raw,entry['sha256'])
    assert any('Arabic' in e for e in draft['errors'])
    mapped=manager.map_fields('employment',draft['draft'],draft['sha256'],[{'paragraph':1,'before':'اسم تجريبي','key':'name_ar'}])
    assert not mapped['errors'] and mapped['draft']!=draft['draft']
    assert manager.file_path('employment',draft['draft']).read_bytes()==raw
    with ZipFile(manager.file_path('employment',mapped['draft'])) as z:
        assert z.read('word/media/test.bin')==b'unchanged image'
        r=parse(z.read('word/document.xml'))
        assert '{{name_ar}}' in text(r)
        assert r.xpath('//w:r[w:t="{{name_ar}}" ]/w:rPr/w:bCs',namespaces=NS)
    assert manager.active('employment')[1]==original


def test_activation_requires_review_and_supported_mapped_fields(workspace):
    _,entry,_=workspace
    draft=manager.stage('employment','not-mapped.docx',word(['A fixed contract for Sample Employee.']),entry['sha256'])
    with pytest.raises(ValueError,match='Check the template wording'):
        manager.activate('employment',draft['draft'],draft['sha256'],False)
    with pytest.raises(ValueError,match='Map the employee name'):
        manager.activate('employment',draft['draft'],draft['sha256'],True)
    malformed=manager.stage('employment','unknown.docx',word(['{{name_ar}}','{{name_en}}','{{unknown_field}}','{{execution_ar}}','{{start_ar}} {{end_ar}}']),entry['sha256'])
    assert any('Unsupported field' in e for e in malformed['errors'])
    with pytest.raises(ValueError,match='Unsupported field'):
        manager.activate('employment',malformed['draft'],malformed['sha256'],True)


def test_stale_tabs_cannot_overwrite_new_template(workspace):
    _,entry,_=workspace
    first=manager.stage('employment','first.docx',word(),entry['sha256'])
    second=manager.stage('employment','second.docx',word(['New wording.','{{name_ar}}','{{name_en}}','{{execution_ar}}','{{start_ar}} {{end_ar}}']),entry['sha256'])
    manager.activate('employment',second['draft'],second['sha256'],True)
    with pytest.raises(ValueError,match='changed since this draft'):
        manager.activate('employment',first['draft'],first['sha256'],True)
    with pytest.raises(ValueError,match='changed'):
        manager.map_fields('employment',None,entry['sha256'],[{'paragraph':0,'before':'Fixed','key':'name_ar'}])
    assert manager.active('employment')[1]==manager.file_path('employment',second['draft']).read_bytes()


def test_mapping_active_template_starts_a_draft(workspace):
    _,entry,raw=workspace
    mapped=manager.map_fields('employment',None,entry['sha256'],[{'paragraph':0,'before':'Fixed approved wording.','key':'project_en'}])
    assert mapped['draft'] and '{{project_en}}' in str(mapped['paragraphs'])
    assert manager.active('employment')[1]==raw


@pytest.mark.parametrize('extra,message',[
    ({'word/vbaProject.bin':b'x'},'macros'),
    ({'word/embeddings/file.bin':b'x'},'embedded'),
    ({'../escape.xml':b'<x/>'},'invalid part'),
    ({'word/_rels/document.xml.rels':b'<Relationships><Relationship TargetMode="External" Type="test/image" Target="https://example.invalid/image"/></Relationships>'},'linked images'),
])
def test_unsafe_word_packages_rejected(extra,message):
    with pytest.raises(ValueError,match=message):manager.inspect(word(extra=extra))


def test_header_tokens_and_incomplete_tags_block_activation():
    report=manager.inspect(word(extra={'word/header1.xml':('<w:hdr xmlns:w="'+NS['w']+'"><w:p><w:r><w:t>{{name_en}}</w:t></w:r></w:p></w:hdr>').encode()}))
    assert any('headers' in e for e in report['errors'])
    assert any('incomplete' in e for e in manager.inspect(word(['{{name_ar}']))['errors'])
    with pytest.raises(ValueError,match='could not be read'):manager.inspect(b'not a Word package')


def test_unknown_versions_and_modified_local_templates_are_refused(workspace):
    root,entry,_=workspace
    with pytest.raises(ValueError,match='changed'):
        manager.file_path('employment',expected_sha='0'*64)
    with pytest.raises(ValueError):manager.file_path('employment','../../registry.json')
    with pytest.raises(ValueError):manager.file_path('employment',version='0'*32)
    (root/'templates/employment/template.docx').write_bytes(word(['Modified outside app']))
    with pytest.raises(ValueError,match='changed outside'):manager.active('employment')


def test_custom_template_review_checks_each_repeated_field(workspace,tmp_path):
    from private_contracts.review import review_contract
    from test_core import fields
    raw=word(['Employee: {{name_en}}','الاسم: {{name_ar}}','Date: {{execution_en}}','Period: {{start_en}} — {{end_en}}','Signed by: {{name_en}}'])
    reference=tmp_path/'custom.docx';reference.write_bytes(raw)
    output=tmp_path/'contract.docx';f=fields();generate(reference,f,output)
    with ZipFile(output) as z:parts={n:z.read(n) for n in z.namelist()}
    document=parse(parts['word/document.xml'])
    last=document.xpath('//w:p',namespaces=NS)[-1]
    for node in last.xpath('.//w:t',namespaces=NS):
        if node.text=='Test Employee Example':node.text='Incorrect Person'
    parts['word/document.xml']=etree.tostring(document)
    with ZipFile(output,'w') as z:
        for name,data in parts.items():z.writestr(name,data)
    source={'path':str(output),'pages':[{'number':1,'text':text(document),'kind':'text'}]}
    findings=review_contract({'fields':f},source,reference)
    assert any(i['field']=='name_en' and i['level']=='error' and 'paragraph 5' in i.get('location','') for i in findings)
    assert not any(i['field']=='name_en' and i['level']=='pass' for i in findings)


def test_changed_table_layout_with_same_row_count_does_not_use_old_slots(tmp_path):
    from private_contracts.review import review_contract
    from test_core import fields
    from private_contracts.templates import render_values
    values=render_values(fields())
    raw=word(['Fields: '+' | '.join('{{'+k+'}}' for k in values if k!='contract_type')])
    with ZipFile(BytesIO(raw)) as z:parts={n:z.read(n) for n in z.namelist()}
    document=parse(parts['word/document.xml']);body=document.find('w:body',NS)
    table=etree.SubElement(body,W+'tbl')
    for row in range(22):
        tr=etree.SubElement(table,W+'tr')
        for col in range(2):
            tc=etree.SubElement(tr,W+'tc')
            for index in range(6):
                p=etree.SubElement(tc,W+'p');r=etree.SubElement(p,W+'r')
                value='Approved fixed wording.'
                if (row,col,index)==(2,1,1):value='{{job_title_ar}}'
                if (row,col,index)==(7,1,4):value='{{salary_usd}}'
                etree.SubElement(r,W+'t').text=value
    parts['word/document.xml']=etree.tostring(document)
    reference=tmp_path/'new-layout.docx'
    with ZipFile(reference,'w') as z:
        for name,data in parts.items():z.writestr(name,data)
    output=tmp_path/'generated.docx';generate(reference,fields(),output)
    with ZipFile(output) as z:actual=text(parse(z.read('word/document.xml')))
    findings=review_contract({'fields':fields()},{'path':str(output),'pages':[{'number':1,'text':actual,'kind':'text'}]},reference)
    assert not [f for f in findings if f['level']=='error']


def test_template_http_routes_are_local_authenticated_and_versioned(workspace,monkeypatch):
    from private_contracts import server
    root,entry,_=workspace
    monkeypatch.setattr(server,'DATA',root)
    app=server.AppServer(('127.0.0.1',0),server.Handler)
    thread=threading.Thread(target=app.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{app.server_port}'
    client=build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()))
    def post(route,payload,origin=None):
        return json.load(client.open(Request(base+route,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Origin':origin or base,'X-Private-CSRF':server.CSRF})))
    try:
        with pytest.raises(HTTPError) as error:client.open(base+'/api/template-file?kind=employment')
        assert error.value.code==403
        client.open(base).read()
        current=json.load(client.open(base+'/api/template-editor?kind=employment'))
        assert current['sha256']==entry['sha256']
        payload={'kind':'employment','name':'updated.docx','data':base64.b64encode(word()).decode(),'expected_sha':entry['sha256']}
        with pytest.raises(HTTPError) as error:post('/api/template-import',payload,'https://outside.invalid')
        assert error.value.code==403
        draft=post('/api/template-import',payload)
        post('/api/template-activate',{'kind':'employment','draft':draft['draft'],'expected_sha':draft['sha256'],'reviewed':True})
        assert client.open(base+'/api/template-file?kind=employment').read()==word()
        with pytest.raises(HTTPError):client.open(base+'/api/template-file?kind=../../registry.json')
    finally:
        app.shutdown();app.server_close();thread.join(timeout=2)
