"""Local, versioned Word template changes with an explicit draft/activate step."""
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from threading import RLock
from zipfile import ZipFile, BadZipFile
import hashlib
import json
import os
import re
import uuid
from lxml import etree
from .config import DATA
from .fields import FIELD_KEYS
from .templates import NS, W, TOKEN, parse, text, replace_value, registry

LOCK = RLock()
KINDS = {'employment': 'Employment contract', 'service': 'Service contract', 'extension': 'Extension letter'}
TOKENS = FIELD_KEYS | {
    'execution_ar', 'execution_en', 'start_ar', 'start_en', 'end_ar', 'end_en',
    'original_ar', 'original_en', 'weekday_ar', 'weekday_en',
    'identity_details_ar', 'identity_details_en', 'salary_words_ar', 'salary_words_en',
    'honorific_ar', 'honorific_en', 'nationality_ar', 'refer_ar',
    'manager_base_clause_ar', 'manager_base_clause_en',
}


def check_kind(kind):
    if kind not in KINDS:
        raise ValueError('Choose a supported contract type.')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def checked_contents(raw):
    if not raw or len(raw) > 25 * 1024 * 1024:
        raise ValueError('Choose a Word template up to 25 MB.')
    try:
        with ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            if len(infos) > 5000 or sum(i.file_size for i in infos) > 180 * 1024 * 1024:
                raise ValueError('This Word template is too large to open.')
            if len(names) != len(set(names)) or any(i.flag_bits & 1 for i in infos):
                raise ValueError('Choose an unencrypted Word document without duplicate parts.')
            if any(n.startswith('/') or '..' in Path(n).parts for n in names):
                raise ValueError('This Word package contains an invalid part name.')
            if not {'[Content_Types].xml', 'word/document.xml'} <= set(names):
                raise ValueError('Choose a valid .docx Word document.')
            if any('vbaproject' in n.lower() or n.startswith('word/embeddings/') for n in names):
                raise ValueError('Remove macros and embedded files from the Word template first.')
            contents = {i.filename: archive.read(i.filename) for i in infos}
        for name, data in contents.items():
            if name.endswith(('.xml', '.rels')):
                node = parse(data)
                if node.getroottree().docinfo.doctype:
                    raise ValueError('This Word document contains an unsupported XML declaration.')
                if name.endswith('.rels'):
                    for rel in node:
                        if rel.get('TargetMode') == 'External' and not rel.get('Type', '').endswith('/hyperlink'):
                            raise ValueError('Embed linked images or other linked content in Word before importing it.')
        root = parse(contents['word/document.xml'])
        if root.tag != W + 'document' or root.find('w:body', NS) is None:
            raise ValueError('Choose a valid .docx Word document.')
        if root.xpath('//w:ins|//w:del|//w:moveFrom|//w:moveTo', namespaces=NS):
            raise ValueError('Accept or reject tracked changes in Word before importing this template.')
        return contents, root
    except (BadZipFile, KeyError, etree.XMLSyntaxError, RuntimeError) as exc:
        raise ValueError('This file could not be read as a .docx Word document.') from exc


def inspect(raw, previous_tokens=()):
    contents, root = checked_contents(raw)
    paragraphs = [{'index': i, 'text': text(p)} for i, p in enumerate(root.xpath('//w:p', namespaces=NS)) if text(p).strip()]
    placeholders = sorted(set(t for p in paragraphs for t in TOKEN.findall(p['text'])))
    errors = []
    warnings = []
    unknown = sorted(set(placeholders) - TOKENS)
    if unknown:
        errors.append('Unsupported field tags: ' + ', '.join(unknown) + '. Map them to a supported field.')
    if any('{{' in TOKEN.sub('', p['text']) or '}}' in TOKEN.sub('', p['text']) for p in paragraphs):
        errors.append('An incomplete field tag was found. Use the field mapper to replace it.')
    for name, data in contents.items():
        if name.startswith('word/') and name.endswith('.xml') and name != 'word/document.xml':
            if '{{' in text(parse(data)):
                errors.append('Field tags in headers, footers or other Word parts are not supported. Put changing fields in the document body.')
                break
    for key in ['name_ar', 'name_en']:
        if key not in placeholders:
            errors.append('Map the employee name in ' + ('Arabic' if key.endswith('_ar') else 'English') + ' before using this template.')
    for prefix, label in [('execution', 'contract date'), ('start', 'start date'), ('end', 'end date')]:
        if not ({prefix + '_ar', prefix + '_en', {'execution': 'execution_date', 'start': 'start_date', 'end': 'end_date'}[prefix]} & set(placeholders)):
            errors.append('Map the ' + label + ' before using this template.')
    missing = sorted(set(previous_tokens) - set(placeholders))
    if missing:
        warnings.append('Fields present in the active template are absent here: ' + ', '.join(missing) + '. Check whether they need mapping.')
    warnings.append('Check that every employee-specific value is a field tag, including repeated names, document numbers, dates and signature details in both languages.')
    return {'paragraphs': paragraphs, 'placeholders': placeholders, 'errors': errors, 'warnings': warnings}


