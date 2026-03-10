package com.retailiq.shared.network

import io.ktor.client.HttpClient
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.plugins.logging.LogLevel
import io.ktor.client.plugins.logging.Logger
import io.ktor.client.plugins.logging.Logging
import io.ktor.client.plugins.auth.Auth
import io.ktor.client.plugins.auth.providers.bearer
import io.ktor.client.request.header
import io.ktor.http.ContentType
import io.ktor.http.URLProtocol
import io.ktor.http.contentType
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json

expect fun httpClient(config: HttpClientConfig<*>.() -> Unit = {}): HttpClient

class RetailIQApi(private val tokenManager: TokenManager) {
    
    val client = httpClient {
        install(ContentNegotiation) {
            json(Json {
                prettyPrint = true
                isLenient = true
                ignoreUnknownKeys = true
            })
        }
        
        install(Logging) {
            logger = object : Logger {
                override fun log(message: String) {
                    println("Ktor: $message")
                }
            }
            level = LogLevel.INFO
        }
        
        install(Auth) {
            bearer {
                loadTokens {
                    io.ktor.client.plugins.auth.providers.BearerTokens(
                        accessToken = tokenManager.getAccessToken() ?: "",
                        refreshToken = tokenManager.getRefreshToken() ?: ""
                    )
                }
                refreshTokens {
                    // Logic to refresh token goes here
                    io.ktor.client.plugins.auth.providers.BearerTokens(
                        accessToken = tokenManager.getAccessToken() ?: "",
                        refreshToken = tokenManager.getRefreshToken() ?: ""
                    )
                }
            }
        }
        
        defaultRequest {
            url {
                protocol = URLProtocol.HTTPS
                host = "api.retailiq.com" // Update for specific environment
            }
            contentType(ContentType.Application.Json)
        }
    }
}

interface TokenManager {
    fun getAccessToken(): String?
    fun getRefreshToken(): String?
    fun saveTokens(accessToken: String, refreshToken: String)
    fun clearTokens()
}
