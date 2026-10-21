package app.soshuhen.db

import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Entity(tableName = "marked")
data class MarkedEntity(
    @PrimaryKey @ColumnInfo(name = "series_id") val seriesId: Long,
    val slug: String,
    @ColumnInfo(name = "marked_at") val markedAt: Long,
)

@Dao
interface MarkedDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun put(marked: MarkedEntity)

    @Query("DELETE FROM marked WHERE series_id = :seriesId")
    suspend fun delete(seriesId: Long)

    @Query("SELECT EXISTS(SELECT 1 FROM marked WHERE series_id = :seriesId)")
    fun isMarked(seriesId: Long): Flow<Boolean>

    @Query("SELECT series_id FROM marked")
    fun ids(): Flow<List<Long>>
}
