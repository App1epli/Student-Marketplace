"""Presentation-only sample photos; uploaded photo rows always take precedence.

These mappings never write to product_photos or modify a listing's content.
"""
from pathlib import Path

SAMPLE_KINDS = {
    'scientific calculator': 'calculator', 'scientific calculator fx-991': 'calculator',
    'java programming textbook': 'textbooks', 'database systems textbook': 'textbooks',
    'computer networks handbook': 'textbooks', 'academic english workbook': 'notebooks',
    'graph paper notebook set': 'notebooks', 'discrete mathematics notes': 'notes',
    'wireless mouse': 'mouse', 'desk lamp': 'lamp', 'led study light': 'lamp',
    'campus backpack': 'backpack', 'sports backpack': 'backpack', 'campus tote bag': 'tote',
    'laptop stand': 'laptop-stand', 'usb-c hub': 'usb-hub', 'bluetooth headphones': 'headphones',
    'mechanical keyboard': 'keyboard', 'portable ssd 500gb': 'ssd', 'desk organiser': 'organizer',
    'electric kettle 1.5l': 'kettle', 'storage box set': 'storage-box',
    'foldable laundry basket': 'laundry-basket', 'laptop sleeve 15-inch': 'laptop-sleeve',
    'winter scarf': 'scarf', 'rain jacket': 'rain-jacket',
}
CATEGORY_DEFAULTS = {'Electronics': 'headphones', 'Books and Study': 'textbooks',
                     'Clothing and Bags': 'tote', 'Dorm Essentials': 'lamp'}
IMAGE_ROOT = Path(__file__).resolve().parents[1] / 'frontend/static/images/products'


def sample_image(product_name, category_name=''):
    key = SAMPLE_KINDS.get(str(product_name).strip().lower(), CATEGORY_DEFAULTS.get(category_name))
    return f'/static/images/products/{key}.jpg' if key and (IMAGE_ROOT / f'{key}.jpg').is_file() else None
