import subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
for name in ['smoke_ai.py','smoke_identity.py','prepare_extension.py','output_checks.py']:
    print('Checking '+name,flush=True)
    subprocess.run([sys.executable,str(root/'tools'/name)],cwd=root,check=True)
