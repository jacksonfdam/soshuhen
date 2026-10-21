package app.soshuhen.db

import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Entity
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Upsert

/** The server's own JSON, kept verbatim so what is shown offline is what it said. */
@Entity(tableName = "snapshot")
data class SnapshotEntity(
    @PrimaryKey val key: String,
    val json: String,
    @ColumnInfo(name = "fetched_at") val fetchedAt: Long,
)

@Dao
interface SnapshotDao {
    @Upsert suspend fun put(snapshot: SnapshotEntity)

    @Query("SELECT * FROM snapshot WHERE `key` = :key")
    suspend fun get(key: String): SnapshotEntity?
}
