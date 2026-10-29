# Student Marketplace

A student-to-student marketplace project with a web app, populated SQLite database, PostgreSQL assignment script, and team report.

## Team

| Student | ID | Project responsibility |
|---|---|---|
| Tynyshtyk Alis | `24B032081` | Systems analysis and requirements; main action and tables |
| Medetkhan Aruzhan | `24B070509` | Application development; primary keys and data rules |
| Alkhan Yerdaulet | `24B031631` | Testing and integration; foreign keys and relationships |
| Tanirberdi Daulet | `24B032053` | Data and database; ERD and repeated data |
| Sembayev Zharas | `24B032016` | Architecture and security; SQL, decisions, and transactions |

## Run the app

Install Python 3.9 or later. No extra packages are required. From the repository root, run:

```powershell
python app.py
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000). Press `Ctrl+C` in the terminal to stop the server. On Windows, you can also double-click `run_app.bat`.

The first launch creates and populates `database/student_marketplace.db`. To initialize the database separately, run `python app.py --init-db` before starting the app.

## Features

- Browse listings as product cards.
- Search by product name, description, category, or seller.
- Filter by category and listing status.
- Publish a listing with required-field and price validation.
- Purchase an available item with transaction protection against duplicate sales and self-purchases.
- View completed purchases.
- Responsive English-language interface for desktop and mobile.

## Project files

```text
.
├── app.py
├── run_app.bat
├── README.md
├── database/
│   └── student_marketplace.db
└── deliverables/
    ├── Student_Marketplace_Task09.sql
    ├── StudentMarketplace_Team_StudentMarketplace_Task09.docx
    └── StudentMarketplace_Full_Project.zip
```

The downloadable archive is kept in `deliverables/` and is not included inside itself.

## PostgreSQL assignment

Run `deliverables/Student_Marketplace_Task09.sql` once in a new, empty PostgreSQL database with pgAdmin or `psql`. Check the created tables and SELECT output, then capture screenshots for the instructor.

The web app uses SQLite so it runs without a separate PostgreSQL server. The SQLite file is the app's working database; it does not replace running the PostgreSQL assignment script.