def _raw_registry():
    path = DATA / 'templates/registry.json'
    return json.loads(path.read_text()) if path.exists() else {}


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value):
        raise ValueError('This template version could not be found.')
    return value


def _draft(kind, draft):
    check_kind(kind)
    folder = DATA / 'templates' / kind / 'drafts' / _id(draft)
    if not (folder / 'draft.json').is_file():
        raise ValueError('This draft could not be found. Choose the Word file again.')
    return folder, json.loads((folder / 'draft.json').read_text())


def active(kind, expected_sha=None):
    check_kind(kind)
    entry = registry().get(kind, {})
    sha = entry.get('sha256', '')
    if expected_sha is not None and expected_sha != sha:
        raise ValueError('The active template changed in another window. Reload Templates and check the new version.')
    if not entry.get('path') or not Path(entry['path']).is_file():
        raise ValueError('Choose a Word template for this contract type first.')
    raw = Path(entry['path']).read_bytes()
    if digest(raw) != sha:
        raise ValueError('The template changed outside the app. Replace it in Templates before continuing.')
    return entry, raw


def _new_draft(kind, raw, name, base_sha):
    inspect(raw)
    draft = uuid.uuid4().hex
    folder = DATA / 'templates' / kind / 'drafts' / draft
    folder.mkdir(parents=True)
    (folder / 'template.docx').write_bytes(raw)
    atomic_json(folder / 'draft.json', {'name': name, 'base_sha': base_sha, 'created': datetime.now(timezone.utc).isoformat(), 'sha256': digest(raw)})
    return draft


def stage(kind, name, raw, expected_sha):
    check_kind(kind)
    if Path(name).suffix.lower() != '.docx':
        raise ValueError('Choose a .docx Word template.')
    with LOCK:
        current = registry().get(kind, {})
        if current.get('sha256', '') != expected_sha:
            raise ValueError('The active template changed. Reload Templates before replacing it.')
        draft = _new_draft(kind, raw, Path(name.replace('\\', '/')).name[:200], expected_sha)
        return describe(kind, draft)


def file_path(kind, draft=None, version=None, pdf=False, expected_sha=None):
    check_kind(kind)
    if draft:
        folder, metadata = _draft(kind, draft)
        path = folder / 'template.docx'
        if digest(path.read_bytes()) != metadata['sha256']:
            raise ValueError('The draft changed outside the app. Import it again.')
    elif version:
        entry = registry().get(kind, {})
        candidates = [entry] + entry.get('history', [])
        selected = next((e for e in candidates if e.get('version') == _id(version)), None)
        if not selected:
            raise ValueError('This saved template version could not be found.')
        path = DATA / 'templates' / kind / 'versions' / version / 'template.docx'
        if not path.is_file() or digest(path.read_bytes()) != selected['sha256']:
            raise ValueError('This saved version changed outside the app.')
    else:
        entry, _ = active(kind)
        path = Path(entry['path'])
    if expected_sha and digest(path.read_bytes()) != expected_sha:
        raise ValueError('The template changed. Reload its fields and preview before continuing.')
    if pdf:
        # The preview is keyed by content, including for immutable saved versions.
        path = DATA / 'cache/template-previews' / digest(path.read_bytes()) / 'template.pdf'
        if not path.is_file():
            raise ValueError('Create the local preview first.')
    return path


def describe(kind, draft=None):
    with LOCK:
        entry = registry().get(kind, {})
        name = entry.get('source_name', KINDS.get(kind, kind))
        base_sha = entry.get('sha256', '')
        if draft:
            folder, metadata = _draft(kind, draft)
            raw = file_path(kind, draft).read_bytes()
            name = metadata['name']
            base_sha = metadata['base_sha']
        else:
            _, raw = active(kind)
        report = inspect(raw, entry.get('placeholders', []))
        return {**report, 'kind': kind, 'draft': draft, 'name': name, 'sha256': digest(raw),
                'base_sha': base_sha, 'tokens': sorted(TOKENS), 'history': [
                    {k: v for k, v in old.items() if k in {'version', 'source_name', 'saved_at', 'sha256'}}
                    for old in entry.get('history', [])]}


