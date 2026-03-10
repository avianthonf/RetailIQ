import SwiftUI

struct DashboardView: View {
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 20) {
                    // Summary Cards
                    HStack(spacing: 16) {
                        SummaryCard(title: "Today's Sales", value: "₹45,230", icon: "indianrupeesign.circle.fill", color: .green)
                        SummaryCard(title: "Transactions", value: "128", icon: "cart.fill", color: .blue)
                    }
                    .padding(.horizontal)
                    
                    HStack(spacing: 16) {
                        SummaryCard(title: "Avg Basket", value: "₹353", icon: "basket.fill", color: .orange)
                        SummaryCard(title: "Low Stock", value: "14 items", icon: "exclamationmark.triangle.fill", color: .red)
                    }
                    .padding(.horizontal)
                    
                    // Chart Placeholder
                    VStack(alignment: .leading) {
                        Text("Revenue Trend (7 Days)")
                            .font(.headline)
                            .padding(.bottom, 8)
                        
                        RoundedRectangle(cornerRadius: 12)
                            .fill(Color(.systemGray6))
                            .frame(height: 200)
                            .overlay(
                                VStack {
                                    Image(systemName: "chart.xyaxis.line")
                                        .font(.system(size: 40))
                                        .foregroundColor(.gray)
                                    Text("Analytics charts via KMP")
                                        .foregroundColor(.secondary)
                                        .padding(.top, 8)
                                }
                            )
                    }
                    .padding()
                    .background(Color(.systemBackground))
                    .cornerRadius(16)
                    .shadow(color: Color.black.opacity(0.05), radius: 5, x: 0, y: 2)
                    .padding(.horizontal)
                }
                .padding(.vertical)
            }
            .navigationTitle("Dashboard")
            .background(Color(.systemGroupedBackground))
        }
    }
}

struct SummaryCard: View {
    let title: String
    let value: String
    let icon: String
    let color: Color
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: icon)
                    .font(.title2)
                    .foregroundColor(color)
                Spacer()
            }
            
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                Text(value)
                    .font(.title2)
                    .fontWeight(.bold)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(16)
        .shadow(color: Color.black.opacity(0.05), radius: 5, x: 0, y: 2)
    }
}
