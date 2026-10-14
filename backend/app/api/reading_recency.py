"""When a series was last read, for every screen that orders by it.

Not `list_entry.updated_at`: a sync rewrites that whenever it touches the row,
so ordering by it put whatever MyAnimeList or AniList refreshed last at the
front. Only reading moves these two: a page turned in the reader, and progress
moving forward from any path. `greatest` skips a null, so either one alone is
enough, and a series with neither is null rather than a guess.

Correlated on `s.id`, so the query using it must alias series as `s`.
"""

LAST_READ_AT = """
greatest(
    (select max(p.created_at) from progress_event p where p.series_id = s.id),
    (select r.updated_at from reading_position r where r.series_id = s.id)
)
"""
