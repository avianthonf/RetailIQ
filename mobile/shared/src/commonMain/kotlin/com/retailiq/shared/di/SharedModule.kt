package com.retailiq.shared.di

import org.koin.core.context.startKoin
import org.koin.dsl.module
import com.retailiq.shared.network.RetailIQApi
import com.retailiq.shared.network.AuthApi
import com.retailiq.shared.sync.SyncEngine
import com.retailiq.shared.database.RetailIQDatabase

val sharedModule = module {
    single { RetailIQApi(get()).client }
    single { AuthApi(get()) }
    single { SyncEngine(get()) }
    // database gets provided by platform-specific modules since expect/actual driver
}

fun initKoin() {
    startKoin {
        modules(sharedModule)
    }
}
