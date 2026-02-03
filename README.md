
1) **Create virtual env**
```
python -m venv venv
venv\Scripts\activate
```

2) **Install dependencies**
```
pip install -r requirements.txt
```
3) **Migrate**
```
python manage.py makemigrations
python manage.py migrate
```

4) **Create superuser**
```
python manage.py createsuperuser
```

5) **Run server**
- Development (HTTP):
```
python manage.py runserver
```
- WebSockets (Channels / Daphne):
```
daphne -b 127.0.0.1 -p 8000 moveline.asgi:application
```
