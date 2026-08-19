import SwiftUI

struct EliminationView: View {
    @EnvironmentObject private var appModel: AppModel
    @Environment(\.dismiss) private var dismiss
    private let initial: [SavedRecipeRecord]
    @State private var queue: [SavedRecipeRecord]
    @State private var survivors: [SavedRecipeRecord] = []
    @State private var finalists: [SavedRecipeRecord] = []

    init(recipes: [SavedRecipeRecord]) {
        initial = recipes
        _queue = State(initialValue: recipes)
    }

    var body: some View {
        VStack(spacing: 16) {
            if !finalists.isEmpty {
                Text(finalists.count == 1 ? "Your winner" : "Finalists")
                    .font(.largeTitle.bold())
                Text("These survived your quick elimination rounds.")
                    .foregroundStyle(.secondary)
                ForEach(finalists) { recipe in
                    NavigationLink {
                        SavedRecipeDetailView(saved: recipe)
                    } label: {
                        finalistRow(recipe)
                    }
                    .buttonStyle(.plain)
                }
                Button("Done") { dismiss() }.buttonStyle(.borderedProminent)
            } else if let current = queue.first {
                Text("What do you want to try?")
                    .font(.title.bold())
                Text("This round does not change your permanent taste profile.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                RemoteRecipeImage(url: current.imageURL, title: current.title)
                    .frame(maxHeight: 350)
                    .clipped()
                    .clipShape(RoundedRectangle(cornerRadius: 24))
                Text(current.title).font(.title2.bold()).multilineTextAlignment(.center)
                Text("#\(current.rank) \(current.verticalName)").foregroundStyle(.secondary)
                HStack {
                    Button("Pass", systemImage: "xmark") { decide(keep: false, recipe: current) }
                        .buttonStyle(.bordered)
                    Button("Keep", systemImage: "checkmark") { decide(keep: true, recipe: current) }
                        .buttonStyle(.borderedProminent)
                }
            } else {
                ContentUnavailableView("Not enough candidates", systemImage: "shuffle")
            }
        }
        .padding()
        .navigationTitle("Help Me Pick")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func decide(keep: Bool, recipe: SavedRecipeRecord) {
        if keep {
            survivors.append(recipe)
            _ = appModel.recordEvent(.eliminationSelected, recipeID: recipe.recipeID, verticalID: recipe.verticalID)
        } else {
            _ = appModel.recordEvent(.eliminationRejected, recipeID: recipe.recipeID, verticalID: recipe.verticalID)
        }
        queue.removeFirst()
        if queue.isEmpty { finishRound() }
    }

    private func finishRound() {
        if survivors.isEmpty {
            finalists = Array(initial.prefix(2))
        } else if survivors.count <= 2 {
            finalists = survivors
        } else {
            queue = survivors
            survivors = []
        }
    }

    private func finalistRow(_ recipe: SavedRecipeRecord) -> some View {
        HStack(spacing: 12) {
            RemoteRecipeImage(url: recipe.imageURL, title: recipe.title)
                .frame(width: 92, height: 72)
                .clipped()
                .clipShape(RoundedRectangle(cornerRadius: 12))
            VStack(alignment: .leading) {
                Text(recipe.title).font(.headline)
                Text("#\(recipe.rank) · \(recipe.rating, specifier: "%.1f") ★").foregroundStyle(.secondary)
            }
            Spacer()
            Image(systemName: "chevron.right").foregroundStyle(.secondary)
        }
        .padding()
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
    }
}
