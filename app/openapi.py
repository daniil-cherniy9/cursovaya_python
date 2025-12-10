# app/openapi.py
from fastapi.openapi.utils import get_openapi
from app.main import app


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Добавляем правильную security схему
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Введите: Bearer <ваш_токен>"
        }
    }

    # Для всех защищенных эндпоинтов добавляем security
    protected_paths = [
        "/users/me", "/candidates/", "/candidates/{candidate_id}",
        "/vacancies/", "/vacancies/{vacancy_id}"
    ]

    for path, methods in openapi_schema["paths"].items():
        for method in methods.values():
            if any(p in path for p in protected_paths):
                method["security"] = [{"BearerAuth": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
