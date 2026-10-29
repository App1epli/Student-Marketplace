# Student Marketplace

A student-to-student marketplace project with a local web app, SQLite database, PostgreSQL assignment script, and team report.

## Team

| Student | ID | Project responsibility |
|---|---|---|
| Tynyshtyk Alis | `24B032081` | Systems analysis and requirements; main action and tables |
| Medetkhan Aruzhan | `24B070509` | Application development; primary keys and data rules |
| Alkhan Yerdaulet | `24B031631` | Testing and integration; foreign keys and relationships |
| Tanirberdi Daulet | `24B032053` | Data and database; ERD and repeated data |
| Sembayev Zharas | `24B032016` | Architecture and security; SQL, decisions, and transactions |

## Run the app

Install Python 3.9 or later. No additional packages are required. In Windows PowerShell, run:

```powershell
cd StudentMarketplace_App
python app.py
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000). Press `Ctrl+C` in PowerShell to stop the server. You can also double-click `StudentMarketplace_App/run_app.bat`.

The first launch creates and populates `StudentMarketplace_App/database/student_marketplace.db`. To set up the database separately, run `python app.py --init-db` from the app folder.

## Project contents

- `StudentMarketplace_App/app.py` - English web interface and app logic.
- `StudentMarketplace_App/database/student_marketplace.db` - populated SQLite demo database.
- `StudentMarketplace_App/deliverables/Student_Marketplace_Task09.sql` - PostgreSQL assignment script.
- `StudentMarketplace_App/deliverables/StudentMarketplace_Team_StudentMarketplace_Task09.docx` - team report.
- `StudentMarketplace_App/deliverables/StudentMarketplace_Full_Project.zip` - complete project archive.

The web application uses SQLite for a simple local setup. Run the PostgreSQL script separately in pgAdmin or `psql` to complete the database assignment.
