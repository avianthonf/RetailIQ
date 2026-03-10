package com.retailiq.shared.network

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class AuthApiTests {

    @Test
    fun testSuccessfulLogin() = runTest {
        val mockEngine = MockEngine { request ->
            respond(
                content = """{"success":true,"data":{"access_token":"mock_token","refresh_token":"mock_refresh","user_id":1,"role":"owner","store_id":1},"error":null}""",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, "application/json")
            )
        }

        val mockClient = io.ktor.client.HttpClient(mockEngine) {
            install(ContentNegotiation) {
                json()
            }
        }

        val authApi = AuthApi(mockClient)
        val response = authApi.login(LoginRequest("1234567890", "password"))

        assertTrue(response.success)
        assertEquals("mock_token", response.data?.access_token)
        assertEquals(1, response.data?.user_id)
    }

    @Test
    fun testFailedLogin() = runTest {
        val mockEngine = MockEngine { request ->
            respond(
                content = """{"success":false,"data":null,"error":{"code":"INVALID_CREDENTIALS","message":"Invalid credentials"}}""",
                status = HttpStatusCode.Unauthorized,
                headers = headersOf(HttpHeaders.ContentType, "application/json")
            )
        }

        val mockClient = io.ktor.client.HttpClient(mockEngine) {
            install(ContentNegotiation) {
                json()
            }
        }

        val authApi = AuthApi(mockClient)
        val response = authApi.login(LoginRequest("1234567890", "wrong_pass"))

        assertTrue(!response.success)
        assertEquals("INVALID_CREDENTIALS", response.error?.code)
    }
}
