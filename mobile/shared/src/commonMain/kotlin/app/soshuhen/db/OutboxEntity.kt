package app.soshuhen.db

import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.PrimaryKey
import androidx.room.Query

/** Reading done away from home, waiting to be told to the server. kind: position, complete or prefs. */
@Entity(tableName = "outbox")
data class OutboxEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val kind: String,
    @ColumnInfo(name = "series_id") val seriesId: Long,
    @ColumnInfo(name = "chapter_id") val chapterId: Long?,
    val page: Int?,
    @ColumnInfo(name = "read_at") val readAt: String?,
    val body: String?,
)

@Dao
interface OutboxDao {
    @Insert suspend fun put(entry: OutboxEntity)

    @Query("SELECT * FROM outbox ORDER BY id")
    suspend fun all(): List<OutboxEntity>

    @Query("DELETE FROM outbox WHERE id = :id")
    suspend fun delete(id: Long)

    @Query("DELETE FROM outbox WHERE series_id = :seriesId AND kind = :kind")
    suspend fun deleteKind(seriesId: Long, kind: String)
}
