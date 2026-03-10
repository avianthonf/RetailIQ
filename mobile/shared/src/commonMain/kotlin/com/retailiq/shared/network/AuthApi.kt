package com.retailiq.shared.network

import kotlinx.serialization.Serializable
import io.ktor.client.HttpClient

@Serializable
data class LoginRequest(
    val mobile_number: String,
    val password: String,
    val mfa_code: String? = null
)

@Serializable
data class LoginResponse(
    val success: Boolean,
    val data: AuthData?,
    val error: AuthError?
)

@Serializable
data class AuthData(
    val access_token: String?,
    val refresh_token: String?,
    val user_id: Int?,
    val role: String?,
    val store_id: Int?,
    val mfa_required: Boolean? = false,
    val message: String? = null
)

@Serializable
data class AuthError(
    val code: String,
    val message: String
)

class AuthApi(private val client: HttpClient) {
    suspend fun login(request: LoginRequest): LoginResponse {
        import io.ktor.client.call.body
        import io.ktor.client.request.post
        import io.ktor.client.request.setBody
        
        return client.post("/api/v1/auth/login") {
            setBody(request)
        }.body()
    }
    
    // Additional auth endpoints (register, verify OTP, etc.)
}
