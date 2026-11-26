"""Language selection, localization coverage and user-content regression checks."""
import re
import unittest
from unittest.mock import patch

from flask import render_template
from jinja2 import nodes

from backend import app as web, i18n
from backend.moderation import REPORT_REASONS, REPORT_STATUSES
from tests.test_app import post_form


class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.client = web.app.test_client()

    def test_switch_languages_and_persist_across_navigation_and_logout(self):
        self.assertIn('<html lang="en">', self.client.get('/register').text)
        for code, heading in [('kk', 'Аккаунт ашу'), ('ru', 'Создать аккаунт'), ('en', 'Create account')]:
            with self.subTest(code=code):
                response = post_form(self.client, '/language', {'language': code, 'next': '/register'})
                self.assertEqual(response.status_code, 303)
                cookie = self.client.get_cookie('language')
                self.assertEqual(cookie.value, code)
                self.assertTrue(cookie.http_only)
                self.assertEqual(cookie.same_site, 'Lax')
                html = self.client.get(response.location).text
                self.assertIn(f'<html lang="{code}">', html)
                self.assertIn(f'<h2>{heading}</h2>', html)
                post_form(self.client, '/logout')
                self.assertIn(f'<html lang="{code}">', self.client.get('/login').text)

    def test_preserves_filters_and_fragment_with_safe_redirect(self):
        target = '/?category=2&status=All&q=book#sell'
        response = post_form(self.client, '/language', {'language': 'ru', 'next': target})
        self.assertEqual(response.location, target)
        for unsafe in ['https://example.com', '//example.com', '/\\example.com', 'javascript:alert(1)', '//[', '/\r\nLocation: https://example.com']:
            with self.subTest(target=unsafe):
                response = post_form(self.client, '/language', {'language': 'kk', 'next': unsafe})
                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.location, '/')

    def test_invalid_language_and_missing_csrf_do_not_change_preference(self):
        self.client.set_cookie('language', 'ru')
        self.assertEqual(self.client.post('/language', data={'language': 'kk'}).status_code, 400)
        for invalid in ['kz', 'fr', '', '../ru']:
            self.assertEqual(post_form(self.client, '/language', {'language': invalid}).status_code, 400)
            self.assertEqual(self.client.get_cookie('language').value, 'ru')
        self.client.set_cookie('language', 'unknown')
        self.assertIn('<html lang="en">', self.client.get('/register').text)

    def test_validation_and_not_found_are_localized(self):
        for code, error, missing in [('ru', 'Введите полное имя.', 'Страница не найдена'),
                                     ('kk', 'Толық аты-жөніңізді енгізіңіз.', 'Бет табылмады')]:
            with self.subTest(code=code):
                self.client.set_cookie('language', code)
                response = post_form(self.client, '/register', {'full_name': ''})
                self.assertEqual(response.status_code, 400)
                self.assertIn(error, response.text)
                response = self.client.get('/missing')
                self.assertEqual(response.status_code, 404)
                self.assertIn(missing, response.text)

    def test_russian_count_forms(self):
        with web.app.test_request_context('/', headers={'Cookie': 'language=ru'}):
            for count, noun in [(0, 'объявлений'), (1, 'объявление'), (2, 'объявления'),
                                (5, 'объявлений'), (11, 'объявлений'), (21, 'объявление'),
                                (22, 'объявления'), (25, 'объявлений'), (112, 'объявлений')]:
                self.assertEqual(i18n.count_label('listing', count), f'{count} {noun}')

    def test_all_template_and_client_messages_have_translations(self):
        keys = set(i18n.CLIENT_MESSAGES)
        for name in web.app.jinja_env.list_templates():
            tree = web.app.jinja_env.parse(web.app.jinja_loader.get_source(web.app.jinja_env, name)[0])
            for call in tree.find_all(nodes.Call):
                if isinstance(call.node, nodes.Name) and call.node.name == '_' and call.args:
                    argument = call.args[0]
                    branches = [argument.expr1, argument.expr2] if isinstance(argument, nodes.CondExpr) else [argument]
                    keys.update(branch.value for branch in branches if isinstance(branch, nodes.Const))
        keys.update(web.CONDITIONS + web.STATUSES + REPORT_REASONS + REPORT_STATUSES)
        for code, catalog in i18n.CATALOGS.items():
            self.assertFalse(keys - catalog.keys(), f'Missing {code} messages: {keys - catalog.keys()}')
            self.assertEqual(set(catalog), set(i18n.CATALOGS['ru']))
            for source, translation in catalog.items():
                self.assertEqual(set(re.findall(r'\{\w+\}', source)), set(re.findall(r'\{\w+\}', translation)), source)

    def test_item_content_is_not_translated_and_remains_escaped(self):
        product = dict(product_id=1, seller_id=2, product_name='New', category_name='Electronics',
                       status='Available', item_condition='Good', price=2500,
                       description='<script>alert(1)</script>', seller='Seller')
        with web.app.test_request_context('/items/1', headers={'Cookie': 'language=ru'}):
            # Match the real endpoint without querying the database.
            with patch.object(web.auth, 'current_student', return_value=None):
                html = render_template('item.html', title=product['product_name'], product=product,
                                       product_rating=(None, 0), my_stars=None, photos=[], rating=(None, 0), reviews=[])
        self.assertIn('<title>New | Студенческий маркетплейс</title>', html)
        self.assertIn('<h1>New</h1>', html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertIn('Электроника', html)
        self.assertIn('В продаже', html)
        self.assertIn('Хорошее', html)

    def test_catalog_values_remain_compatible_with_backend(self):
        with web.app.test_request_context('/', headers={'Cookie': 'language=kk'}):
            with patch.object(web.auth, 'current_student', return_value=None):
                html = render_template('catalog.html', title='Marketplace catalog', mine=False,
                                       rows=[], categories=[{'category_id': 1, 'category_name': 'Electronics'}],
                                       counts={}, statuses=web.STATUSES, conditions=web.CONDITIONS,
                                       status='Available', category='', search='')
        self.assertIn('value="Available" selected>Сатылымда</option>', html)
        self.assertIn('category=1', html)
        self.assertIn('Электроника</a>', html)
        self.assertNotIn('id="sell"', html)
        with web.app.test_request_context('/sell', headers={'Cookie': 'language=kk'}):
            with patch.object(web.auth, 'current_student', return_value=None):
                form_html = render_template('listing_form.html',
                    current_user={'student_id': 1, 'full_name': 'Student'},
                    categories=[{'category_id': 1, 'category_name': 'Electronics'}],
                    conditions=web.CONDITIONS, commission_rate=0.03)
        self.assertIn('value="Good">Жақсы</option>', form_html)
        self.assertIn('value="1">Электроника</option>', form_html)
        self.assertIn('action="/listing"', form_html)
        self.assertIn('0 хабарландыру', html)


if __name__ == '__main__':
    unittest.main()
