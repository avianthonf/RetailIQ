import SwiftUI
import shared

struct InventoryListView: View {
    @State private var products: [Product] = []
    @State private var searchText = ""
    @State private var isLoading = false
    @State private var showingScanner = false
    
    var filteredProducts: [Product] {
        if searchText.isEmpty {
            return products
        } else {
            return products.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
        }
    }
    
    var body: some View {
        NavigationView {
            Group {
                if isLoading {
                    ProgressView("Loading inventory...")
                } else if products.isEmpty {
                    VStack {
                        Image(systemName: "shippingbox.circle")
                            .font(.system(size: 60))
                            .foregroundColor(.gray)
                        Text("No products found")
                            .font(.headline)
                            .padding(.top)
                    }
                } else {
                    List(filteredProducts, id: \.productId) { product in
                        ProductRowView(product: product)
                    }
                    .listStyle(PlainListStyle())
                }
            }
            .navigationTitle("Inventory")
            .searchable(text: $searchText, prompt: "Search products...")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { showingScanner = true }) {
                        Image(systemName: "barcode.viewfinder")
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { /* Add product */ }) {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $showingScanner) {
                BarcodeScannerView(onBarcodeScanned: { barcode in
                    searchText = barcode
                    showingScanner = false
                })
            }
            .onAppear {
                loadProducts()
            }
        }
    }
    
    private func loadProducts() {
        isLoading = true
        // Mock loading from KMP SyncEngine / Repository
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            products = [
                Product(productId: 1, storeId: 1, categoryId: 1, name: "Premium Coffee Beans", skuCode: "CF-001", uom: .pack, costPrice: 250.0, sellingPrice: 350.0, currentStock: 45.0, reorderLevel: 10.0, supplierName: "Global Beans", barcode: "8901234567890", imageUrl: nil, isActive: true, hsnCode: "0901", gstCategory: "REGULAR"),
                Product(productId: 2, storeId: 1, categoryId: 2, name: "Organic Green Tea", skuCode: "TG-002", uom: .pack, costPrice: 150.0, sellingPrice: 200.0, currentStock: 12.0, reorderLevel: 15.0, supplierName: "Nature Extracts", barcode: "8901234567891", imageUrl: nil, isActive: true, hsnCode: "0902", gstCategory: "REGULAR")
            ]
            isLoading = false
        }
    }
}

struct ProductRowView: View {
    let product: Product
    
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(product.name)
                    .font(.headline)
                Text(product.skuCode ?? "N/A")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            Spacer()
            
            VStack(alignment: .trailing, spacing: 4) {
                Text("₹\(String(format: "%.2f", product.sellingPrice ?? 0.0))")
                    .font(.subheadline)
                    .fontWeight(.bold)
                
                HStack(spacing: 4) {
                    Circle()
                        .fill(stockColor)
                        .frame(width: 8, height: 8)
                    Text("\(String(format: "%.1f", product.currentStock ?? 0.0)) qty")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding(.vertical, 4)
    }
    
    private var stockColor: Color {
        let stock = product.currentStock ?? 0.0
        let reorder = product.reorderLevel ?? 0.0
        if stock <= 0 { return .red }
        if stock <= reorder { return .orange }
        return .green
    }
}
