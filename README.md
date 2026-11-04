# Student Marketplace

A student-to-student marketplace with an English web interface and a PostgreSQL database. Students can browse, search, and filter listings, publish items, record purchases, and review purchase history.

## Team

| Student | ID | Project responsibility |
|---|---|---|
| Tynyshtyk Alis | `24B032081` | Systems analysis and requirements; main actions and tables |
| Medetkhan Aruzhan | `24B070509` | Application development; primary keys and data rules |
| Alkhan Yerdaulet | `24B031631` | Testing and integration; foreign keys and relationships |
| Tanirberdi Daulet | `24B032053` | Data and database; ERD and repeated data |
| Sembayev Zharas | `24B032016` | Architecture and security; SQL, decisions, and transactions |

## Requirements

- Python 3.9 or later
- PostgreSQL 14+ installed and running
- Docker Desktop is optional

## Run without Docker

Install PostgreSQL for Windows and start its PostgreSQL service. In pgAdmin, connect as the PostgreSQL administrator, open the Query Tool on the `postgres` database, and create the app role and database:

```sql
CREATE ROLE marketplace WITH LOGIN PASSWORD 'marketplace';
CREATE DATABASE student_marketplace OWNER marketplace;
```

In PowerShell, from the project root:

```powershell
Copy-Item .env.example .env
python -m pip install -r requirements.txt
python app.py --init-db
python app.py
```

Open <http://127.0.0.1:8000>. The app creates the four tables and loads sample data on first launch: five students, four categories, 26 listings (including 20 added listings), and one example purchase. On an existing project database, it adds any missing sample listings without duplicating them. `--init-db` is optional; it prints table record counts. Stop the app with `Ctrl+C`.

On Windows, `run_app.bat` installs the Python dependency and starts the app. It expects the local PostgreSQL service to be running and `.env` to contain the right connection string. The default `.env.example` values match the SQL role and database shown above.

For a different PostgreSQL user, password, host, or database, edit `DATABASE_URL` in `.env`. Example: `postgresql://marketplace:your-password@localhost:5432/student_marketplace`.

## Optional Docker setup

If Docker Desktop is installed, Compose can start a PostgreSQL instance for the project instead of installing PostgreSQL directly:

```powershell
Copy-Item .env.example .env
python -m pip install -r requirements.txt
docker compose up -d --wait db
python app.py
```

Stop the container with `docker compose down`; its data remains in the named volume.

`app.py` initializes tables and sample records on first run. Existing tables and data are retained on later launches. `.env` is excluded from Git; never commit real database passwords.

## Features

- Browse listings, with search by item, description, category, or seller.
- Filter by category and listing status.
- Publish listings with required-field and price validation.
- Record purchases in an atomic database transaction. PostgreSQL locks a listing during purchase to prevent concurrent duplicate sales and self-purchases.
- View purchase history.
- Responsive English interface for desktop and mobile.
- PostgreSQL primary keys, foreign keys, uniqueness rules, and check constraints.

## Project layout

```text
.
├── app.py
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── run_app.bat
├── README.md
└── deliverables/
    ├── Student_Marketplace_Task09.sql
    ├── StudentMarketplace_Team_StudentMarketplace_Task09.docx
    └── StudentMarketplace_Full_Project.zip
```

## Assignment SQL

`deliverables/Student_Marketplace_Task09.sql` is the standalone PostgreSQL assignment script. Run it in a new, empty practice database with pgAdmin or `psql`. The web app connects to PostgreSQL directly and initializes the same marketplace tables automatically; you do not need to run the assignment script for the app.
