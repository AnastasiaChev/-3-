from flask import Flask, render_template, send_from_directory, request, abort
import os
import json
import datetime
import shutil

app = Flask(__name__)

# Путь к папке с книгами
BOOKS_DIR = os.path.join(os.getcwd(), 'books')

# Количество книг на странице
BOOKS_PER_PAGE = 6

# Путь к папке с обложками
COVERS_DIR = os.path.join(os.getcwd(), 'static', 'covers')

# Путь к папке с метаданными
METADATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'books.json')

# Путь к файлу со статистикой скачивания книг
DOWNLOADS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads.json')

# Путь к файлу логирования
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log.json')

# Разрешённые расширения для загрузки
ALLOWED_BOOK_EXTENSIONS = {'pdf'}
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 МБ

def allowed_book_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_BOOK_EXTENSIONS

def allowed_image_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def load_metadata():
    """Загружает метаданные из books.json при каждом вызове"""
    try:
        with open(METADATA_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    
def increment_download(filename):
    """Увеличивает счётчик скачиваний для файла"""
    # Загружаем текущую статистику
    if os.path.exists(DOWNLOADS_PATH):
        with open(DOWNLOADS_PATH, 'r', encoding='utf-8') as f:
            downloads = json.load(f)
    else:
        downloads = {}

    # Увеличиваем счётчик
    downloads[filename] = downloads.get(filename, 0) + 1

    # Сохраняем обратно
    with open(DOWNLOADS_PATH, 'w', encoding='utf-8') as f:
        json.dump(downloads, f, ensure_ascii=False, indent=4)

@app.route('/')

def index():
    # Получаем номер страницы из URL (по умолчанию 1)
    page = request.args.get('page', 1, type=int)
    
    # Получаем список файлов в папке books
    try:
        files = [f for f in os.listdir(BOOKS_DIR) if os.path.isfile(os.path.join(BOOKS_DIR, f))]
    except FileNotFoundError:
        files = []
    
    # Сортируем для стабильности
    files.sort()
    
    # Пагинация
    total_books = len(files)
    total_pages = (total_books + BOOKS_PER_PAGE - 1) // BOOKS_PER_PAGE  # ceil division
    start = (page - 1) * BOOKS_PER_PAGE
    end = start + BOOKS_PER_PAGE
    books_on_page = []
    for filename in files[start:end]:
        # Проверяем наличие обложки: .jpg, .png, .jpeg
        cover = None
        basename = filename.rsplit('.', 1)[0]  # отрезаем расширение файла
        for ext in ['.jpg', '.jpeg', '.png']:
            cover_filename = basename + ext
            cover_path = os.path.join(COVERS_DIR, cover_filename)
            if os.path.exists(cover_path):
                cover = cover_filename  # только имя файла, без пути
                break
        books_on_page.append({
            'filename': filename,
            'cover': cover,  # None, если нет обложки
            'metadata': load_metadata().get(filename, {})  # ← добавили! всегда словарь
        })
    
    # Генерируем список страниц для навигации (ограничим, чтобы не было 100 кнопок)
    pagination_range = range(max(1, page - 2), min(total_pages + 1, page + 3))

    return render_template(
        'index.html',
        books=books_on_page,
        page=page,
        total_pages=total_pages,
        pagination_range=pagination_range
    )

@app.route('/download/<path:filename>')
def download_file(filename):
    file_path = os.path.join(BOOKS_DIR, filename)
    if not os.path.exists(file_path):
        abort(404, description=f"Файл '{filename}' не найден в папке books/")

    # 💡 Увеличиваем счётчик ПЕРЕД отправкой файла
    increment_download(filename)
    log_action("download", f"Файл: {filename} был скачан пользователем")

    return send_from_directory(BOOKS_DIR, filename, as_attachment=True)

@app.route('/filters')
def filter_books():
    #Получаем параметры из URL
    page = request.args.get('page', 1, type=int)
    topic_filter = request.args.get('topic', None)

    # Получаем список файлов в папке books
    try:
        files = [f for f in os.listdir(BOOKS_DIR) if os.path.isfile(os.path.join(BOOKS_DIR, f))]
    except FileNotFoundError:
        files = []

    metadata_dict = load_metadata()
    # Применяем фильтр по теме, если указан
    if topic_filter and topic_filter != "all":
        files = [
            f for f in files
            
            if f in metadata_dict and metadata_dict[f].get('topic') == topic_filter
        ]
    
    # Сортируем для стабильности
    files.sort()

    # Пагинация
    total_books = len(files)
    total_pages = (total_books + BOOKS_PER_PAGE - 1) // BOOKS_PER_PAGE
    start = (page - 1) * BOOKS_PER_PAGE
    end = start + BOOKS_PER_PAGE

    books_on_page = []
    for filename in files[start:end]:
        cover = None
        basename = filename.rsplit('.', 1)[0]
        for ext in ['.jpg', '.jpeg', '.png']:
            cover_filename = basename + ext
            cover_path = os.path.join(COVERS_DIR, cover_filename)
            if os.path.exists(cover_path):
                cover = cover_filename
                break
        books_on_page.append({
            'filename': filename,
            'cover': cover,
            'metadata': metadata_dict.get(filename, {})
        })
    
    # Генерируем список тем для фильтра
    all_topics = set()
    metadata_dict = load_metadata()
    for meta in metadata_dict.values():
        if 'topic' in meta:
            all_topics.add(meta['topic'])

    # Генерируем пагинацию
    pagination_range = range(max(1, page - 2), min(total_pages + 1, page + 3))

    return render_template(
        'filters.html',  # ← используем НОВЫЙ шаблон
        books=books_on_page,
        page=page,
        total_pages=total_pages,
        pagination_range=pagination_range,
        topics=all_topics,
        current_topic=topic_filter
    )

@app.route('/admin/catalog')
def admin_catalog():
    
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('q', '').strip()

    try:
        files = os.listdir(BOOKS_DIR)
    except FileNotFoundError:
        files = []

    # Фильтрация по поиску
    if search_query:
        files = [f for f in files if search_query.lower() in f.lower()]

    files = [f for f in files if os.path.isfile(os.path.join(BOOKS_DIR, f))]

    # Сортировка по дате обновления
    files.sort(key=lambda x: os.path.getmtime(os.path.join(BOOKS_DIR, x)), reverse=True)

    # Пагинация
    ITEMS_PER_PAGE = 5
    total_items = len(files)
    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    files_on_page = files[start:end]

    # Формируем данные для шаблона
    catalog = []
    for filename in files_on_page:
        filepath = os.path.join(BOOKS_DIR, filename)
        stat = os.stat(filepath)
        size = stat.st_size
        mtime = datetime.datetime.fromtimestamp(stat.st_mtime)

        cover_exists = False
        basename = filename.rsplit('.', 1)[0]
        for ext in ['.jpg', '.jpeg', '.png']:
            cover_path = os.path.join(COVERS_DIR, basename + ext)
            if os.path.exists(cover_path):
                cover_exists = True
                break

        metadata = load_metadata().get(filename, {})

        catalog.append({
            'filename': filename,
            'size': size,
            'size_mb': round(size / (1024 * 1024), 2),
            'modified': mtime.strftime('%Y-%m-%d %H:%M'),
            'cover_exists': cover_exists,
            'has_metadata': bool(metadata),
            'metadata': metadata
        })

    # Диапазон страниц для навигации
    pagination_range = range(max(1, page - 2), min(total_pages + 1, page + 3))

    return render_template(
        'admin_catalog.html',
        catalog=catalog,
        page=page,
        total_pages=total_pages,
        pagination_range=pagination_range,
        search_query=search_query  # передаём текущий запрос в шаблон
    )

@app.route('/admin/manage', methods=['GET', 'POST'])
def admin_manage():
    message = None

    if request.method == 'POST':
        # --- Удаление файла (остаётся как было) ---
        if 'delete' in request.form:
            filename = request.form.get('filename')
            if filename:
                # Удаляем книгу
                book_path = os.path.join(BOOKS_DIR, filename)
                if os.path.exists(book_path):
                    os.remove(book_path)

                # Удаляем обложку
                basename = filename.rsplit('.', 1)[0]
                for ext in ['.jpg', '.jpeg', '.png']:
                    cover_path = os.path.join(COVERS_DIR, basename + ext)
                    if os.path.exists(cover_path):
                        os.remove(cover_path)

                message = f"Файл '{filename}' и связанные данные удалены."
                log_action("delete", f"Файл: {filename} был удален")
                

        # --- Добавление новой книги с метаданными ---
        elif 'book_file' in request.files:
            book_file = request.files['book_file']
            cover_file = request.files.get('cover_file')
            title = request.form.get('title', '').strip()
            author = request.form.get('author', '').strip()
            topic = request.form.get('topic', '').strip()

            # Проверка книги
            if not book_file or book_file.filename == '':
                message = "Не выбран файл книги."
            elif not allowed_book_file(book_file.filename):
                message = "Недопустимый формат книги. Разрешены: " + ", ".join(ALLOWED_BOOK_EXTENSIONS)
            elif len(book_file.read()) > MAX_FILE_SIZE:
                message = "Файл книги слишком большой (макс. 50 МБ)."
            else:
                book_file.seek(0)
                book_filename = book_file.filename
                book_path = os.path.join(BOOKS_DIR, book_filename)

                # Избегаем дубликатов имён
                counter = 1
                name, ext = os.path.splitext(book_filename)
                while os.path.exists(book_path):
                    book_filename = f"{name} ({counter}){ext}"
                    book_path = os.path.join(BOOKS_DIR, book_filename)
                    counter += 1

                # Сохраняем книгу
                book_file.save(book_path)

                # Обработка обложки
                cover_filename = None
                if cover_file and cover_file.filename != '':
                    if not allowed_image_file(cover_file.filename):
                        message = "Недопустимый формат обложки. Разрешены: jpg, jpeg, png."
                    elif len(cover_file.read()) > MAX_FILE_SIZE:
                        message = "Обложка слишком большая (макс. 50 МБ)."
                    else:
                        cover_file.seek(0)
                        # Имя обложки = имя книги + расширение обложки
                        cover_ext = cover_file.filename.rsplit('.', 1)[1]
                        cover_filename = f"{name}.{cover_ext}"
                        cover_path = os.path.join(COVERS_DIR, cover_filename)
                        cover_file.save(cover_path)
                # Если обложки нет — оставляем None

                # Подготавливаем метаданные
                metadata_entry = {
                    "title": title or name,
                    "author": author or "Не указан",
                    "topic": topic or "без темы",
                    "cover": cover_filename  # может быть None
                }

                # Обновляем books.json
                if os.path.exists(METADATA_PATH):
                    with open(METADATA_PATH, 'r', encoding='utf-8') as f:
                        all_metadata = json.load(f)
                else:
                    all_metadata = {}

                all_metadata[book_filename] = metadata_entry

                with open(METADATA_PATH, 'w', encoding='utf-8') as f:
                    json.dump(all_metadata, f, ensure_ascii=False, indent=4)

                message = f"Книга '{book_filename}' добавлена."
                log_action("add", f"Книга: {book_filename} была добавлена администратором")

    # Получаем список файлов для отображения
    try:
        files = [f for f in os.listdir(BOOKS_DIR) if os.path.isfile(os.path.join(BOOKS_DIR, f))]
    except FileNotFoundError:
        files = []
    files.sort()

    return render_template('admin_manage.html', files=files, message=message)

@app.route('/admin/rating')
def admin_rating():
    # Загружаем статистику скачиваний
    if os.path.exists(DOWNLOADS_PATH):
        with open(DOWNLOADS_PATH, 'r', encoding='utf-8') as f:
            downloads = json.load(f)
    else:
        downloads = {}

    # Загружаем метаданные для отображения названий
    metadata = load_metadata()  # ← используем нашу функцию

    # Формируем список: (filename, count, title, author)
    rating = []
    for filename, count in downloads.items():
        meta = metadata.get(filename, {})
        title = meta.get('title') or filename.rsplit('.', 1)[0]
        author = meta.get('author', '')
        rating.append({
            'filename': filename,
            'count': count,
            'title': title,
            'author': author
        })

    # Сортируем по убыванию количества скачиваний
    rating.sort(key=lambda x: x['count'], reverse=True)

    return render_template('admin_rating.html', rating=rating)

@app.route('/admin/log')
def admin_log():
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, 'r', encoding='utf-8') as f:
            log_data = json.load(f)
    else:
        log_data = []

    # Опционально: ограничим количество отображаемых записей
    log_data = log_data[:100]  # последние 100 действий

    return render_template('admin_log.html', log=log_data)

def log_action(action: str, details: str = ""):
    # Текущие дата и время
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Новая запись
    log_entry = {
        "timestamp": timestamp,
        "action": action,
        "details": details
    }

    # Загружаем существующий лог или создаём пустой
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, 'r', encoding='utf-8') as f:
            log_data = json.load(f)
    else:
        log_data = []

    log_data.insert(0, log_entry)

    # Сохраняем (ограничим размер, чтобы не рос бесконечно)
    MAX_LOG_ENTRIES = 500
    if len(log_data) > MAX_LOG_ENTRIES:
        log_data = log_data[:MAX_LOG_ENTRIES]

    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, ensure_ascii=False, indent=4)

if __name__ == '__main__':
    app.run(debug=True)


