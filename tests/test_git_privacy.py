"""Guard against accidentally staging real HR documents or local workspaces."""
from pathlib import Path
import shutil
import subprocess


def test_private_files_are_ignored_but_source_is_versioned(tmp_path):
    root=Path(__file__).resolve().parent.parent
    shutil.copy2(root/'.gitignore',tmp_path/'.gitignore')
    subprocess.run(['git','init','-q'],cwd=tmp_path,check=True)
    private=[
        'data/sources/employee.docx','data/templates/service/template.docx',
        'local/import_templates.py','Private Contracts.app/Contents/MacOS/Private Contracts',
        'Employee.PDF','passport.JPEG','Employee List.ODS','offer.DOCX','employee.TXT',
        'employee.csv','rules.json','test-results/review.png','.env.local',
        'node_modules/package/index.js','workspace.sqlite3','private-model.gguf',
    ]
    source=[
        'private_contracts/server.py','web/app.js','web/icon.svg','README.md',
        'DEVELOPMENT.md','tests/test_core.py','tools/setup_engine.py',
        'requirements.txt','requirements-dev.txt',
    ]
    result=subprocess.run(['git','check-ignore','-z','--stdin'],cwd=tmp_path,input='\0'.join(private+source)+'\0',text=True,capture_output=True,check=True)
    ignored=set(result.stdout.rstrip('\0').split('\0'))
    assert set(private)<=ignored
    assert not set(source)&ignored
