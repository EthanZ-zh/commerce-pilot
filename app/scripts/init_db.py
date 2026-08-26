from app.domain.models import Base
from app.infrastructure.database import engine


def main() -> None:
    Base.metadata.create_all(engine)
    print("Database schema initialized.")


if __name__ == "__main__":
    main()
