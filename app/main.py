from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import timedelta
import os
import uvicorn
import jwt

from dotenv import load_dotenv
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

from app.database import engine, Base, get_db
from app.models import User, Candidate, Vacancy
from app.schemas import (
    UserCreate, UserOut, UserLogin, Token,
    CandidateCreate, CandidateUpdate, CandidateOut,
    VacancyCreate, VacancyUpdate, VacancyOut
)
from app.auth import create_access_token, get_password_hash, verify_password
from app.schemas import TokenData
import app.models

security = HTTPBearer(auto_error=False)

app = FastAPI(
    title="HR Automation API",
    description="API для автоматизации HR процессов: кандидаты, вакансии, онбординг",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters={"defaultModelsExpandDepth": -1}
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Создание таблиц при запуске
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Верификация токена
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise credentials_exception

    # Получение пользователя из БД
    result = await db.execute(
        select(User).where(User.username == username)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return user

async def get_current_hr_user(
    current_user: User = Depends(get_current_user)
):
    if not current_user.is_hr:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="HR privileges required"
        )
    return current_user


# Эндпоинт для проверки работоспособности
@app.get("/", summary="Проверка работоспособности API")
async def root():
    return {
        "message": "HR Automation API",
        "version": "1.0.0",
        "docs": "/docs",
        "description": "API для автоматизации HR процессов"
    }


# Аутентификация и пользователи
@app.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED,
          summary="Регистрация нового пользователя")
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    # Проверка существующего пользователя
    result = await db.execute(
        select(User).where(
            (User.email == user_data.email) | (User.username == user_data.username)
        )
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or username already registered"
        )

    # Создание нового пользователя
    hashed_password = get_password_hash(user_data.password)
    db_user = User(
        email=user_data.email,
        username=user_data.username,
        hashed_password=hashed_password,
        full_name=user_data.full_name,
        is_hr=user_data.is_hr
    )

    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    return db_user


@app.post("/login", response_model=Token, summary="Вход в систему")
async def login(form_data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.username == form_data.username)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users/me", response_model=UserOut, summary="Получить информацию о текущем пользователе")
async def read_users_me(current_user: User = Depends(get_current_user)):
    """
    Получение информации о текущем аутентифицированном пользователе.

    Требуется авторизация через Bearer токен.
    """
    return current_user


# CRUD для кандидатов
@app.post("/candidates/", response_model=CandidateOut, status_code=status.HTTP_201_CREATED,
          summary="Создать нового кандидата", description="Требуются HR права")
async def create_candidate(
    candidate: CandidateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_hr_user)
):
    """
    Создание нового кандидата в системе.

    Требуются HR права доступа.
    """
    # Проверка на существующего кандидата с таким email
    result = await db.execute(
        select(Candidate).where(Candidate.email == candidate.email)
    )
    existing_candidate = result.scalar_one_or_none()

    if existing_candidate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Candidate with this email already exists"
        )

    db_candidate = Candidate(**candidate.model_dump(), recruiter_id=current_user.id)
    db.add(db_candidate)
    await db.commit()
    await db.refresh(db_candidate)

    return db_candidate


@app.get("/candidates/", response_model=List[CandidateOut], summary="Получить список всех кандидатов")
async def read_candidates(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Получение списка кандидатов с пагинацией.

    - **skip**: Количество записей для пропуска (по умолчанию 0)
    - **limit**: Максимальное количество записей (по умолчанию 100)
    """
    result = await db.execute(
        select(Candidate).offset(skip).limit(limit)
    )
    candidates = result.scalars().all()
    return candidates


@app.get("/candidates/{candidate_id}", response_model=CandidateOut, summary="Получить кандидата по ID")
async def read_candidate(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Получение информации о конкретном кандидате по его ID.

    - **candidate_id**: ID кандидата
    """
    result = await db.execute(
        select(Candidate).where(Candidate.id == candidate_id)
    )
    candidate = result.scalar_one_or_none()

    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found"
        )

    return candidate


@app.put("/candidates/{candidate_id}", response_model=CandidateOut,
         summary="Обновить информацию о кандидате", description="Требуются HR права")
