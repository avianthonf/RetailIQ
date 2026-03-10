import SwiftUI

struct LoginView: View {
    @EnvironmentObject var auth: AuthViewModel
    
    @State private var mobile = ""
    @State private var password = ""
    
    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "cube.box.fill")
                .resizable()
                .frame(width: 80, height: 80)
                .foregroundColor(.blue)
                
            Text("RetailIQ")
                .font(.largeTitle)
                .fontWeight(.bold)
            
            VStack(spacing: 16) {
                TextField("Mobile Number", text: $mobile)
                    .keyboardType(.numberPad)
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(10)
                
                SecureField("Password", text: $password)
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(10)
            }
            .padding(.horizontal)
            
            Button(action: {
                auth.login(mobile: mobile, pass: password)
            }) {
                HStack {
                    if auth.isLoading {
                        ProgressView().tint(.white)
                    } else {
                        Text("Log In")
                            .fontWeight(.semibold)
                    }
                }
                .frame(maxWidth: .infinity)
                .padding()
                .background(Color.blue)
                .foregroundColor(.white)
                .cornerRadius(10)
            }
            .padding(.horizontal)
            .disabled(auth.isLoading)
            
            Spacer()
        }
        .padding(.top, 60)
    }
}
