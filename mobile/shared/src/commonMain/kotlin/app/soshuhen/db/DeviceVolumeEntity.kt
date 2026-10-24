package app.soshuhen.db

import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

/** A light novel volume's EPUB on the device, beside device_chapter rather than in it: the ids are another table's. */
@Entity(tableName = "device_volume")
data class DeviceVolumeEntity(
    @PrimaryKey @ColumnInfo(name = "volume_id") val volumeId: Long,
    @ColumnInfo(name = "series_id") val seriesId: Long,
    val number: Double,
    @ColumnInfo(name = "file_name") val fileName: String,
    val uri: String,
    val etag: String?,
    val size: Long,
    @ColumnInfo(name = "imported_at") val importedAt: Long,
)

@Dao
interface DeviceVolumeDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun put(volume: DeviceVolumeEntity)

    @Query("DELETE FROM device_volume WHERE volume_id = :volumeId")
    suspend fun delete(volumeId: Long)

    @Query("SELECT * FROM device_volume WHERE series_id = :seriesId ORDER BY number")
    fun forSeries(seriesId: Long): Flow<List<DeviceVolumeEntity>>

    @Query("SELECT * FROM device_volume WHERE volume_id = :volumeId")
    suspend fun get(volumeId: Long): DeviceVolumeEntity?

    @Query("SELECT DISTINCT series_id FROM device_volume")
    fun seriesIds(): Flow<List<Long>>

    @Query("UPDATE device_volume SET etag = :etag WHERE volume_id = :volumeId")
    suspend fun setEtag(volumeId: Long, etag: String)

    @Query("DELETE FROM device_volume")
    suspend fun clear()
}
