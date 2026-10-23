"""What an import will do, decided before anything is written.

The review screen shows exactly this plan and the job carries out exactly this
plan, so every reason a file is left out has to be decided here, once.
"""

from decimal import Decimal

from app.downloader.paths import chapter_filename, volume_filename
from app.importer.numbering import NumberedChapter, ReadVolume
from app.importer.pdf import PdfEntry
from app.importer.plan import Existing, Override, plan_import

SLUG = "tsukimichi-moonlit-fantasy-2"
NOTHING = Existing(chapters=frozenset(), volumes=frozenset())


def chapter(number: str, title: str | None = None) -> NumberedChapter:
    entry = PdfEntry(title=title or f"Chapter {number}", pages=["text"], images=[])
    return NumberedChapter(number=Decimal(number), title=title, entries=[entry])


def web(volume: int, *numbers: str) -> ReadVolume:
    return ReadVolume(Decimal(volume), "web", [chapter(n, f"Title {n}") for n in numbers], None)


def light(volume: int) -> ReadVolume:
    return ReadVolume(Decimal(volume), "light", [chapter("1"), chapter("2")], None)


def test_web_volume_lists_its_chapter_files():
    [planned] = plan_import(SLUG, [("WN 15.pdf", "a", web(15, "213", "214"))], NOTHING, {})

    assert planned.status == "ready"
    assert planned.chapters == [Decimal(213), Decimal(214)]
    assert planned.outputs == [
        chapter_filename(SLUG, Decimal(213), "Title 213", kind="prose"),
        chapter_filename(SLUG, Decimal(214), "Title 214", kind="prose"),
    ]


def test_light_volume_is_one_volume_file():
    [planned] = plan_import(SLUG, [("LN 19.pdf", "a", light(19))], NOTHING, {})

    assert planned.status == "ready"
    assert planned.chapters == []
    assert planned.outputs == [volume_filename(SLUG, Decimal(19))]


def test_unreadable_file_is_reported():
    [planned] = plan_import(SLUG, [("scan.pdf", "a", None)], NOTHING, {})

    assert planned.status == "unreadable"
    assert planned.outputs == []


def test_existing_chapters_are_exists_unless_replaced():
    existing = Existing(chapters=frozenset({Decimal(214)}), volumes=frozenset())
    files = [("WN 15.pdf", "a", web(15, "213", "214"))]

    [kept] = plan_import(SLUG, files, existing, {})
    [replaced] = plan_import(SLUG, files, existing, {"a": Override(replace=True)})

    assert kept.status == "exists"
    assert replaced.status == "ready"


def test_existing_light_volume_is_exists():
    existing = Existing(chapters=frozenset(), volumes=frozenset({(Decimal(19), "light")}))

    [planned] = plan_import(SLUG, [("LN 19.pdf", "a", light(19))], existing, {})

    assert planned.status == "exists"


def test_same_file_twice_is_duplicate():
    planned = plan_import(
        SLUG, [("one.pdf", "same", light(19)), ("copy.pdf", "same", light(19))], NOTHING, {}
    )

    assert [p.status for p in planned] == ["ready", "duplicate"]


def test_two_files_claiming_one_volume_is_duplicate():
    planned = plan_import(SLUG, [("a.pdf", "a", light(19)), ("b.pdf", "b", light(19))], NOTHING, {})

    assert [p.status for p in planned] == ["ready", "duplicate"]


def test_both_editions_of_one_volume_are_both_ready():
    planned = plan_import(
        SLUG, [("WN 1.pdf", "a", web(1, "1", "2")), ("LN 1.pdf", "b", light(1))], NOTHING, {}
    )

    assert [p.status for p in planned] == ["ready", "ready"]


def test_generated_number_colliding_with_a_real_one_is_conflict():
    planned = plan_import(SLUG, [("WN 1.pdf", "a", web(1, "9", "9.5", "9.5"))], NOTHING, {})

    assert planned[0].status == "conflict"
    assert "9.5" in planned[0].reason


def test_overlapping_web_volumes_in_one_drop_conflict():
    planned = plan_import(
        SLUG, [("WN 1.pdf", "a", web(1, "1", "2")), ("WN 2.pdf", "b", web(2, "2", "3"))], NOTHING, {}
    )

    assert [p.status for p in planned] == ["ready", "conflict"]


def test_no_volume_number_is_conflict():
    read = ReadVolume(None, "light", [chapter("1")], None)

    [planned] = plan_import(SLUG, [("book.pdf", "a", read)], NOTHING, {})

    assert planned.status == "conflict"
    assert planned.reason == "no volume number"


def test_override_flips_edition_and_volume():
    [planned] = plan_import(
        SLUG,
        [("odd.pdf", "a", web(3, "1", "2"))],
        NOTHING,
        {"a": Override(volume=Decimal(20), edition="light")},
    )

    assert (planned.volume, planned.edition) == (Decimal(20), "light")
    assert planned.outputs == [volume_filename(SLUG, Decimal(20))]
