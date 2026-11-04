"""Pagination for every list endpoint (#10). Set globally in REST_FRAMEWORK."""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """`?page=` and `?page_size=` (default 25, at most 100).

    Responds `{count, next, previous, results}`.
    """

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
