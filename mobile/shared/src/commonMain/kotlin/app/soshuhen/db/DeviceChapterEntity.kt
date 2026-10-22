package app.soshuhen.db

import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Entity(tableName = "device_chapter")
data class DeviceChapterEntity(
    @PrimaryKey @ColumnInfo(name = "chapter_id") val chapterId: Long,
    @ColumnInfo(name = "series_id") val seriesId: Long,
    val number: Double,
    @ColumnInfo(name = "file_name") val fileName: String,
    val uri: String,
    val etag: String?,
    val size: Long,
    @ColumnInfo(name = "imported_at") val importedAt: Long,
)

@Dao
interface DeviceChapterDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun put(chapter: DeviceChapterEntity)

    @Query("DELETE FROM device_chapter WHERE chapter_id = :chapterId")
    suspend fun delete(chapterId: Long)

    @Query("SELECT * FROM device_chapter WHERE series_id = :seriesId ORDER BY number")
    fun forSeries(seriesId: Long): Flow<List<DeviceChapterEntity>>

    @Query("SELECT * FROM device_chapter WHERE chapter_id = :chapterId")
    suspend fun get(chapterId: Long): DeviceChapterEntity?

    @Query("SELECT chapter_id FROM device_chapter")
    fun ids(): Flow<List<Long>>

    @Query("DELETE FROM device_chapter")
    suspend fun clear()
}
