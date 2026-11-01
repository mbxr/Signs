"""Field bounding boxes are normalized to [0,1] on the reference photograph.
These initial regions were estimated from a single sample. ALWAYS calibrate first.
"""
FIELD_LABELS = {
    'name':'Customer name', 'telephone':'Telephone', 'email':'Email',
    'delivery':'Delivery checkbox', 'pickup':'Pickup checkbox',
    'date_required':'Date required', 'return_date':'Return date',
    'address':'Address', 'sign':'Sign', 'ornaments':'Ornaments',
    'message':'Message on sign', 'notes':'Notes', 'rate':'Rate quoted',
}
DEFAULT_REGIONS = {
    'name': [0.34,0.288,0.78,0.340],
    'telephone': [0.47,0.334,0.82,0.385],
    'email': [0.46,0.374,0.91,0.458],
    'delivery': [0.245,0.398,0.285,0.424],
    'pickup': [0.414,0.404,0.452,0.432],
    'date_required': [0.45,0.426,0.84,0.481],
    'return_date': [0.57,0.469,0.84,0.523],
    'address': [0.33,0.504,0.88,0.567],
    'sign': [0.35,0.563,0.77,0.602],
    'ornaments': [0.39,0.591,0.89,0.647],
    'message': [0.31,0.649,0.93,0.721],
    'notes': [0.25,0.704,0.90,0.761],
    'rate': [0.33,0.757,0.81,0.820],
}

def validate_regions(regions):
    if not isinstance(regions, dict) or set(regions) != set(FIELD_LABELS):
        raise ValueError('Exactly the required field keys must be present')
    for name, box in regions.items():
        if not isinstance(box, (list,tuple)) or len(box) != 4 or any(type(v) not in (float,int) for v in box):
            raise ValueError(f'Invalid region for {name}')
        x1,y1,x2,y2 = box
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise ValueError(f'Region out of range for {name}')
    return regions
