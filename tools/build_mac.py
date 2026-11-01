"""Build the local Mac launcher; preserves any previous build as a backup."""
import os,sys,subprocess,shutil,time
from pathlib import Path
root=Path(__file__).resolve().parent.parent
env=dict(os.environ);env['PYINSTALLER_CONFIG_DIR']=str(root/'build/pyinstaller-cache')
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--windowed','--onedir','--name','Private Contracts','--osx-bundle-identifier','org.nmo.privatecontracts','--add-data','web:web','--collect-all','pypdfium2','--collect-all','num2words','run.py'],cwd=root,env=env,check=True)
target=root/'Private Contracts.app'
if target.exists():shutil.move(str(target),str(root/'build'/('Previous app '+str(int(time.time()))+'.app')))
shutil.move(str(root/'dist/Private Contracts.app'),str(target))
print('Built '+str(target))