async def update_candidate(
    candidate_id: int,
    candidate_update: CandidateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_hr_user)
):
    """
    Обновление информации о кандидате.

    Требуются HR права доступа.
    """
    result = await db.execute(
        select(Candidate).where(Candidate.id == candidate_id)
    )
    db_candidate = result.scalar_one_or_none()

    if db_candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found"
        )

    update_data = candidate_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_candidate, field, value)

    await db.commit()
    await db.refresh(db_candidate)

    return db_candidate


@app.delete("/candidates/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="Удалить кандидата", description="Требуются HR права")
async def delete_candidate(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_hr_user)
):
    """
    Удаление кандидата из системы.

    Требуются HR права доступа.
    """
    result = await db.execute(
        select(Candidate).where(Candidate.id == candidate_id)
    )
    db_candidate = result.scalar_one_or_none()

    if db_candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found"
        )

    await db.delete(db_candidate)
    await db.commit()

    return None


# CRUD для вакансий
@app.post("/vacancies/", response_model=VacancyOut, status_code=status.HTTP_201_CREATED,
          summary="Создать новую вакансию", description="Требуются HR права")
async def create_vacancy(
    vacancy: VacancyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_hr_user)
):
    """
    Создание новой вакансии.

    Требуются HR права доступа.
    """
    db_vacancy = Vacancy(**vacancy.model_dump())
    db.add(db_vacancy)
    await db.commit()
    await db.refresh(db_vacancy)

    return db_vacancy


@app.get("/vacancies/", response_model=List[VacancyOut], summary="Получить список всех вакансий")
async def read_vacancies(
    skip: int = 0,
    limit: int = 100,
    status: str = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Получение списка вакансий с фильтрацией и пагинацией.

    - **skip**: Количество записей для пропуска (по умолчанию 0)
    - **limit**: Максимальное количество записей (по умолчанию 100)
    - **status**: Фильтр по статусу вакансии (опционально)
    """
    query = select(Vacancy)
    if status:
        query = query.where(Vacancy.status == status)

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    vacancies = result.scalars().all()

    return vacancies


@app.get("/vacancies/{vacancy_id}", response_model=VacancyOut, summary="Получить вакансию по ID")
async def read_vacancy(
    vacancy_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Получение информации о конкретной вакансии по её ID.

    - **vacancy_id**: ID вакансии
    """
    result = await db.execute(
        select(Vacancy).where(Vacancy.id == vacancy_id)
    )
    vacancy = result.scalar_one_or_none()

    if vacancy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vacancy not found"
        )

    return vacancy


@app.put("/vacancies/{vacancy_id}", response_model=VacancyOut,
         summary="Обновить информацию о вакансии", description="Требуются HR права")
async def update_vacancy(
    vacancy_id: int,
    vacancy_update: VacancyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_hr_user)
):
    """
    Обновление информации о вакансии.

    Требуются HR права доступа.
    """
    result = await db.execute(
        select(Vacancy).where(Vacancy.id == vacancy_id)
    )
    db_vacancy = result.scalar_one_or_none()

    if db_vacancy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vacancy not found"
        )

    update_data = vacancy_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_vacancy, field, value)

    await db.commit()
    await db.refresh(db_vacancy)

    return db_vacancy


@app.delete("/vacancies/{vacancy_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="Удалить вакансию", description="Требуются HR права")
async def delete_vacancy(
    vacancy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_hr_user)
):
    """
    Удаление вакансии из системы.

    Требуются HR права доступа.
    """
    result = await db.execute(
        select(Vacancy).where(Vacancy.id == vacancy_id)
    )
    db_vacancy = result.scalar_one_or_none()

    if db_vacancy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vacancy not found"
        )

    await db.delete(db_vacancy)
    await db.commit()

    return None


# Обработчики ошибок
@app.exception_handler(404)
async def not_found_exception_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Resource not found"}
    )


@app.exception_handler(422)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation error", "errors": exc.errors()}
    )


# Блок для запуска напрямую
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
