"""Local layout and preservation checks using fictional employee values."""
import sys,json,runpy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from private_contracts.config import DATA
from private_contracts.templates import registry,generate,validate_template
from private_contracts.office import to_pdf
from private_contracts.readers import pdf_pages
root=Path(__file__).resolve().parent.parent
make_fields=runpy.run_path(str(root/'tests/test_core.py'))['fields']
results=[]
out=DATA/'cache/output-checks';out.mkdir(exist_ok=True)
for kind,entry in registry().items():
    if not entry.get('path'):continue
    f=make_fields(kind)
    f['original_contract_date'].update(value='2026-07-01',confirmed=True)
    issues=validate_template(f,entry,True)
    if issues:raise RuntimeError('Template requirements missing: '+','.join(x['field'] for x in issues))
    target=out/(kind+'-dummy.docx')
    proof=generate(entry['path'],f,target)
    pdf=to_pdf(target,out);pages=pdf_pages(pdf)
    blank=[p['number'] for p in pages if len(p['text'].strip())<12]
    if blank:raise RuntimeError('Potential empty pages detected: '+kind)
    results.append({'kind':kind,'pdf_pages':len(pages),'empty_pages':blank,'fixed_text_preserved':proof['template_text_preserved'],'other_package_parts_unchanged':proof['other_package_parts_unchanged']})
(root/'test-results/output-checks.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results))
