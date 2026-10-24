package app.soshuhen.db

import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Query
import androidx.room.Upsert

/**
 * The ETag of the archive a `.part` was started from. Without it a resume
 * cannot ask the server whether the rest of the bytes still belong to the same
 * file, and a rebuilt archive would be glued onto the old one's head.
 * Here rather than beside the `.part`: the picked folder holds chapters only.
 */
// Keyed by kind as well: chapter 7 and volume 7 are different files.
@Entity(tableName = "import_part", primaryKeys = ["kind", "chapter_id"])
data class ImportPartEntity(
    @ColumnInfo(name = "chapter_id") val chapterId: Long,
    val etag: String,
    @ColumnInfo(defaultValue = "chapter") val kind: String = "chapter",
)

@Dao
interface ImportPartDao {
    @Upsert suspend fun put(part: ImportPartEntity)

    @Query("SELECT etag FROM import_part WHERE kind = :kind AND chapter_id = :chapterId")
    suspend fun etag(kind: String, chapterId: Long): String?

    @Query("DELETE FROM import_part WHERE kind = :kind AND chapter_id = :chapterId")
    suspend fun delete(kind: String, chapterId: Long)

    @Query("DELETE FROM import_part")
    suspend fun clear()
}
