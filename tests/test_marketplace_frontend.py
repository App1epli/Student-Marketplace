"""Contracts between the photo-first UI and the merged Flask routes."""
import unittest
from uuid import uuid4
from unittest.mock import patch

from flask import render_template

from backend import app as web, database
from backend.catalog_images import sample_image


class MarketplaceFrontendTests(unittest.TestCase):
    def test_every_seeded_product_has_a_local_sample_photo(self):
        for product in database.PRODUCTS:
            self.assertIsNotNone(sample_image(product[2]))
        for product in database.EXTRA_PRODUCTS:
            self.assertIsNotNone(sample_image(product[2], product[1]))

    def test_uploaded_image_is_used_without_sample_replacement(self):
        photo_id = str(uuid4())
        row = dict(product_id=1, seller_id=2, product_name='Scientific Calculator',
                   category_name='Electronics', description='User description', price=2500,
                   item_condition='Good', status='Available', photo_id=photo_id,
                   liked=False, booked_by=None, product_rating=None, product_rating_count=0,
                   my_stars=None, rating=None)
        with web.app.test_request_context('/'):
            with patch.object(web.auth, 'current_student', return_value=None):
                rendered = render_template('catalog.html', title='Marketplace catalog', rows=[row],
                    categories=[], status='Available', statuses=web.STATUSES, category='', search='',
                    mine=False, liked=False, booked=False, hot_offers=[], cart_product_ids=set())
        self.assertIn(f'src="/photos/{photo_id}"', rendered)
        self.assertNotIn('/static/images/products/calculator.jpg', rendered)
        self.assertNotIn('class="stats"', rendered)
        self.assertNotIn('class="campus-workspace"', rendered)
        self.assertNotIn('class="live-pill"', rendered)
        self.assertNotIn('id="sell"', rendered)
        self.assertIn('href="/sell"', rendered)

    def test_category_links_keep_search_scope_and_status(self):
        with web.app.test_request_context('/?q=book&scope=liked&status=All&category=2'):
            with patch.object(web.auth, 'current_student', return_value=None):
                rendered = render_template('catalog.html', title='Liked items', rows=[],
                    categories=[dict(category_id=1, category_name='Electronics')], status='All',
                    statuses=web.STATUSES, category='2', search='book', mine=False,
                    liked=True, booked=False, hot_offers=[], cart_product_ids=set())
        self.assertIn('q=book&amp;status=All&amp;scope=liked&amp;category=1', rendered)
        self.assertIn('name="category" value="2"', rendered)
        self.assertIn('name="scope" value="liked"', rendered)
