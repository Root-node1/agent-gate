"""Offset/limit pagination for dashboard tables."""

from rest_framework.pagination import LimitOffsetPagination


class DashboardPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = 200
    limit_query_param = "limit"
    offset_query_param = "offset"
