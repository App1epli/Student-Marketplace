# Security and Database Architecture

This document records the security controls and database decisions used by the Student Marketplace. It is intended for the architecture and security project contribution.

## 1. Application architecture

The project uses a server-rendered Flask application with PostgreSQL:

- `backend/app.py` contains HTTP routes, request validation, and application setup.
- `backend/auth.py` handles registration, login, logout, and the `login_required` access-control decorator.
- `backend/database.py` owns PostgreSQL connections, schema initialization, migrations, and the small SQL compatibility wrapper.
- `backend/payments.py` contains the purchase transaction and demo-payment checks.
- `backend/messaging.py` contains authenticated student-to-student conversations.
- `frontend/templates/` contains Jinja templates; `frontend/static/` contains browser assets.

The frontend does not connect directly to PostgreSQL. Requests go through Flask, which validates input and executes database operations.

## 2. SQL injection prevention

Values from requests are passed separately from SQL statements using parameterized queries. `DatabaseConnection.execute()` converts the project's `?` placeholders to psycopg2 `%s` placeholders and passes the values as a separate `params` argument.

Safe pattern used by the application:

```python
row = conn.execute(
    "SELECT * FROM products WHERE product_id = ?",
    (product_id,),
).fetchone()
```

Do not build SQL by concatenating user input, for example:

```python
# Unsafe: do not use
query = "SELECT * FROM products WHERE product_name = '" + name + "'"
```

Parameterized queries keep user input as data rather than executable SQL. When a query needs a variable number of placeholders, the application builds only the placeholder marks and still passes all values separately (see `backend/cart.py`).

## 3. Database integrity decisions

The PostgreSQL schema enforces important rules even if an application route contains a bug:

- `PRIMARY KEY` identifies each student, product, category, and purchase.
- `FOREIGN KEY` keeps product sellers and buyers connected to existing students and products connected to existing categories.
- `UNIQUE` prevents duplicate student numbers/emails, duplicate purchases for one product, duplicate cart entries, and duplicate ratings by one student for one product.
- `CHECK` validates positive prices, allowed product conditions/statuses, rating values from 1 to 5, and valid payment values.
- Indexes support common catalog, seller, purchase-history, messaging, and cart lookups.

The schema and additive migrations are defined in `backend/database.py` and `backend/migrations/`. Migrations are tracked in `schema_migrations`, so an already-applied migration is not run again.

## 4. Purchase transaction and concurrency control

`backend/app.py` opens a database connection context for checkout. `DatabaseConnection.__exit__()` commits when the operation succeeds and rolls back when an exception occurs. Therefore, the purchase row and product status change belong to the same database transaction.

`backend/payments.py` performs the following checks and operations:

1. Validate product, buyer, payment method, and payment reference.
2. Lock the saved demo-card row with `SELECT ... FOR UPDATE` and verify that it belongs to the selected buyer and browser wallet.
3. Serialize reuse of a payment reference with a PostgreSQL transaction-level advisory lock.
4. Lock the product row with `SELECT ... FOR UPDATE`.
5. Verify that the product is still `Available`, the buyer exists, and the buyer is not the seller.
6. Insert the purchase and its payment/commission details.
7. Change the product status from `Available` to `Sold` and verify that exactly one row changed.

If an error occurs before commit, the connection context rolls back the transaction. The unique constraint on `purchases.product_id` is an additional database-level safeguard against duplicate purchases.

The listing withdrawal/restore route in `backend/app.py` also locks the product row with `FOR UPDATE`. This makes a status change coordinate with the purchase operation, which locks the same row.

## 5. Authentication and access control

- Passwords are stored as Werkzeug password hashes, not as plaintext (`backend/auth.py`).
- Protected routes use `@login_required`.
- Seller-only listing changes compare the listing's `seller_id` with the logged-in student's ID.
- Seller reviews verify that the logged-in student is the buyer recorded in the purchase.
- Product ratings are unique per `(product_id, student_id)` and an update replaces that student's previous rating.
- Messaging routes require login and verify that the current student is the buyer or seller in the conversation.

Registration does not let a visitor claim an existing student record merely by entering its email. That case is rejected because the application does not yet have an independent student-ownership verification process.

## 6. Request, session, and upload protections

- Flask-WTF CSRF protection is enabled for state-changing form and JSON requests.
- Session cookies use `HttpOnly` and `SameSite=Lax`; the secure flag is enabled on Vercel.
- Flask uses an explicit environment `SECRET_KEY` when configured. Otherwise, the custom session interface creates and reuses a random key stored in PostgreSQL.
- Uploads are limited by request size, file count, individual file size, accepted image formats, and pixel count. Images are decoded and re-encoded as JPEG; original EXIF metadata is not retained (`backend/media.py`).
- Response headers include `X-Content-Type-Options: nosniff`.

## 7. Important demo limitation and future decision

The current checkout is explicitly a classroom demo: the buyer is selected in the checkout form and no real payment is processed. It must not be presented as production-grade identity or payment authorization. Before real deployment, checkout must derive the buyer ID from the authenticated session, payment must use a trusted payment provider, and authorization/rate-limiting/monitoring policies must be reviewed for the production threat model.

## 8. Verification

Run the existing automated checks from the repository root:

```powershell
python -m unittest discover -s tests -v
python scripts/build_static.py
```

The test suite includes CSRF checks, registration/login checks, ownership checks, purchase validation, payment replay handling, and a concurrent-purchase test that verifies only one competing purchase succeeds. Database integration tests require a separate `TEST_DATABASE_URL` test database.
