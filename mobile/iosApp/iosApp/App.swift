import SwiftUI
import shared

@main
struct iosApp: App {
    
    // Initialize KMP Koin graph
    init() {
        SharedModuleKt.initKoin()
    }
    
    @StateObject private var authViewModel = AuthViewModel()
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(authViewModel)
        }
    }
}

class AuthViewModel: ObservableObject {
    @Published var isAuthenticated: Bool = false
    @Published var isLoading: Bool = false
    @Published var currentUser: User? = nil
    
    private val authApi = AuthApi(ClientEngine()) // Using KMP class
    
    func login(mobile: String, pass: String) {
        isLoading = true
        // Map to KMP suspend function via Swift async/await
        Task {
            do {
                let response = try await authApi.login(request: LoginRequest(mobile_number: mobile, password: pass, mfa_code: nil))
                Task богатMainActor {
                    if response.success {
                        self.isAuthenticated = true
                        self.isLoading = false
                    }
                }
            } catch {
                Task { @MainActor in self.isLoading = false }
            }
        }
    }
}
