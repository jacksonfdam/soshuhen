"""Whether the library already holds something of a series.

What turns a series without a source from waiting into `local`. The review
queue and the dashboard's pending count ask the same question as the series
state, so it is written once here and all three cannot drift apart.

Correlated on `s.id`, so the query using it must alias series as `s`.
"""

HOLDS_FILES = """
(exists (select 1 from chapter c where c.series_id = s.id and c.state = 'downloaded')
 or exists (select 1 from volume v where v.series_id = s.id and v.state = 'downloaded'))
"""
