package app.soshuhen.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

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
