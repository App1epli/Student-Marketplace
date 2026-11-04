# Student Marketplace

A student-to-student marketplace project with an English web interface, a populated SQLite database, and a PostgreSQL script for the classroom assignment.

## Team

| Student | ID | Project responsibility |
|---|---|---|
| Tynyshtyk Alis | `24B032081` | Systems analysis and requirements; main action and tables |
| Medetkhan Aruzhan | `24B070509` | Application development; primary keys and data rules |
| Alkhan Yerdaulet | `24B031631` | Testing and integration; foreign keys and relationships |
| Tanirberdi Daulet | `24B032053` | Data and database; ERD and repeated data |
| Sembayev Zharas | `24B032016` | Architecture and security; SQL, decisions, and transactions |

## Run the application

Python 3.9 or later is required. The application uses only the Python standard library; no packages need to be installed.

### Windows

1. Extract the project archive if needed.
2. Open the `StudentMarketplace_App` folder.
3. Double-click `run_app.bat`, or open PowerShell in that folder and run:

   ```powershell
   python app.py
   ```

4. Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.
5. Press `Ctrl+C` in the app window to stop the server.

On the first launch, the app creates `database/student_marketplace.db` and inserts the sample data. To initialize the database separately, run `python app.py --init-db`, then start the app with `python app.py`.

## Features

- Browse listings as product cards.
- Search by product name, description, category, or seller.
- Filter listings by category and status.
- Publish a listing with required-field and price validation.
- Purchase an available item with transaction protection against duplicate sales and self-purchases.
- View completed purchases.
- Responsive layout for desktop and mobile screens.

## Project files

```text
StudentMarketplace_App/
├── app.py                 # Web application and database setup
├── run_app.bat            # Windows launcher
├── README.md              # This guide
├── database/
│   └── student_marketplace.db
└── deliverables/
    ├── Student_Marketplace_Task09.sql
    ├── StudentMarketplace_Team_StudentMarketplace_Task09.docx
    └── StudentMarketplace_Full_Project.zip
```

The full project ZIP contains a copy of the application and deliverables. Do not include the ZIP inside itself when rebuilding the archive.

## PostgreSQL assignment

Run `deliverables/Student_Marketplace_Task09.sql` once in a new, empty PostgreSQL database using pgAdmin or `psql`. Check the created tables and SELECT output, then capture screenshots for the instructor.

The web app uses SQLite so it can run locally without a separate PostgreSQL server. Its SQLite database is the app's working database; it does not replace running the PostgreSQL assignment script.
