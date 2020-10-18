from gorrabot.api.gitlab import gitlab_session


def paginated_get(url: str, filters: dict = None, actual_page: int = 1):
    if filters is None:
        filters = {}
    filters['page'] = actual_page
    res = gitlab_session.get(url, params=filters)
    res.raise_for_status()
    if int(res.headers['X-Total-Pages']) > actual_page:
        return res.json() + paginated_get(url, filters, actual_page+1)
    else:
        return res.json()

