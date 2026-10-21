package app.soshuhen.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

/** What the Updates tab lists. */
@Entity(tableName = "import_log")
data class ImportLogEntity(
    @PrimaryKey @ColumnInfo(name = "chapter_id") val chapterId: Long,
    @ColumnInfo(name = "series_id") val seriesId: Long,
    @ColumnInfo(name = "series_title") val seriesTitle: String,
    val number: Double,
    @ColumnInfo(name = "imported_at") val importedAt: Long,
)
