package app.soshuhen.db

import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Entity
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Upsert

/**
 * The ETag of the archive a `.part` was started from. Without it a resume
 * cannot ask the server whether the rest of the bytes still belong to the same
 * file, and a rebuilt archive would be glued onto the old one's head.
 * Here rather than beside the `.part`: the picked folder holds chapters only.
 */
@Entity(tableName = "import_part")
data class ImportPartEntity(
    @PrimaryKey @ColumnInfo(name = "chapter_id") val chapterId: Long,
    val etag: String,
)

@Dao
interface ImportPartDao {
    @Upsert suspend fun put(part: ImportPartEntity)

    @Query("SELECT etag FROM import_part WHERE chapter_id = :chapterId")
    suspend fun etag(chapterId: Long): String?

    @Query("DELETE FROM import_part WHERE chapter_id = :chapterId")
    suspend fun delete(chapterId: Long)
}
