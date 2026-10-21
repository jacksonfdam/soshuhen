package app.soshuhen.core

import app.soshuhen.db.SoshuhenDatabase
import app.soshuhen.db.inMemoryDatabaseBuilder
import kotlin.coroutines.CoroutineContext

actual fun testDatabase(queryContext: CoroutineContext): SoshuhenDatabase =
    inMemoryDatabaseBuilder().setQueryCoroutineContext(queryContext).build()
