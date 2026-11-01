import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from private_contracts.engine import chat,status
from private_contracts.privacy import install_network_guard
from private_contracts.extract import extract_source

install_network_guard()
started=time.monotonic()
candidates=extract_source({'id':'fictional-offer','name':'Fictional offer','role':'offer','pages':[{'number':1,'kind':'text','image':False,'text':'DEMONSTRATION ONLY. Employment offer. Offer date: 1 October 2026. Start: 4 October 2026. End: 31 December 2026. Job title: Education Assistant. Gross monthly salary USD 825.69.'}]})
fields={f['key']:f['value'] for f in candidates}
expected={'contract_type':'employment','execution_date':'2026-10-01','start_date':'2026-10-04','end_date':'2026-12-31','job_title_en':'Education Assistant','salary_usd':'825.69'}
passed=all(fields.get(k)==v for k,v in expected.items())
report={'local_model':status(),'elapsed_seconds':round(time.monotonic()-started,2),'dummy_fields':fields,'expected_fields_correct':passed}
(Path(__file__).resolve().parent.parent/'test-results').mkdir(exist_ok=True)
(Path(__file__).resolve().parent.parent/'test-results/ai-smoke.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
if not passed:sys.exit(1)
