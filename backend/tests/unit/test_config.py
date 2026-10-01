from signallens.config import normalize_database_url


def test_hosted_connection_strings_become_asyncpg_urls():
    url = "postgresql://u:p@ep-x.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    assert normalize_database_url(url) == "postgresql+asyncpg://u:p@ep-x.aws.neon.tech/neondb?ssl=require"
    assert normalize_database_url("postgres://u:p@h:5432/db") == "postgresql+asyncpg://u:p@h:5432/db"


def test_asyncpg_urls_and_other_drivers_are_left_alone():
    url = "postgresql+asyncpg://signallens:signallens@127.0.0.1:5432/signallens"
    assert normalize_database_url(url) == url
    assert normalize_database_url("sqlite:///x.db") == "sqlite:///x.db"


def test_disabled_ssl_modes_are_dropped():
    assert normalize_database_url("postgresql://u:p@h/db?sslmode=disable") == "postgresql+asyncpg://u:p@h/db"
