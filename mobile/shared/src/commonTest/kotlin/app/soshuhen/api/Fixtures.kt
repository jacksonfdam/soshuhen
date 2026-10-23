package app.soshuhen.api

// Shapes copied from the running server's responses. Test resources are not
// portable across KMP targets, so the bodies live here as strings.
object Fixtures {
    const val SERIES = """[
      {"id": 243, "title": "2.5 Dimensional Seduction", "slug": "2-5-dimensional-seduction",
       "cover_url": "https://s4.anilist.co/file/anilistcdn/media/manga/cover/medium/bx110785.jpg",
       "source_site": "mangadex", "source_url": "https://mangadex.org/title/7bf1",
       "providers": ["anilist"], "writable": true, "downloaded": 0, "known": 12, "in_flight": 0,
       "failed": 0, "total_chapters": 241, "auto_download": false, "kind": "comic",
       "expiring": null, "state": "mapped", "status": "plan_to_read", "progress": 0,
       "updated_at": "2026-10-20T12:00:00.989903+00:00", "last_read_at": null,
       "komga_series_id": null, "score": 7.3, "genres": ["Comedy"], "format": "MANGA"},
      {"id": 7, "title": "Nulls", "slug": "nulls", "cover_url": null, "downloaded": 3,
       "known": 3, "total_chapters": null, "kind": "prose", "status": null, "progress": 1,
       "updated_at": null, "last_read_at": null, "something_new": 1}
    ]"""

    const val DETAIL = """{
      "series": {"id": 1, "title": "Frieren", "slug": "frieren", "cover_url": null,
                 "downloaded": 2, "known": 3, "total_chapters": 141, "kind": "comic",
                 "status": "reading", "progress": 1,
                 "last_read_at": "2026-10-19T21:04:00+00:00", "updated_at": null},
      "metadata": {}, "mapping": null, "volumes": [], "entries": [],
      "chapters": [
        {"id": 11, "number": 1.0, "title": "Chapter 1", "state": "downloaded",
         "file_path": "/manga/frieren/frieren - Ch.0001.cbz", "komga_book_id": null, "available_until": null},
        {"id": 12, "number": 2.0, "title": null, "state": "known", "file_path": null},
        {"id": 13, "number": 2.5, "title": "Extra", "state": "downloaded",
         "file_path": "/manga/frieren/frieren - Ch.0002.5.cbz"}
      ]
    }"""

    const val PROSE_DETAIL = """{
      "series": {"id": 308, "title": "Tsukimichi", "slug": "tsuki", "kind": "prose",
                 "status": "reading", "progress": 0, "state": "local"},
      "metadata": {}, "mapping": null, "chapters": [],
      "volumes": [
        {"id": 41, "number": 1.0, "edition": "light", "title": null, "status": "owned",
         "state": "downloaded", "last_updated": null, "revised": false, "komga_book_id": "k1",
         "file_path": "/manga/tsuki/tsuki - Vol.0001.epub", "first_part": null, "last_part": null,
         "readable": true}
      ],
      "entries": [{"provider": "mal", "provider_media_id": "1", "status": "reading",
                   "user_progress_chapter": 2, "user_progress_volume": 3, "updated_at": null}]
    }"""

    const val PROSE_DETAIL_OLD = """{
      "series": {"id": 308, "title": "Tsukimichi", "slug": "tsuki", "kind": "prose"},
      "metadata": {}, "mapping": null, "chapters": [], "entries": [],
      "volumes": [
        {"number": 1.0, "edition": "light", "title": null, "status": "owned",
         "state": "downloaded", "last_updated": null, "revised": false, "komga_book_id": "k1"}
      ]
    }"""

    const val IDENTITY = """{"app": "soshuhen", "name": "Soshuhen", "version": "0.1.0",
      "instance_id": "8c0e1b9a-5f2e-4c1d-9a7b-3f6e2d1c0b9a"}"""
}
