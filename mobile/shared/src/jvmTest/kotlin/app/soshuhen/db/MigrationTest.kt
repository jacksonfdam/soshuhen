package app.soshuhen.db

import androidx.room.testing.MigrationTestHelper
import androidx.sqlite.driver.bundled.BundledSQLiteDriver
import androidx.sqlite.execSQL
import kotlin.io.path.createTempDirectory
import kotlin.io.path.deleteRecursively
import kotlin.io.path.div
import kotlin.io.path.Path
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals

// The phone already holds a version 2 database with unsent copies in it; a
// migration that drops them would copy every cut-off chapter from the start.
class MigrationTest {
    private val dir = createTempDirectory()
    private val helper = MigrationTestHelper(
        schemaDirectoryPath = Path("schemas"),
        databasePath = dir / "test.db",
        driver = BundledSQLiteDriver(),
        databaseClass = SoshuhenDatabase::class,
    )

    @OptIn(kotlin.io.path.ExperimentalPathApi::class)
    @AfterTest fun tearDown() = dir.deleteRecursively()

    @Test fun version2RowsBecomeChapterRowsInVersion3() {
        val old = helper.createDatabase(2)
        old.execSQL("INSERT INTO import_part (chapter_id, etag) VALUES (7, '\"e\"')")
        old.execSQL(
            "INSERT INTO import_log (chapter_id, series_id, series_title, number, imported_at) VALUES (7, 1, 'T', 1.0, 5)",
        )
        old.close()
        val connection = helper.runMigrationsAndValidate(3)
        try {
            connection.prepare("SELECT kind, etag FROM import_part WHERE chapter_id = 7").use {
                it.step()
                assertEquals("chapter", it.getText(0))
                assertEquals("\"e\"", it.getText(1))
            }
            connection.prepare("SELECT kind FROM import_log WHERE chapter_id = 7").use {
                it.step()
                assertEquals("chapter", it.getText(0))
            }
        } finally {
            connection.close()
        }
    }

    // Marks and queued reading from before profiles are the managing profile's
    // (key 0): an upgrade must neither drop them nor strand them unowned.
    @Test fun marksAndOutboxBelongToTheManagerAfter3To4() {
        val old = helper.createDatabase(3)
        old.execSQL("INSERT INTO marked (series_id, slug, marked_at) VALUES (5, 'frieren', 1)")
        old.execSQL(
            "INSERT INTO outbox (kind, series_id, chapter_id, page, read_at, body) VALUES ('position', 5, 9, 3, '2026-01-01T00:00:00Z', NULL)",
        )
        old.close()
        val connection = helper.runMigrationsAndValidate(4)
        try {
            connection.prepare("SELECT profile_key FROM marked WHERE series_id = 5").use {
                it.step()
                assertEquals(0L, it.getLong(0))
            }
            connection.prepare("SELECT profile_key FROM outbox WHERE series_id = 5").use {
                it.step()
                assertEquals(0L, it.getLong(0))
            }
            connection.execSQL("INSERT INTO marked (profile_key, series_id, slug, marked_at) VALUES (7, 5, 'frieren', 2)")
            connection.prepare("SELECT count(*) FROM marked WHERE series_id = 5").use {
                it.step()
                assertEquals(2L, it.getLong(0))
            }
        } finally {
            connection.close()
        }
    }
}
