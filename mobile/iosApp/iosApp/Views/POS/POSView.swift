import SwiftUI
import shared

struct POSView: View {
    @State private var cartItems: [CartItem] = []
    @State private var showingScanner = false
    
    var totalAmount: Double {
        cartItems.reduce(0) { $0 + ($1.product.sellingPrice ?? 0.0) * $1.quantity }
    }
    
    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Cart Items List
                if cartItems.isEmpty {
                    Spacer()
                    VStack(spacing: 16) {
                        Image(systemName: "cart.badge.plus")
                            .font(.system(size: 80))
                            .foregroundColor(.gray.opacity(0.5))
                        Text("Cart is empty")
                            .font(.title2)
                            .foregroundColor(.secondary)
                        Button(action: { showingScanner = true }) {
                            Text("Scan Item to Add")
                                .fontWeight(.semibold)
                                .padding()
                                .background(Color.blue)
                                .foregroundColor(.white)
                                .cornerRadius(10)
                        }
                    }
                    Spacer()
                } else {
                    List {
                        ForEach($cartItems) { $item in
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(item.product.name)
                                        .font(.headline)
                                    Text("₹\(String(format: "%.2f", item.product.sellingPrice ?? 0.0))")
                                        .font(.subheadline)
                                        .foregroundColor(.secondary)
                                }
                                
                                Spacer()
                                
                                HStack(spacing: 12) {
                                    Button(action: {
                                        if item.quantity > 1 { item.quantity -= 1 }
                                    }) {
                                        Image(systemName: "minus.circle.fill")
                                            .foregroundColor(.blue)
                                    }
                                    .buttonStyle(PlainButtonStyle())
                                    
                                    Text("\(Int(item.quantity))")
                                        .frame(width: 30)
                                        .multilineTextAlignment(.center)
                                        
                                    Button(action: { item.quantity += 1 }) {
                                        Image(systemName: "plus.circle.fill")
                                            .foregroundColor(.blue)
                                    }
                                    .buttonStyle(PlainButtonStyle())
                                }
                            }
                        }
                        .onDelete(perform: deleteItems)
                    }
                    .listStyle(PlainListStyle())
                }
                
                // Bottom Checkout Bar
                VStack {
                    HStack {
                        Text("Total")
                            .font(.title2)
                            .fontWeight(.bold)
                        Spacer()
                        Text("₹\(String(format: "%.2f", totalAmount))")
                            .font(.largeTitle)
                            .fontWeight(.bold)
                            .foregroundColor(.blue)
                    }
                    .padding(.horizontal)
                    .padding(.top, 16)
                    
                    HStack(spacing: 16) {
                        Button(action: { showingScanner = true }) {
                            Image(systemName: "barcode.viewfinder")
                                .font(.title)
                                .frame(height: 50)
                                .frame(maxWidth: 80)
                                .background(Color(.systemGray5))
                                .foregroundColor(.primary)
                                .cornerRadius(12)
                        }
                        
                        Button(action: { checkout() }) {
                            Text("Checkout")
                                .font(.title3)
                                .fontWeight(.bold)
                                .frame(maxWidth: .infinity)
                                .frame(height: 50)
                                .background(cartItems.isEmpty ? Color.gray : Color.green)
                                .foregroundColor(.white)
                                .cornerRadius(12)
                        }
                        .disabled(cartItems.isEmpty)
                    }
                    .padding()
                }
                .background(Color(.systemBackground).shadow(radius: 5, y: -5))
            }
            .navigationTitle("Point of Sale")
            .sheet(isPresented: $showingScanner) {
                BarcodeScannerView(onBarcodeScanned: { barcode in
                    handleBarcode(barcode)
                    showingScanner = false
                })
            }
        }
    }
    
    private func deleteItems(at offsets: IndexSet) {
        cartItems.remove(atOffsets: offsets)
    }
    
    private func handleBarcode(_ barcode: String) {
        // Mock query product from CRDT Sync DB
        if let existingIndex = cartItems.firstIndex(where: { $0.product.barcode == barcode }) {
            cartItems[existingIndex].quantity += 1
        } else {
            let mockProduct = Product(productId: Int.random(in: 100...999), storeId: 1, categoryId: 1, name: "Scanned Item (\(barcode.prefix(4)))", skuCode: barcode, uom: .pieces, costPrice: 50.0, sellingPrice: 99.0, currentStock: 100.0, reorderLevel: 10.0, supplierName: nil, barcode: barcode, imageUrl: nil, isActive: true, hsnCode: nil, gstCategory: "REGULAR")
            cartItems.append(CartItem(product: mockProduct, quantity: 1))
        }
    }
    
    private func checkout() {
        // Save transaction to DB through KMP shared SyncEngine
        cartItems.removeAll()
    }
}

struct CartItem: Identifiable {
    let id = UUID()
    let product: Product
    var quantity: Double
}
