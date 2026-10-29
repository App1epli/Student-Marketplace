# Student Marketplace

Учебный проект маркетплейса для студентов: локальное веб-приложение, база данных, PostgreSQL-скрипт и командный отчёт.

## Команда

| Имя | ID | Роль |
|---|---|---|
| Tynyshtyk Alis | `24B032081` | Анализ системы, требования, основные таблицы |
| Medetkhan Aruzhan | `24B070509` | Разработка, первичные ключи и правила данных |
| Alkhan Yerdaulet | `24B031631` | Тестирование, внешние ключи и связи |
| Tanirberdi Daulet | `24B032053` | База данных, ER-диаграмма и повторяющиеся данные |
| Sembayev Zharas | `24B032016` | Архитектура, SQL, безопасность и транзакции |

## Запуск приложения

Нужен Python 3.9 или новее. Дополнительные библиотеки устанавливать не требуется.

В Windows откройте PowerShell в папке репозитория и выполните:

```powershell
cd StudentMarketplace_App
python app.py
```

Затем откройте [http://127.0.0.1:8000](http://127.0.0.1:8000). Для остановки нажмите `Ctrl+C` в PowerShell. Можно также запустить `StudentMarketplace_App/run_app.bat` двойным щелчком.

При первом запуске приложение создаст и заполнит SQLite-базу `StudentMarketplace_App/database/student_marketplace.db`. Для ручной подготовки базы выполните `python app.py --init-db` из папки приложения.

## Структура

- `StudentMarketplace_App/app.py` — веб-приложение и логика базы данных.
- `StudentMarketplace_App/database/student_marketplace.db` — демонстрационная база SQLite.
- `StudentMarketplace_App/deliverables/Student_Marketplace_Task09.sql` — скрипт для PostgreSQL.
- `StudentMarketplace_App/deliverables/StudentMarketplace_Team_StudentMarketplace_Task09.docx` — отчёт команды.
- `StudentMarketplace_App/deliverables/StudentMarketplace_Full_Project.zip` — архив проекта.

Веб-приложение работает на SQLite для простого локального запуска. Скрипт PostgreSQL подготовлен для выполнения практической части задания в pgAdmin или `psql`.
