package app.soshuhen.db

import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.PrimaryKey
import androidx.room.Query

/**
 * One table for positions, completions and prefs rather than one each: the
 * server must hear them in the order they happened, and a single
 * autoincrement id is that order.
 */
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

    @Query("DELETE FROM outbox")
    suspend fun clear()
}