def map_fields(kind, draft, expected_sha, mappings):
    if not isinstance(mappings, list) or not mappings or len(mappings) > 100:
        raise ValueError('Choose text and a field to map.')
    with LOCK:
        if not draft:
            _, raw = active(kind, expected_sha)
            draft = _new_draft(kind, raw, 'Edited template', expected_sha)
        folder, metadata = _draft(kind, draft)
        raw = file_path(kind, draft).read_bytes()
        if digest(raw) != expected_sha:
            raise ValueError('This draft changed in another window. Reload its fields before editing.')
        contents, root = checked_contents(raw)
        paragraphs = root.xpath('//w:p', namespaces=NS)
        for mapping in mappings:
            index = int(mapping['paragraph'])
            key = str(mapping['key'])
            before = str(mapping['before'])
            if key not in TOKENS or not 0 <= index < len(paragraphs):
                raise ValueError('Choose a supported field and paragraph.')
            if not before.strip():
                raise ValueError('Select the exact text to replace.')
            replace_value(paragraphs[index], before, '{{' + key + '}}')
        contents['word/document.xml'] = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
        buffer = BytesIO()
        with ZipFile(BytesIO(raw)) as source, ZipFile(buffer, 'w') as output:
            for info in source.infolist():
                output.writestr(info, contents[info.filename])
        # Each edit creates a new draft. A preview or another window can keep
        # reading the preceding immutable draft without a race.
        new_draft = _new_draft(kind, buffer.getvalue(), metadata['name'], metadata['base_sha'])
        return describe(kind, new_draft)


def _save_version(kind, raw, entry):
    version = uuid.uuid4().hex
    path = DATA / 'templates' / kind / 'versions' / version / 'template.docx'
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    return {**{k: v for k, v in entry.items() if k not in {'history', 'original'}}, 'version': version,
            'path': str(path.relative_to(DATA)), 'sha256': digest(raw),
            'saved_at': datetime.now(timezone.utc).isoformat()}


def activate(kind, draft, expected_sha, reviewed):
    if reviewed is not True:
        raise ValueError('Check the template wording and all changing fields before activating it.')
    with LOCK:
        report = describe(kind, draft)
        if report['sha256'] != expected_sha:
            raise ValueError('The draft changed. Check its fields again before activating it.')
        if report['errors']:
            raise ValueError(' '.join(report['errors']))
        entries = _raw_registry()
        old = deepcopy(entries.get(kind, {}))
        if old.get('sha256', '') != report['base_sha']:
            raise ValueError('The active template changed since this draft was started. Import the draft again against the new version.')
        history = old.pop('history', [])
        if old.get('path'):
            _, old_raw = active(kind)
            saved = old if old.get('version') else _save_version(kind, old_raw, old)
            history.insert(0, saved)
        raw = file_path(kind, draft).read_bytes()
        entry = _save_version(kind, raw, {'label': old.get('label', KINDS[kind]), 'source_name': report['name'],
                                        'placeholders': report['placeholders'], 'ready': True})
        entries[kind] = {**entry, 'history': history}
        atomic_json(DATA / 'templates/registry.json', entries)
        return {'ok': True, 'version': entry['version']}


def restore_draft(kind, version, expected_sha):
    with LOCK:
        entry, _ = active(kind, expected_sha)
        selected = next((e for e in entry.get('history', []) if e.get('version') == version), None)
        if not selected:
            raise ValueError('This previous template version could not be found.')
        raw = file_path(kind, version=version).read_bytes()
        draft = _new_draft(kind, raw, selected.get('source_name', 'Restored template'), expected_sha)
        return describe(kind, draft)


def preview(kind, draft=None, progress=lambda message: None, cancelled=lambda: False, source=None):
    from .office import to_pdf
    from .readers import page_image
    from pypdf import PdfReader
    path = source or file_path(kind, draft)
    sha = digest(path.read_bytes())
    folder = DATA / 'cache/template-previews' / sha
    folder.mkdir(parents=True, exist_ok=True)
    # Always use a fixed stem so the viewer has a stable PDF filename.
    local = folder / 'template.docx'
    if not local.exists():
        local.write_bytes(path.read_bytes())
    pdf = to_pdf(local, folder)
    count = len(PdfReader(pdf).pages)
    if count > 120:
        raise ValueError('Please use a template with at most 120 pages.')
    pages = [{'kind': 'pdf', 'pdf': str(pdf)} for _ in range(count)]
    for index in range(count):
        if cancelled():
            return None
        progress(f'Rendering template page {index + 1} of {count} on this computer')
        target = folder / f'page-{index + 1:04d}.jpg'
        if not target.exists():
            target.write_bytes(page_image({'pages': pages}, index, max_side=1800))
    return {'pages': count, 'sha256': sha}
