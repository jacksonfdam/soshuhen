package app.soshuhen.db

import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

/** What the Updates tab lists. */
@Entity(tableName = "import_log")
data class ImportLogEntity(
    @PrimaryKey @ColumnInfo(name = "chapter_id") val chapterId: Long,
    @ColumnInfo(name = "series_id") val seriesId: Long,
    @ColumnInfo(name = "series_title") val seriesTitle: String,
    val number: Double,
    @ColumnInfo(name = "imported_at") val importedAt: Long,
)

@Dao
interface ImportLogDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun put(entry: ImportLogEntity)

    @Query("SELECT * FROM import_log ORDER BY imported_at DESC")
    fun newestFirst(): Flow<List<ImportLogEntity>>
}
