"""Read a fictional passport image locally; no actual employee document is used."""
import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from PIL import Image
from zipfile import ZipFile
from io import BytesIO
from xml.sax.saxutils import escape
from private_contracts.config import DATA
from private_contracts.readers import read_file,page_image
from private_contracts.office import to_pdf
from private_contracts.extract import extract_source
from private_contracts.privacy import install_network_guard
initialize=__import__('private_contracts.config',fromlist=['initialize']).initialize
initialize();install_network_guard()
lines=['SAMPLE DOCUMENT - FICTIONAL - NOT VALID','REPUBLIC OF YEMEN / PASSPORT','Passport No: 00012345','Full name: TEST EMPLOYEE EXAMPLE','Nationality: YEMENI     Sex: M','Place of birth: TAIZ - YEM','Date of birth: 13/08/2000','Date of issue: 15/01/2024','Date of expiry: 15/01/2030','Issuing authority: ADEN']
lines+=['الاسم: موظف تجريبي غير حقيقي','مكان الإصدار: عدن']
paragraphs=[]
for line in lines:
    ar=any('\u0600'<=c<='\u06ff' for c in line)
    paragraphs.append('<w:p><w:pPr><w:spacing w:after="180"/>'+('<w:bidi/><w:jc w:val="right"/>' if ar else '')+'</w:pPr><w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="32"/><w:szCs w:val="32"/>'+('<w:rtl/>' if ar else '')+'</w:rPr><w:t>'+escape(line)+'</w:t></w:r></w:p>')
docx=DATA/'cache/fictional-passport.docx'
with ZipFile(docx,'w') as z:
    z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+''.join(paragraphs)+'<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="600" w:left="600" w:right="600" w:bottom="600"/></w:sectPr></w:body></w:document>')
pdf=to_pdf(docx,DATA/'cache')
pages=read_file(pdf);assert len(pages)==1
image=Image.open(BytesIO(page_image({'pages':pages},0,max_side=1600)))
path=DATA/'cache/fictional-passport.png';image.save(path)
source={'id':'fictional-passport','name':'Fictional passport image','role':'identity','path':str(path),'pages':read_file(path)}
started=time.monotonic();candidates=extract_source(source)
fields={c['key']:c['value'] for c in candidates}
expected={'identity_type':'passport','identity_number':'00012345','identity_issue_date':'2024-01-15','identity_expiry_date':'2030-01-15','issuer_en':'Aden'}
correct={k:fields.get(k,'').casefold()==v.casefold() for k,v in expected.items()}
report={'elapsed_seconds':round(time.monotonic()-started,2),'dummy_fields':fields,'checks':correct,'all_numeric_and_document_checks_passed':all(correct.values())}
(Path(__file__).resolve().parent.parent/'test-results/identity-smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
if not all(correct.values()):sys.exit(1)
