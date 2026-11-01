from pathlib import Path
from zipfile import ZipFile
from io import BytesIO
import csv
import hashlib
import re
import shutil
import subprocess
from lxml import etree
from PIL import Image, ImageOps
from .config import DATA
from .office import to_pdf

XML_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)
NS = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

def checked_zip(path):
    z = ZipFile(path)
    if sum(i.file_size for i in z.infolist()) > 180*1024*1024:
        z.close()
        raise ValueError('This compressed document is too large to open safely.')
    return z

def pdf_pages(path):
    import pdfplumber
    pages=[]
    with pdfplumber.open(path) as document:
        if len(document.pages)>120:
            raise ValueError('Please split documents longer than 120 pages before importing.')
        for index,page in enumerate(document.pages):
            text=page.extract_text(layout=False) or ''
            pages.append({'number':index+1,'text':text,'image':True,'kind':'pdf','pdf':str(path),'ocr_needed':len(text.strip())<40})
    return pages

def docx_paragraphs(path):
    with checked_zip(path) as z:
        root=etree.fromstring(z.read('word/document.xml'),parser=XML_PARSER)
    return [''.join(p.xpath('.//w:t/text()',namespaces=NS)) for p in root.xpath('/w:document/w:body//w:p',namespaces=NS)]

def read_ods(path):
    namespaces={'o':'urn:oasis:names:tc:opendocument:xmlns:table:1.0','t':'urn:oasis:names:tc:opendocument:xmlns:text:1.0'}
    with checked_zip(path) as z:
        root=etree.fromstring(z.read('content.xml'),parser=XML_PARSER)
    pages=[]
    for table in root.xpath('//o:table',namespaces=namespaces):
        lines=[]
        row_number=0
        for row in table.xpath('./o:table-row',namespaces=namespaces):
            repeat_rows=int(row.get('{'+namespaces['o']+'}number-rows-repeated','1'))
            if repeat_rows<1:raise ValueError('Invalid spreadsheet row repetition.')
            cells=[]
            for cell in row:
                text=' '.join(cell.xpath('.//t:p//text()',namespaces=namespaces))
                repeat=min(int(cell.get('{'+namespaces['o']+'}number-columns-repeated','1')),40)
                cells.extend([text]*repeat)
            if any(cells):
                if repeat_rows>10000:raise ValueError('The employee list repeats too many non-empty rows.')
                for offset in range(repeat_rows):
                    lines.append(f'Row {row_number+offset+1}: '+' | '.join(cells[:40]))
            row_number+=repeat_rows
            if len(lines)>10000:
                raise ValueError('The employee list is too large. Import the relevant sheet only.')
        pages.append({'number':len(pages)+1,'title':table.get('{'+namespaces['o']+'}name','Sheet'),'text':'\n'.join(lines),'kind':'text','image':False})
    return pages

def read_xlsx(path):
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with checked_zip(path) as z:
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            r=etree.fromstring(z.read('xl/sharedStrings.xml'),parser=XML_PARSER)
            shared=[''.join(x.xpath('.//s:t/text()',namespaces=ns)) for x in r]
        pages=[]
        for name in sorted(n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',n)):
            root=etree.fromstring(z.read(name),parser=XML_PARSER)
            lines=[]
            for row in root.xpath('//s:sheetData/s:row',namespaces=ns):
                cells=[]
                for cell in row:
                    value=''.join(cell.xpath('./s:v/text()|./s:is//s:t/text()',namespaces=ns))
                    if cell.get('t')=='s' and value.isdigit():
                        value=shared[int(value)]
                    cells.append(f'{cell.get("r","")}: {value}')
                lines.append('Row '+row.get('r',str(len(lines)+1))+': '+' | '.join(cells))
                if len(lines)>10000:
                    raise ValueError('The employee list is too large. Import the relevant sheet only.')
            pages.append({'number':len(pages)+1,'text':'\n'.join(lines),'kind':'text','image':False})
    return pages

def read_file(path):
    path=Path(path)
    suffix=path.suffix.lower()
    if suffix=='.pdf':
        return pdf_pages(path)
    if suffix=='.docx':
        digest=hashlib.sha256(path.read_bytes()).hexdigest()[:20]
        target=DATA/'cache'/digest
        try:
            pdf=to_pdf(path,target)
            return pdf_pages(pdf)
        except (ValueError,subprocess.TimeoutExpired):
            text='\n'.join(docx_paragraphs(path))
            return [{'number':1,'text':text,'kind':'text','image':False,'location_note':'Word text; page numbers unavailable until PDF rendering succeeds.'}]
    if suffix=='.ods':
        return read_ods(path)
    if suffix=='.xlsx':
        return read_xlsx(path)
    if suffix in {'.jpg','.jpeg','.png'}:
        with Image.open(path) as image:
            if image.width*image.height>70_000_000:
                raise ValueError('This image is too large. Please use a smaller scan.')
        return [{'number':1,'text':'','kind':'image','image':True,'path':str(path),'ocr_needed':True}]
    if suffix=='.csv':
        raw=path.read_text(encoding='utf-8-sig')
        records=list(csv.reader(raw.splitlines()))
        if len(records)>10000:raise ValueError('The employee list is too large.')
        text='\n'.join('Row '+str(i+1)+': '+' | '.join(row) for i,row in enumerate(records))
        return [{'number':1,'text':text,'kind':'text','image':False}]
    if suffix=='.txt':
        return [{'number':1,'text':path.read_text(encoding='utf-8-sig'),'kind':'text','image':False}]
    raise ValueError('Unsupported file type.')

def page_image(source, page_index, max_side=1600):
    page=source['pages'][page_index]
    if page['kind']=='pdf':
        import pypdfium2 as pdfium
        document=pdfium.PdfDocument(page['pdf'])
        pdf_page=document[page_index]
        width,height=pdf_page.get_size()
        bitmap=pdf_page.render(scale=min(2.0,max_side/max(width,height)))
        image=bitmap.to_pil().copy()
        bitmap.close();pdf_page.close();document.close()
    elif page['kind']=='image':
        with Image.open(page['path']) as raw:
            image=ImageOps.exif_transpose(raw).convert('RGB')
    else:
        return None
    image.thumbnail((max_side,max_side))
    output=BytesIO();image.convert('RGB').save(output,format='JPEG',quality=90)
    return output.getvalue()

def tesseract_binary():
    return shutil.which('tesseract') or next((str(p) for p in [Path('/opt/homebrew/bin/tesseract'),Path('C:/Program Files/Tesseract-OCR/tesseract.exe')] if p.exists()),None)

def ocr_image(image_bytes):
    binary=tesseract_binary()
    if not binary:
        return ''
    languages='ara+eng'
    command=[binary,'stdin','stdout','-l',languages,'--psm','3']
    if (DATA/'tessdata/ara.traineddata').exists() and (DATA/'tessdata/eng.traineddata').exists():
        command+=['--tessdata-dir',str(DATA/'tessdata')]
    result=subprocess.run(command,input=image_bytes,capture_output=True,timeout=90)
    return result.stdout.decode('utf-8',errors='replace') if result.returncode==0 else ''
