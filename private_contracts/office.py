from pathlib import Path
from zipfile import ZipFile
import os
import shutil
import subprocess
import tempfile
import sys
from lxml import etree
from .config import ROOT, DATA

def office_binary():
    candidates = [
        ROOT/'runtime/office/LibreOfficeDev.app/Contents/MacOS/soffice',
        Path('/Applications/LibreOffice.app/Contents/MacOS/soffice'),
        Path('/Applications/LibreOfficeDev.app/Contents/MacOS/soffice'),
        Path(os.environ.get('PROGRAMFILES', 'C:/Program Files'))/'LibreOffice/program/soffice.exe',
    ]
    bundled = Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice'
    candidates.extend([bundled, Path(shutil.which('soffice') or '/nonexistent')])
    return next((str(p) for p in candidates if p.is_file()), None)

def safe_render_copy(source, destination):
    """Strip external relationships in a disposable render copy, never the original."""
    with ZipFile(source) as src, ZipFile(destination,'w') as out:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename.endswith('.rels'):
                root = etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True))
                for rel in list(root):
                    if rel.get('TargetMode') == 'External':
                        root.remove(rel)
                data = etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
            out.writestr(item,data)

def to_pdf(source, output_folder):
    source = Path(source).resolve()
    output_folder = Path(output_folder).resolve()
    output_folder.mkdir(parents=True,exist_ok=True)
    target = output_folder/(source.stem+'.pdf')
    binary = office_binary()
    if not binary:
        raise ValueError('LibreOffice is needed for PDF export. The Word file is still available.')
    with tempfile.TemporaryDirectory(prefix='office-',dir=DATA/'cache') as work:
        work = Path(work)
        profile = work/'profile'
        render_input = work/source.name
        if source.suffix.lower()=='.docx':
            safe_render_copy(source,render_input)
        else:
            shutil.copy2(source,render_input)
        env = dict(os.environ)
        env.update({'SAL_DISABLE_OPENCL':'1','SAL_USE_VCLPLUGIN':'svp'})
        command=[binary,f'-env:UserInstallation={profile.as_uri()}','--headless','--nologo','--nodefault','--norestore','--convert-to','pdf:writer_pdf_Export','--outdir',str(output_folder),str(render_input)]
        if sys.platform=='darwin':
            from .engine import MAC_NETWORK_PROFILE
            command=['/usr/bin/sandbox-exec','-p',MAC_NETWORK_PROFILE]+command
        result = subprocess.run(command,capture_output=True,timeout=150,env=env)
        if result.returncode or not target.exists():
            raise ValueError('PDF export did not complete. The Word file was preserved.')
    return target
