# Student Marketplace

Учебный маркетплейс на Flask и PostgreSQL: каталог, поиск, фильтры, публикация товаров и история покупок. Интерфейс остаётся на английском.

## Демо-оплата

Кнопка **Buy this item** открывает checkout без логина: выбор учебного покупателя, демо-карта, демо-перевод или наличные при встрече. Есть успешная оплата, тестовый отказ с повторной попыткой, отмена, демо-чек с печатью и статус в истории. Реальные деньги не списываются, вводить реквизиты карты не нужно.

Для существующей базы перед деплоем новой версии выполните `python -m backend.app --migrate-db`. Команда добавляет поля оплаты и сохраняет старые данные. Для пустой базы достаточно обычного `--init-db`.

Подробности, сценарий демонстрации и точка подключения будущего логина: [docs/PAYMENTS.md](docs/PAYMENTS.md).

## Структура

```text
frontend/
  templates/        # HTML-шаблоны Jinja: каталог, форма, история, ошибки
  static/styles.css # Стили интерфейса
backend/
  app.py            # Flask, маршруты и проверка данных
  database.py       # PostgreSQL, схема и демоданные
scripts/build_static.py # Копирует стили в public/static для CDN Vercel
app.py              # Совместимый запуск: python app.py
pyproject.toml      # Зависимости Python и точка входа backend.app:app
uv.lock             # Зафиксированные версии для сборки Vercel
vercel.json         # Настройки Flask и сборки
requirements.txt
.env.example
```

Фронтенд и бэкенд разделены по папкам, но разворачиваются **одним проектом Vercel из корня репозитория**. HTML формируется сервером; отдельная Node.js-сборка и CORS не нужны. Существующие URL `/`, `/sales`, `/listing` и `/purchase` сохранены. `/api/health` проверяет подключение к базе и наличие таблицы `students`.

## Деплой на Vercel и облачная база Neon

