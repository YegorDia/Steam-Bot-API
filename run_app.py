from wsgi_app.app import app, celery

if __name__ == "__main__":
    app.run(port=8001)