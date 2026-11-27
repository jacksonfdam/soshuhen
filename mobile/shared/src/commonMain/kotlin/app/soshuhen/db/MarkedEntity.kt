package app.soshuhen.db

import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

// Keyed by profile as well as series: two people on one tablet mark series
// apart. Rows from before profiles are the managing profile's, key 0.
@Entity(tableName = "marked", primaryKeys = ["profile_key", "series_id"])
data class MarkedEntity(
    @ColumnInfo(name = "profile_key", defaultValue = "0") val profileKey: Long = 0,
    @ColumnInfo(name = "series_id") val seriesId: Long,
    val slug: String,
    @ColumnInfo(name = "marked_at") val markedAt: Long,
)

@Dao
interface MarkedDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun put(marked: MarkedEntity)

    @Query("DELETE FROM marked WHERE profile_key = :profileKey AND series_id = :seriesId")
    suspend fun delete(profileKey: Long, seriesId: Long)

    @Query("SELECT EXISTS(SELECT 1 FROM marked WHERE profile_key = :profileKey AND series_id = :seriesId)")
    fun isMarked(profileKey: Long, seriesId: Long): Flow<Boolean>

    @Query("SELECT series_id FROM marked WHERE profile_key = :profileKey")
    fun ids(profileKey: Long): Flow<List<Long>>

    @Query("SELECT DISTINCT series_id FROM marked")
    fun allIds(): Flow<List<Long>>

    @Query("SELECT EXISTS(SELECT 1 FROM marked WHERE profile_key <> :profileKey AND series_id = :seriesId)")
    suspend fun markedByOthers(profileKey: Long, seriesId: Long): Boolean

    @Query("DELETE FROM marked")
    suspend fun clear()
}
