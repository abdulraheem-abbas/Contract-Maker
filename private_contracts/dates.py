"""Convert printed dates deterministically; never guess ambiguous numeric dates."""
import re
from datetime import date
from .fields import normalize,MONTHS_AR,MONTHS_EN

def dates_in(value):
    source=normalize(value).replace('،',' ').replace(',',' ')
    found=set()
    def add(y,m,d):
        try:
            if 1900<=int(y)<=2199:found.add(date(int(y),int(m),int(d)).isoformat())
        except ValueError:pass
    for match in re.finditer(r'(?<!\d)(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)',source):add(*match.groups())
    for match in re.finditer(r'(?<!\d)(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})(?!\d)',source):
        a,b,y=map(int,match.groups())
        if a>12 or a==b:add(y,b,a)
        elif b>12:add(y,a,b)
    names={}
    for i,name in enumerate(MONTHS_EN[1:],1):names[name.casefold()]=i;names[name[:3].casefold()]=i
    for i,name in enumerate(MONTHS_AR[1:],1):names[name]=i;names[name.replace('أ','ا')]=i
    names.update({'كانون الثاني':1,'شباط':2,'آذار':3,'نيسان':4,'أيار':5,'حزيران':6,'تموز':7,'آب':8,'أيلول':9,'تشرين الأول':10,'تشرين الثاني':11,'كانون الأول':12})
    month_pattern='|'.join(re.escape(n) for n in sorted(names,key=len,reverse=True))
    for match in re.finditer(r'(?<!\d)(\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?('+month_pattern+r')\s*(\d{4})(?!\d)',source,re.I):
        d,m,y=match.groups();add(y,names[m.casefold()],d)
    for match in re.finditer(r'(?<!\w)('+month_pattern+r')\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})(?!\d)',source,re.I):
        m,d,y=match.groups();add(y,names[m.casefold()],d)
    return found

def printed_date(value,quote=''):
    values=dates_in(value)
    if len(values)==1:return next(iter(values))
    quoted=dates_in(quote)
    return next(iter(quoted)) if len(quoted)==1 else None
