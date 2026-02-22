# Retail Intelligence Backend

Modular Flask backend powering analytics, forecasting, inventory, NLP
processing, and transaction workflows.

------------------------------------------------------------------------

## Overview

This backend provides domain-specific services for:

-   Customer management\
-   Inventory tracking\
-   Transaction processing\
-   Sales forecasting\
-   Business analytics\
-   NLP-based insights\
-   Decision support workflows

The system follows a **modular monolith architecture** with clear domain
separation and asynchronous task handling.

------------------------------------------------------------------------

## Architecture

High-Level Flow:

Client → Flask API → Domain Modules → SQLAlchemy ORM → Database\
Client → Flask API → Celery → Background Worker → Database

Key characteristics:

-   Blueprint-based modular design\
-   Centralized database layer\
-   Async processing for heavy workloads\
-   Containerized runtime

------------------------------------------------------------------------

## Technology Stack

-   Flask\
-   SQLAlchemy\
-   Alembic\
-   Celery\
-   Redis / RabbitMQ\
-   PostgreSQL\
-   Docker & Docker Compose\
-   Pytest

------------------------------------------------------------------------

## Project Structure

backend/ │ ├── app/ │ ├── **init**.py │ ├── database.py │ ├── analytics/
│ ├── forecasting/ │ ├── inventory/ │ ├── customers/ │ ├── transactions/
│ ├── nlp/ │ ├── decisions/ │ ├── tasks/ │ └── models/ │ ├── migrations/
│ ├── env.py │ └── versions/ │ ├── tests/ │ ├── celery_worker.py ├──
wsgi.py ├── Dockerfile ├── docker-compose.yml ├── requirements.txt └──
README.md

------------------------------------------------------------------------

## Local Development

1.  Clone repository:

    git clone https://github.com/yourusername/project.git\
    cd project

2.  Create virtual environment:

    python -m venv venv\
    venv`\Scripts`{=tex}`\activate  `{=tex}(Windows)

3.  Install dependencies:

    pip install -r requirements.txt

4.  Configure environment variables in `.env`.

5.  Run:

    flask run

------------------------------------------------------------------------

## Docker Setup

Build and start services:

docker-compose up --build

Stop services:

docker-compose down

------------------------------------------------------------------------

## Environment Variables (Example)

FLASK_ENV=development\
SECRET_KEY=your_secret_key\
DATABASE_URL=postgresql://user:password@db:5432/appdb\
CELERY_BROKER_URL=redis://redis:6379/0\
CELERY_RESULT_BACKEND=redis://redis:6379/0

------------------------------------------------------------------------

## Database & Migrations

Apply migrations:

flask db upgrade

Create migration:

flask db migrate -m "message"\
flask db upgrade

------------------------------------------------------------------------

## Background Tasks

Start Celery worker:

celery -A celery_worker.celery worker --loglevel=info

Used for:

-   Forecast model generation\
-   Analytics report processing\
-   NLP batch jobs\
-   Scheduled operations

------------------------------------------------------------------------

## Testing

Run full test suite:

pytest

------------------------------------------------------------------------

## Deployment Recommendations

-   Use Gunicorn as WSGI server\
-   Use Nginx as reverse proxy\
-   Use PostgreSQL in production\
-   Use Redis for Celery\
-   Enable structured logging\
-   Enable CI for automated tests

