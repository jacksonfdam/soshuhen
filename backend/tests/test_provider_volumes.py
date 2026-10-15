"""The providers' volume counts, read from the fields they already return.

Field names are the providers' own (spec, "Provider contracts"): MyAnimeList
num_volumes_read/num_volumes, AniList progressVolumes/volumes, MangaBaka
progress_volume.
"""

from app.providers.anilist import parse_list
from app.providers.mal import parse_page
from app.providers.mangabaka import parse_library


def test_mal_reads_volumes_and_treats_zero_total_as_unknown():
    page = {"data": [
        {"node": {"id": 1, "title": "A", "num_volumes": 16},
         "list_status": {"status": "reading", "num_chapters_read": 3, "num_volumes_read": 2}},
        {"node": {"id": 2, "title": "B", "num_volumes": 0},
         "list_status": {"status": "reading", "num_volumes_read": 0}},
    ]}
    first, second = parse_page(page)
    assert (first.progress_volume, first.total_volumes) == (2, 16)
    # MyAnimeList documents 0 as "unknown": it must never become a cap of 0.
    assert (second.progress_volume, second.total_volumes) == (0, None)


def test_anilist_reads_volumes():
    data = {"MediaListCollection": {"lists": [{"entries": [{
        "status": "CURRENT", "progress": 12, "progressVolumes": 3,
        "media": {"id": 7, "chapters": 40, "volumes": 10,
                  "title": {"romaji": "A", "english": None, "native": None}},
    }]}]}}
    [entry] = parse_list(data)
    assert (entry.progress_volume, entry.total_volumes) == (3, 10)


def test_mangabaka_reads_volume_progress_without_a_total():
    payload = {"data": [{
        "series_id": 5, "state": "reading", "progress_chapter": 4, "progress_volume": 2,
        "Series": {"id": 5, "title": "A", "type": "novel"},
    }]}
    [entry] = parse_library(payload)
    assert (entry.progress_volume, entry.total_volumes) == (2, None)


def test_entries_without_volume_fields_default_safely():
    [mal] = parse_page({"data": [{"node": {"id": 1, "title": "A"},
                                  "list_status": {"status": "reading"}}]})
    assert (mal.progress_volume, mal.total_volumes) == (0, None)
    anilist_data = {"MediaListCollection": {"lists": [{"entries": [{
        "status": "CURRENT", "progress": 1, "progressVolumes": None,
        "media": {"id": 7, "volumes": None, "title": {"romaji": "A"}},
    }]}]}}
    [anilist] = parse_list(anilist_data)
    assert (anilist.progress_volume, anilist.total_volumes) == (0, None)
