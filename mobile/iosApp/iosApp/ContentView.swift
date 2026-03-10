import SwiftUI
import shared

struct ContentView: View {
    @EnvironmentObject var auth: AuthViewModel
    
    var body: some View {
        if auth.isAuthenticated {
            MainTabView()
        } else {
            LoginView()
        }
    }
}

struct MainTabView: View {
    var body: some View {
        TabView {
            DashboardView()
                .tabItem {
                    Label("Dashboard", systemImage: "chart.bar.fill")
                }
            
            InventoryListView()
                .tabItem {
                    Label("Inventory", systemImage: "shippingbox.fill")
                }
                
            POSView()
                .tabItem {
                    Label("Point of Sale", systemImage: "cart.fill")
                }
                
            SettingsView()
                .tabItem {
                    Label("Settings", systemImage: "gearshape.fill")
                }
        }
        .accentColor(.blue)
    }
}

// Stubs for Views
struct SettingsView: View {
    var body: some View { Text("Settings Screen") }
}
