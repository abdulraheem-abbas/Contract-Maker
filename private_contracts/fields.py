from datetime import date
from decimal import Decimal, InvalidOperation
import re
import unicodedata

FIELDS = [
    ('contract_type', 'Contract type', 'نوع العقد', 'select'),
    ('name_ar', 'Full name · Arabic', 'الاسم الكامل بالعربية', 'text'),
    ('name_en', 'Full name · English', 'الاسم الكامل بالإنجليزية', 'text'),
    ('gender', 'Employee gender', 'الجنس', 'select'),
    ('identity_type', 'Identity document type', 'نوع وثيقة الهوية', 'select'),
    ('identity_number', 'Identity / passport number', 'رقم الهوية أو الجواز', 'text'),
    ('identity_issue_date', 'Document issue date', 'تاريخ إصدار الوثيقة', 'date'),
    ('identity_expiry_date', 'Document expiry date', 'تاريخ انتهاء الوثيقة', 'date'),
    ('issuer_ar', 'Issuing city · Arabic', 'مدينة الإصدار بالعربية', 'text'),
    ('issuer_en', 'Issuing city · English', 'مدينة الإصدار بالإنجليزية', 'text'),
    ('execution_date', 'Contract and signature date', 'تاريخ إبرام وتوقيع العقد', 'date'),
    ('start_date', 'Work start date', 'تاريخ بدء العمل', 'date'),
    ('end_date', 'Contract end date', 'تاريخ انتهاء العقد', 'date'),
    ('original_contract_date', 'Original contract date · extension', 'تاريخ العقد الأصلي للتمديد', 'date'),
    ('job_title_ar', 'Job title · Arabic', 'المسمى الوظيفي بالعربية', 'text'),
    ('job_title_en', 'Job title · English', 'المسمى الوظيفي بالإنجليزية', 'text'),
    ('grade_ar', 'Job grade · Arabic', 'الدرجة الوظيفية بالعربية', 'text'),
    ('grade_en', 'Job grade · English', 'الدرجة الوظيفية بالإنجليزية', 'text'),
    ('workplace_ar', 'Workplace · Arabic', 'مكان العمل بالعربية', 'text'),
    ('workplace_en', 'Workplace · English', 'مكان العمل بالإنجليزية', 'text'),
    ('salary_usd', 'Monthly gross salary · USD', 'الأجر الشهري الشامل بالدولار', 'text'),
    ('manager_title_ar', 'Reporting manager title · Arabic', 'مسمى المدير المباشر بالعربية', 'text'),
    ('manager_title_en', 'Reporting manager title · English', 'مسمى المدير المباشر بالإنجليزية', 'text'),
    ('manager_name_ar', 'Reporting manager name · Arabic', 'اسم المدير المباشر بالعربية', 'text'),
    ('manager_name_en', 'Reporting manager name · English', 'اسم المدير المباشر بالإنجليزية', 'text'),
    ('manager_base_ar', 'Manager workplace · Arabic', 'مقر المدير المباشر بالعربية', 'text'),
    ('manager_base_en', 'Manager workplace · English', 'مقر المدير المباشر بالإنجليزية', 'text'),
    ('project_ar', 'Project name · Arabic', 'اسم المشروع بالعربية', 'text'),
    ('project_en', 'Project name · English', 'اسم المشروع بالإنجليزية', 'text'),
]
FIELD_KEYS = {f[0] for f in FIELDS}
LABELS = {f[0]: f[1] for f in FIELDS}
IDENTITY_KEYS = {'name_ar', 'name_en', 'gender', 'identity_type', 'identity_number', 'identity_issue_date', 'identity_expiry_date', 'issuer_ar', 'issuer_en'}
LIST_KEYS = {'workplace_ar', 'workplace_en', 'manager_title_ar', 'manager_title_en', 'manager_name_ar', 'manager_name_en', 'manager_base_ar', 'manager_base_en'}
OFFER_KEYS = {'contract_type', 'execution_date', 'start_date', 'end_date', 'original_contract_date', 'job_title_ar', 'job_title_en', 'grade_ar', 'grade_en', 'salary_usd', 'project_ar', 'project_en'}
MONTHS_AR = ['', 'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']
MONTHS_EN = ['', 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
DAYS_AR = ['الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']
DAYS_EN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')

def normalize(value):
    value = unicodedata.normalize('NFKC', str(value)).translate(DIGITS)
    return re.sub(r'\s+', ' ', re.sub('[\u200e\u200f\u2060\u202a-\u202e\u2066-\u2069]', '', value)).strip()

def compact(value):
    return re.sub(r'\s+', '', normalize(value)).casefold()

def arabic_name_key(value):
    value = normalize(value).translate(str.maketrans('أإآىة', 'ااايه'))
    return re.sub(r'[\u064b-\u065f\u0670ـ\s]', '', value)

def as_date(value):
    value=normalize(value)
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',value):raise ValueError('Use YYYY-MM-DD.')
    return date.fromisoformat(value)

def date_display(value, language='en'):
    d = as_date(value)
    months = MONTHS_AR if language == 'ar' else MONTHS_EN
    return f'{d.day} {months[d.month]} {d.year}'

def weekday(value, language='en'):
    return (DAYS_AR if language == 'ar' else DAYS_EN)[as_date(value).weekday()]

def identity_date(value):
    return as_date(value).strftime('%d/%m/%Y')

def salary_amount(value):
    text = normalize(value).replace('$', '').replace(',', '').strip()
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError('Enter the gross salary as a number, such as 825.69.') from exc
    if not number.is_finite() or number <= 0 or number > Decimal('1000000') or number.as_tuple().exponent < -2:
        raise ValueError('Salary must be positive, with at most two decimal places.')
    return number

def salary_words(value, language):
    from num2words import num2words
    number = salary_amount(value)
    whole = int(number)
    cents = int((number - whole) * 100)
    if language == 'ar':
        result = f'{num2words(whole, lang="ar")} دولار أمريكي'
        return result + (f' و{num2words(cents, lang="ar")} سنت' if cents else '')
    result = num2words(whole, lang='en').replace(',', '').title() + ' US Dollars'
    return result + (' and ' + num2words(cents, lang='en').replace(',', '').title() + ' Cents' if cents else '')

def required_fields(kind):
    common = {'contract_type', 'name_ar', 'name_en', 'gender', 'identity_type', 'identity_number', 'identity_issue_date', 'execution_date', 'start_date', 'end_date', 'job_title_ar', 'job_title_en', 'workplace_ar', 'workplace_en', 'salary_usd', 'manager_title_ar', 'manager_title_en'}
    if kind == 'employment':
        return common | {'grade_ar', 'grade_en'}
    if kind == 'service':
        return common | {'manager_name_ar', 'manager_name_en', 'project_ar', 'project_en'}
    return {'contract_type', 'name_ar', 'name_en', 'execution_date', 'start_date', 'end_date','original_contract_date'}

def validate(values, require_confirmation=False):
    issues = []
    kind = values.get('contract_type', {}).get('value', '')
    if kind not in {'employment', 'service', 'extension'}:
        issues.append({'level':'error', 'field':'contract_type', 'message':'Choose the contract type.'})
    for key,allowed in [('identity_type',{'passport','id_card','national_id',''}),('gender',{'male','female',''})]:
        if values.get(key,{}).get('value','') not in allowed:
            issues.append({'level':'error','field':key,'message':f'Choose a supported value for {LABELS[key]}.'})
    if require_confirmation:
        relevant=set(required_fields(kind))|{'gender','issuer_ar','issuer_en','identity_expiry_date'}
        if kind=='service':relevant|={'manager_base_ar','manager_base_en'}
        for key in relevant-required_fields(kind):
            field=values.get(key,{})
            if field.get('value') and not field.get('confirmed'):
                issues.append({'level':'error','field':key,'message':f'Confirm {LABELS[key]} before using it.'})
    for key in required_fields(kind):
        field = values.get(key, {})
        if not str(field.get('value', '')).strip():
            issues.append({'level':'error', 'field':key, 'message':f'{LABELS.get(key, key)} is missing.'})
        elif require_confirmation and not field.get('confirmed'):
            issues.append({'level':'error', 'field':key, 'message':f'Confirm {LABELS.get(key, key)} against its source.'})
    parsed = {}
    for key in ['execution_date', 'start_date', 'end_date', 'original_contract_date', 'identity_issue_date', 'identity_expiry_date']:
        value = values.get(key, {}).get('value', '')
        if value:
            try:
                parsed[key] = as_date(value)
            except ValueError:
                issues.append({'level':'error', 'field':key, 'message':'Use an unambiguous date in YYYY-MM-DD format.'})
    if parsed.get('start_date') and parsed.get('end_date') and parsed['start_date'] > parsed['end_date']:
        issues.append({'level':'error','field':'end_date','message':'The contract end precedes the start date.'})
    if parsed.get('execution_date') and parsed.get('start_date') and parsed['execution_date'] > parsed['start_date']:
        issues.append({'level':'warning','field':'execution_date','message':'Signature date is later than work start. Confirm that this is intended.'})
    expiry = parsed.get('identity_expiry_date')
    execution = parsed.get('execution_date', date.today())
    if expiry and parsed.get('identity_issue_date') and expiry<parsed['identity_issue_date']:
        issues.append({'level':'error','field':'identity_expiry_date','message':'Identity expiry precedes its issue date.'})
    if parsed.get('identity_issue_date') and parsed['identity_issue_date']>execution:
        issues.append({'level':'warning','field':'identity_issue_date','message':'The identity document was issued after the contract date. Check that this is the intended document.'})
    if expiry and expiry < execution:
        issues.append({'level':'warning','field':'identity_expiry_date','message':'This identity document expired before the contract date. Explicitly confirm using these supplied details.'})
    elif expiry and parsed.get('end_date') and expiry < parsed['end_date']:
        issues.append({'level':'warning','field':'identity_expiry_date','message':'This identity document expires during the contract period.'})
    if values.get('salary_usd', {}).get('value'):
        try:
            salary_amount(values['salary_usd']['value'])
        except ValueError as exc:
            issues.append({'level':'error','field':'salary_usd','message':str(exc)})
    number = normalize(values.get('identity_number', {}).get('value', ''))
    if number and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 /\-]{2,39}', number):
        issues.append({'level':'error','field':'identity_number','message':'Identity numbers must contain only letters, digits, spaces, slashes or hyphens. Leading zeros are retained.'})
    if kind == 'employment':
        for lang in ['ar','en']:
            title = values.get('job_title_'+lang, {}).get('value','')
            project=normalize(values.get('project_'+lang,{}).get('value',''))
            if ('في مشروع' in title) or re.search(r'\b(in|for)\s+(the\s+)?project\b', title, re.I) or (len(project)>3 and re.search(r'(?<!\w)'+re.escape(project)+r'(?!\w)',normalize(title),re.I)):
                issues.append({'level':'error','field':'job_title_'+lang,'message':'Employment contracts use the job title only. Remove the project phrase from this field.'})
            name=normalize(values.get('manager_name_'+lang,{}).get('value',''))
            reporting=normalize(values.get('manager_title_'+lang,{}).get('value',''))
            if name and re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',reporting,re.I):
                issues.append({'level':'error','field':'manager_title_'+lang,'message':'Employment contracts use the reporting manager title only. Remove the personal name from this field.'})
    for key in ['issuer_ar', 'issuer_en']:
        value = values.get(key, {}).get('value', '')
        if re.search(r'مركز|المركز|مجمع|\b(center|centre|complex)\b', value, re.I):
            issues.append({'level':'error','field':key,'message':'Enter the issuing city only, without a centre or complex name.'})
        elif re.search(r'\d',normalize(value)):
            issues.append({'level':'error','field':key,'message':'Enter the issuing city only, without a centre number.'})
    if bool(values.get('issuer_ar', {}).get('value')) != bool(values.get('issuer_en', {}).get('value')):
        issues.append({'level':'error','field':'issuer_ar','message':'Enter the issuing city in both languages, or leave both empty if it is not stated.'})
    known_cities={'عدن':{'aden'},'لحج':{'lahj'},'تعز':{'taiz','taizz'},'صنعاء':{'sanaa',"sana'a",'sana’a'},'حيس':{'hays','hais'}}
    city_ar=normalize(values.get('issuer_ar',{}).get('value',''))
    city_en=normalize(values.get('issuer_en',{}).get('value','')).casefold()
    if city_ar in known_cities and city_en and city_en not in known_cities[city_ar]:
        issues.append({'level':'error','field':'issuer_en','message':'The issuing city does not match between Arabic and English.'})
    return issues

def empty_fields():
    return {key:{'value':'','confirmed':False,'evidence':[],'origin':'empty'} for key in FIELD_KEYS}
