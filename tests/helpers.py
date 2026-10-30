from __future__ import annotations

from functools import lru_cache

from opslens import store


@lru_cache(maxsize=1)
def database_ready() -> bool:
    if not store.available():
        return False
    from opslens.seed import seed

    store.migrate()
    with store.connection() as conn:
        seed(conn)
    return True


def sign_in_admin(client):
    if database_ready():
        from opslens.seed import demo_password

        reply = client.post("/api/v2/login", json={"username": "admin", "password": demo_password()})
        assert reply.status_code == 200, reply.text
    return client
