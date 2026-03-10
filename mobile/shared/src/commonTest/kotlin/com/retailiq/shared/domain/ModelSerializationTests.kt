package com.retailiq.shared.domain

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlinx.serialization.json.Json
import kotlinx.serialization.encodeToString
import kotlinx.datetime.Clock

class ModelSerializationTests {

    @Test
    fun testProductSerialization() {
        val product = Product(
            productId = 1,
            storeId = 1,
            categoryId = 1,
            name = "Test Product",
            skuCode = "TEST-001",
            uom = ProductUom.pieces,
            costPrice = 100.0,
            sellingPrice = 150.0,
            supplierName = null,
            barcode = "123456789",
            imageUrl = null,
            hsnCode = "0000",
            isActive = true
        )

        val jsonString = Json.encodeToString(product)
        assertNotNull(jsonString)
        
        val decoded = Json.decodeFromString<Product>(jsonString)
        assertEquals(product.productId, decoded.productId)
        assertEquals(product.name, decoded.name)
        assertEquals(product.sellingPrice, decoded.sellingPrice)
    }

    @Test
    fun testUserSerialization() {
        val user = User(
            userId = 1,
            mobileNumber = "1234567890",
            fullName = "John Doe",
            email = "john@example.com",
            role = UserRole.owner,
            storeId = 1,
            isActive = true,
            lastLoginAt = Clock.System.now()
        )

        val jsonString = Json.encodeToString(user)
        val decoded = Json.decodeFromString<User>(jsonString)
        assertEquals(user.userId, decoded.userId)
        assertEquals(user.role, decoded.role)
    }
}
