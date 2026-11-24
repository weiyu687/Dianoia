from alembic import context
from app.db import Base, engine
from app import models, course_models
from app.question_banks import models as bank_models
from app.learning_analytics import models as analytics_models


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if connection := context.config.attributes.get("connection"):
    run(connection)
else:
    with engine.begin() as connection:
        run(connection)
