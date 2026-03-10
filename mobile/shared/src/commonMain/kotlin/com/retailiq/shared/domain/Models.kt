package com.retailiq.shared.domain

import kotlinx.serialization.Serializable
import kotlinx.datetime.Instant

@Serializable
enum class UserRole {
    owner, staff
}

@Serializable
data class User(
    val userId: Int,
    val mobileNumber: String,
    val fullName: String?,
    val email: String?,
    val role: UserRole?,
    val storeId: Int?,
    val isActive: Boolean,
    val mfaEnabled: Boolean = false,
    val lastLoginAt: Instant? = null
)

@Serializable
enum class StoreType {
    grocery, pharmacy, general, electronics, clothing, other
}

@Serializable
data class Store(
    val storeId: Int,
    val ownerUserId: Int?,
    val storeName: String?,
    val storeType: StoreType?,
    val city: String?,
    val state: String?,
    val gstNumber: String?,
    val currencySymbol: String? = "INR",
    val timezone: String?
)

@Serializable
data class Category(
    val categoryId: Int,
    val storeId: Int?,
    val name: String?,
    val colorTag: String?,
    val isActive: Boolean = true,
    val gstRate: Double? = 18.0
)

@Serializable
enum class ProductUom {
    pieces, kg, litre, pack
}

@Serializable
data class Product(
    val productId: Int,
    val storeId: Int?,
    val categoryId: Int?,
    val name: String,
    val skuCode: String?,
    val uom: ProductUom?,
    val costPrice: Double?,
    val sellingPrice: Double?,
    val currentStock: Double? = 0.0,
    val reorderLevel: Double? = 0.0,
    val supplierName: String?,
    val barcode: String?,
    val imageUrl: String?,
    val isActive: Boolean = true,
    val hsnCode: String?,
    val gstCategory: String? = "REGULAR"
)

@Serializable
enum class PaymentMode {
    CASH, UPI, CARD, CREDIT
}

@Serializable
data class Transaction(
    val transactionId: String,
    val storeId: Int?,
    val customerId: Int?,
    val paymentMode: PaymentMode?,
    val notes: String?,
    val createdAt: Instant?,
    val isReturn: Boolean = false,
    val totalAmount: Double = 0.0,
    val originalTransactionId: String?,
    val sessionId: String?
)

@Serializable
data class TransactionItem(
    val itemId: Int,
    val transactionId: String?,
    val productId: Int?,
    val quantity: Double?,
    val sellingPrice: Double?,
    val originalPrice: Double?,
    val discountAmount: Double? = 0.0,
    val costPriceAtTime: Double?
)