1. Создайте проект PostgreSQL в [Neon](https://console.neon.tech/). В окне **Connect** скопируйте строку подключения с включённым **Connection pooling**. Она обычно содержит `-pooler` в имени хоста. Сохраните параметры SSL из выданной строки (`sslmode=require` и остальные, если они есть).
2. Для создания таблиц скопируйте `.env.example` в `.env` в корне проекта и замените `DATABASE_URL` на облачную строку. При желании задайте `DATABASE_URL_UNPOOLED` прямой строкой Neon: команда инициализации предпочитает её, приложение использует `DATABASE_URL`. Не публикуйте `.env` в Git и не передавайте пароль во фронтенд.
3. Выполните локально из корня:

   ```powershell
   python -m pip install -r requirements.txt
   python -m backend.app --init-db
   ```

   Команда создаёт четыре таблицы, пять учебных аккаунтов, четыре категории, 26 объявлений и пример покупки. Повторный запуск добавляет отсутствующие демотовары и обновляет имена учебных аккаунтов, сохраняя существующие покупки. Инициализация выполняется явно, а не при запросах или сборке Vercel. Используйте отдельную базу для этого учебного приложения.
4. Отправьте изменения репозитория в GitHub и импортируйте/откройте проект в Vercel. Настройки:

   | Поле | Значение |
   |---|---|
   | Root Directory | Корень репозитория (`.`), не `frontend` и не `backend` |
   | Framework Preset | Flask |
   | Build Command | Из `vercel.json`: `python scripts/build_static.py` |
   | Output Directory | Без пользовательского переопределения |
   | Install Command | По умолчанию, зависимости из `pyproject.toml` и `uv.lock` |
   | Python | 3.13, задан в `.python-version` |

5. В **Settings → Environment Variables** добавьте `DATABASE_URL` со строкой Neon для **Production**. Для **Preview** лучше использовать отдельную ветку/базу Neon, также предварительно инициализированную. `.env` с компьютера на Vercel не загружается.
6. Запустите **Redeploy** после сохранения переменных. Проверьте `/api/health`: ожидается `{"status":"ok","database":"ok"}`. Затем откройте каталог, создайте объявление, купите его от другого учебного аккаунта и проверьте `/sales`.

Стили при сборке копируются из `frontend/static` в `public/static`, откуда их раздаёт CDN Vercel. Генерируемая папка `public` не хранится в Git. Шаблоны из `frontend/templates` включаются в Python-функцию.

### Почему возникала ошибка PYTHON_ENTRYPOINT_NOT_FOUND

Раньше `app.py` запускал `ThreadingHTTPServer` только через `main()` и не экспортировал WSGI-приложение. Теперь `backend/app.py` экспортирует `app = Flask(...)`, а `pyproject.toml` явно указывает `backend.app:app`.

Не используйте предложенную в старом логе точку входа `apply_messaging:app`: там `app` — путь к файлу, а не веб-сервер. `apply_messaging.py` и `messaging.py` сохранены как старые необязательные материалы; они не подключены к Flask, исключены из Vercel и не должны запускаться для этой структуры. Мессенджер не был включён в исходном приложении.

Если сборка продолжает показывать старую ошибку, проверьте выбранную ветку/коммит, корневую папку и уберите старое переопределение точки входа. При ответе 503 проверьте `DATABASE_URL`, доступность базы и выполненную инициализацию. Создание Neon-проекта и фактический деплой требуют доступа к вашим аккаунтам и не выполняются самой конфигурацией.

Документация: [Python entrypoints](https://vercel.com/docs/functions/runtimes/python#python-entrypoints), [Flask на Vercel](https://vercel.com/docs/frameworks/backend/flask), [подключение Neon](https://neon.com/docs/connect/connect-from-any-app).

### Ошибка ModuleNotFoundError: No module named 'flask'

Vercel отдаёт приоритет `pyproject.toml` при установке Python-зависимостей. В нём должны быть объявлены Flask и psycopg2-binary в `[project].dependencies`; одного `requirements.txt` рядом недостаточно. `requirements.txt` сохраняется для локальной установки через pip, его список должен совпадать с `pyproject.toml`.

`uv.lock` фиксирует версии для Vercel. После изменения зависимостей обновите его командой `uv lock` и включите в коммит.

После изменения зависимостей отправьте новый коммит в GitHub и дождитесь деплоя именно этого коммита. При ручном Redeploy выберите новый деплой и отключите **Use existing Build Cache**. Повторный деплой старого коммита не применит исправления файлов.

## Локальный запуск

Требования: Python 3.13 и PostgreSQL 14+ (локальный, Docker или облачный).

```powershell
Copy-Item .env.example .env
python -m pip install -r requirements.txt
# При использовании Docker вместо установленного PostgreSQL:
# docker compose up -d --wait db
python -m backend.app --init-db
python -m backend.app
```

Откройте http://127.0.0.1:8000. Сохранены команды `python app.py --init-db`, `python app.py` и `run_app.bat`. Для своего PostgreSQL измените `DATABASE_URL` в `.env`. Для базы со стандартными локальными значениями из примера выполните от администратора PostgreSQL:

```sql
CREATE ROLE marketplace WITH LOGIN PASSWORD 'marketplace';
CREATE DATABASE student_marketplace OWNER marketplace;
```

Запуск сервера сам по себе больше не создаёт таблицы. Выполните `--init-db` перед первым запуском. Переменные окружения имеют приоритет над `.env`. Для другого адреса/порта задайте `HOST` / `PORT`. Остановка сервера: Ctrl+C. `docker compose down` сохраняет данные в именованном томе.

## Проверки

```powershell
python -m unittest discover -s tests -v
python scripts/build_static.py
```

Для интеграционных проверок задайте `TEST_DATABASE_URL` тестовой PostgreSQL-базой. Тесты создают отдельную случайную схему, проверяют создание таблиц, каталог, фильтрацию, публикацию, покупку и одновременные покупки, затем удаляют только свою схему. Без этой переменной интеграционные тесты пропускаются.

Приложение остаётся учебной демонстрацией: аккаунт выбирается в форме без авторизации. Для использования реальными пользователями потребуется аутентификация и проверка прав на действия.

## Учебные материалы

`deliverables/Student_Marketplace_Task09.sql` — самостоятельный SQL-скрипт задания для пустой учебной базы. Для запуска сайта выполняйте `--init-db`; импортировать этот файл дополнительно не нужно.

## Team

| Student | ID | Project responsibility |
|---|---|---|
| Tynyshtyk Alis | `24B032081` | Systems analysis and requirements; main actions and tables |
| Medetkhan Aruzhan | `24B070509` | Application development; primary keys and data rules |
| Alkhan Yerdaulet | `24B031631` | Testing and integration; foreign keys and relationships |
| Tanirberdi Daulet | `24B032053` | Data and database; ERD and repeated data |
| Sembayev Zharas | `24B032016` | Architecture and security; SQL, decisions, and transactions |
