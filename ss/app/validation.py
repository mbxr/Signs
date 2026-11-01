import re
from datetime import datetime
from email.utils import parseaddr

def validate(key, text):
    value = (text or '').strip()
    warnings=[]
    if not value: return value, 'No text detected — review the image'
    if key=='telephone':
        digits=re.sub(r'\D','',value)
        if len(digits)==11 and digits.startswith('1'): digits=digits[1:]
        if len(digits)==10:
            value=f'{digits[:3]}-{digits[3:6]}-{digits[6:]}'
        else: warnings.append('Telephone does not contain 10 digits')
    elif key=='email':
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[A-Za-z]{2,}',value):
            warnings.append('Email format needs verification')
    elif key=='rate':
        if not re.search(r'\d',value): warnings.append('Rate does not contain a recognizable number')
    elif key in ('date_required','return_date'):
        # Do not invent a year or mistake "overnight" for a calendar date.
        if not re.search(r'\d|overnight|next day|same day',value,re.I):
            warnings.append('Date/return terms need review')
    return value, '; '.join(warnings) if warnings else None
