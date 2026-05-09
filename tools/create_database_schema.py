from core.database_builder import DatabaseBuilder


def create_database_schema(
    db_path: str
):

    db = DatabaseBuilder(db_path)

    db.create_database()

    return {
        "status": "success",
        "db_path": db_path
    }