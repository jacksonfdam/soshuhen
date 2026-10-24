package app.soshuhen.db

import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

/**
 * Apart from device_chapter so the Updates tab still lists a chapter after it
 * is deleted from the device: it reports what arrived, not what is left.
 * Keyed by chapter, so a chapter copied again moves to the top instead of
 * being listed twice; and by kind, since a volume's id can equal a chapter's.
 */
@Entity(tableName = "import_log", primaryKeys = ["kind", "chapter_id"])
data class ImportLogEntity(
    @ColumnInfo(name = "chapter_id") val chapterId: Long,
    @ColumnInfo(name = "series_id") val seriesId: Long,
    @ColumnInfo(name = "series_title") val seriesTitle: String,
    val number: Double,
    @ColumnInfo(name = "imported_at") val importedAt: Long,
    @ColumnInfo(defaultValue = "chapter") val kind: String = "chapter",
)

@Dao
interface ImportLogDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun put(entry: ImportLogEntity)

    @Query("SELECT * FROM import_log ORDER BY imported_at DESC")
    fun newestFirst(): Flow<List<ImportLogEntity>>
}
