"""What differs between this service's database engines (#29).

`instances` runs on Postgres or MongoDB, chosen by `INSTANCES_DATABASE_URL`. Django's
`transaction.atomic` is a no-op on MongoDB, and `on_commit` callbacks then run at once,
before anything is known to have been written. MongoDB has no row locks either:
`select_for_update()` is ignored. So code that must be all-or-nothing uses `atomic()`
from here, which starts a real MongoDB transaction there. Inside one, two writers to
the same document conflict and one is aborted, which is what the row lock gave on
Postgres.

`select_related` is also different there. The backend runs each join as a `$lookup`
placed before the query's `$sort` and `$limit`, so a page of 25 joins every row the
filter matched; Postgres joins only the 25. `joined()` keeps the join on Postgres and
fetches the related rows in a second query on MongoDB (#30).
"""

from contextlib import AbstractContextManager
from functools import wraps

from django.db import connection, transaction
from django.db.models import QuerySet


def is_mongodb() -> bool:
    return connection.vendor == "mongodb"


def _atomic() -> AbstractContextManager:
    if is_mongodb():
        from django_mongodb_backend import transaction as mongo_transaction

        return mongo_transaction.atomic()
    return transaction.atomic()


def atomic(func=None):
    """`transaction.atomic` that also holds on MongoDB, as decorator or `with`."""
    if func is None:
        return _atomic()

    @wraps(func)
    def inner(*args, **kwargs):
        with _atomic():
            return func(*args, **kwargs)

    return inner


def joined(queryset: QuerySet, *fields: str) -> QuerySet:
    """`select_related(*fields)` on Postgres, `prefetch_related` on MongoDB."""
    if is_mongodb():
        return queryset.prefetch_related(*fields)
    return queryset.select_related(*fields)
