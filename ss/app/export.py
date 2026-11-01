"""Create Excel files, avoiding spreadsheet formula injection."""
from datetime import datetime,timezone
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter
from .template import FIELD_LABELS

def literal_text(value):
    """Force user input to a literal text cell, even if it begins with =,+,-,@."""
    if value is None: return ''
    return str(value)

def build_workbook(orders,fields_by_id):
    wb=Workbook()
    sheet=wb.active;sheet.title='Orders'
    keys=list(FIELD_LABELS)
    headers=['Order ID','Batch ID','Original filename','Processing status','Review status']+[FIELD_LABELS[k] for k in keys]+['Uploaded at','Extraction warning']
    sheet.append(headers)
    for order in orders:
        fs=fields_by_id.get(order.id,{})
        warnings='; '.join(f'{k}: {fs[k].warning}' for k in keys if k in fs and fs[k].warning)
        vals=[order.id,order.batch_id,order.filename,order.status,order.review_status]
        vals += [literal_text(fs[k].value) if k in fs else '' for k in keys]
        vals += [order.created_at.strftime('%Y-%m-%d %H:%M UTC') if order.created_at else '',warnings]
        sheet.append(vals)
        i=sheet.max_row
        # All data originating from the user or OCR is literal string, not a formula.
        for col in [3,*range(6,6+len(keys)),len(headers)]:
            sheet.cell(i,col).data_type='s'
    sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
    for cell in sheet[1]:
        cell.fill=PatternFill('solid',fgColor='153E52')
        cell.font=Font(color='FFFFFF',bold=True)
        cell.alignment=Alignment(vertical='center',wrap_text=True)
    sheet.row_dimensions[1].height=34
    widths=[11,11,28,18,18,25,18,30,20,18,18,22,20,37,18,22,40,30,19,22,48]
    for i,width in enumerate(widths[:len(headers)],start=1):
        sheet.column_dimensions[get_column_letter(i)].width=width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment=Alignment(vertical='top',wrap_text=True)
        sheet.row_dimensions[row[0].row].height=30
    # These tabs preserve provenance and make incomplete extraction visible,
    # without changing the one-row-per-order structure in the Orders tab.
    raw=wb.create_sheet('Original OCR')
    raw.append(['Order ID','Original filename']+[FIELD_LABELS[k] for k in keys])
    review=wb.create_sheet('Review queue')
    review.append(['Order ID','Original filename','Processing status','Review status','Fields needing review','Extraction warnings'])
    for order in orders:
        fields=fields_by_id.get(order.id,{})
        raw.append([order.id, literal_text(order.filename)]+[literal_text(fields[k].raw_text) if k in fields else '' for k in keys])
        for col in range(2,raw.max_column+1):
            raw.cell(raw.max_row,col).data_type='s'
        pending=[FIELD_LABELS[k] for k in keys if k not in fields or not fields[k].reviewed]
        issues='; '.join(f'{FIELD_LABELS[k]}: {fields[k].warning}' for k in keys if k in fields and fields[k].warning)
        if pending or order.status not in ('completed','manual') or order.review_status!='reviewed':
            review.append([order.id,literal_text(order.filename),order.status,order.review_status,', '.join(pending),issues])
            for col in (2,5,6):
                review.cell(review.max_row,col).data_type='s'
    for tab in (raw,review):
        tab.freeze_panes='A2'
        tab.auto_filter.ref=tab.dimensions
        for cell in tab[1]:
            cell.fill=PatternFill('solid',fgColor='153E52')
            cell.font=Font(color='FFFFFF',bold=True)
        for col in range(1,tab.max_column+1):
            tab.column_dimensions[get_column_letter(col)].width=35 if col>1 else 12
    review.column_dimensions['E'].width=65
    review.column_dimensions['F'].width=65
    notes=wb.create_sheet('Read me')
    notes.append(['Surprise Signs — digitized order forms'])
    notes.append(['One row per uploaded order. Blanks and warnings require review.'])
    notes.append(['Original OCR tab contains uncorrected model readings; Orders tab contains human edits where provided.'])
    notes.append(['Review queue tab identifies records not yet fully verified.'])
    notes.append(['Original handwriting is not guaranteed accurate until reviewed.'])
    notes.append(['Timestamps are server UTC. No missing date year was inferred.'])
    notes.column_dimensions['A'].width=95
    stream=BytesIO();wb.save(stream);stream.seek(0)
    return stream
