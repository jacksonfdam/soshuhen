package app.soshuhen.core

import app.soshuhen.db.SoshuhenDatabase
import kotlinx.coroutines.Dispatchers
import kotlin.coroutines.CoroutineContext

// An expect because Room's in-memory builder is JVM-only, and the tests that
// need a store live in commonTest beside the rest. View-model tests pass their
// test dispatcher: on Room's own IO threads a query finishes in real time,
// outside the virtual clock advanceUntilIdle() drives, and its result would
// land after the test had already looked.
expect fun testDatabase(queryContext: CoroutineContext = Dispatchers.IO): SoshuhenDatabase
