import SwiftUI

struct RemoteRecipeImage: View {
    let url: URL?
    let title: String

    var body: some View {
        AsyncImage(url: url, transaction: Transaction(animation: .easeInOut(duration: 0.2))) { phase in
            switch phase {
            case .success(let image):
                image
                    .resizable()
                    .scaledToFill()
            case .failure:
                placeholder(systemImage: "fork.knife")
            case .empty:
                ZStack {
                    Rectangle().fill(.quaternary)
                    ProgressView().controlSize(.large)
                }
            @unknown default:
                placeholder(systemImage: "photo")
            }
        }
        .accessibilityLabel("Photo of \(title)")
    }

    @ViewBuilder
    private func placeholder(systemImage: String) -> some View {
        ZStack {
            Rectangle().fill(.quaternary)
            Image(systemName: systemImage)
                .font(.system(size: 44))
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
        }
    }
}
