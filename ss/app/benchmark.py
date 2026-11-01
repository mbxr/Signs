"""Privacy-preserving benchmark against a locally held ground-truth CSV.

Usage (inside api container, which shares /data):
  python -m app.benchmark /data/ground_truth.csv

CSV requires order_id and any number of field-key columns. Values aren't printed.
This measures extraction accuracy on the *original OCR results*, not manually
corrected database values; edited fields remain suitable for spreadsheet export.
"""
import csv
import json
import sys
import unicodedata
from pathlib import Path
from .db import initialize, SessionLocal, Order, Field
from .template import FIELD_LABELS


def canonical(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value or '')).split())


def distance(a, b):
    """Levenshtein distance, linear auxiliary memory."""
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i]
        for j, char_b in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j-1] + 1,
                               previous[j-1] + int(char_a != char_b)))
        previous = current
    return previous[-1]


def measure(ground_truth, predictions):
    """Aggregate only; no personal information in output."""
    stats = {key: {'evaluated': 0, 'exact_matches': 0, 'edits': 0, 'characters': 0}
             for key in FIELD_LABELS}
    total = 0
    completely_correct = 0
    not_found = 0
    for row in ground_truth:
        identifier = row.get('order_id', '')
        if not identifier or not identifier.isdigit():
            raise ValueError('Every ground-truth row must include a numeric order_id')
        total += 1
        values = predictions.get(int(identifier))
        if values is None:
            not_found += 1
            continue
        all_correct = True
        any_evaluated = False
        for key in FIELD_LABELS:
            if key not in row or row[key] == '':
                continue  # Missing reference value isn't interpreted as ground truth.
            any_evaluated = True
            expected = canonical(row[key])
            actual = canonical(values.get(key, ''))
            stat = stats[key]
            stat['evaluated'] += 1
            stat['exact_matches'] += int(expected == actual)
            stat['edits'] += distance(expected, actual)
            stat['characters'] += len(expected)
            if expected != actual:
                all_correct = False
        completely_correct += int(all_correct and any_evaluated)
    fields = {}
    for key, stat in stats.items():
        n = stat['evaluated']
        if n:
            fields[key] = {
                'evaluated': n,
                'exact_match_rate': round(stat['exact_matches'] / n, 4),
                'character_error_rate': round(stat['edits'] / max(stat['characters'], 1), 4),
            }
    return {'ground_truth_orders': total, 'missing_order_ids': not_found,
            'complete_order_exact_match_rate': round(completely_correct / total, 4) if total else None,
            'fields': fields,
            'note': 'Empty CSV fields are excluded. OCR raw_text is compared, not corrected values. This benchmark does not independently validate checkbox calibration.'}


def run(path):
    initialize()
    with Path(path).open('r', encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle))
    if not rows or 'order_id' not in rows[0]:
        raise ValueError('CSV must have a header order_id and at least one ground-truth row')
    wrong = set(rows[0]) - set(FIELD_LABELS) - {'order_id'}
    if wrong:
        raise ValueError('Unknown CSV columns: ' + ', '.join(sorted(wrong)))
    ids = [int(row['order_id']) for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('Ground-truth CSV has duplicate order IDs')
    with SessionLocal() as db:
        fields = db.query(Field).filter(Field.order_id.in_(ids)).all()
        available_ids = {r[0] for r in db.query(Order.id).filter(Order.id.in_(ids)).all()}
    predictions = {key: {} for key in available_ids}
    for field in fields:
        predictions[field.order_id][field.key] = field.raw_text
    return measure(rows, predictions)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python -m app.benchmark /data/ground_truth.csv')
    print(json.dumps(run(sys.argv[1]), indent=2))
