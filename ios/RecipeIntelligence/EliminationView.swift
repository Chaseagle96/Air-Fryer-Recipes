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
        ScrollView {
            VStack(spacing: 18) {
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

                    Button("Done", systemImage: "checkmark") { dismiss() }
                        .recipeGlassButton(prominent: true)
                        .padding(.top, 4)
                } else if let current = queue.first {
                    Text("What do you want to try?")
                        .font(.title.bold())
                        .multilineTextAlignment(.center)
                    Text("This round does not change your permanent taste profile.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)

                    VStack(spacing: 0) {
                        RemoteRecipeImage(url: current.imageURL, title: current.title)
                            .frame(height: 350)
                            .clipped()

                        VStack(spacing: 8) {
                            Text(current.title)
                                .font(.title2.bold())
                                .multilineTextAlignment(.center)
                            Text("#\(current.rank) · \(current.verticalName)")
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(18)
                    }
                    .clipShape(RoundedRectangle(cornerRadius: 30, style: .continuous))
                    .recipeGlassSurface(cornerRadius: 30)

                    RecipeGlassGroup(spacing: 12) {
                        HStack(spacing: 12) {
                            Button("Pass", systemImage: "xmark") {
                                decide(keep: false, recipe: current)
                            }
                            .recipeGlassButton()

                            Button("Keep", systemImage: "checkmark") {
                                decide(keep: true, recipe: current)
                            }
                            .recipeGlassButton(prominent: true)
                        }
                    }
                } else {
                    ContentUnavailableView("Not enough candidates", systemImage: "shuffle")
                }
            }
            .frame(maxWidth: 620)
            .frame(maxWidth: .infinity)
            .padding()
        }
        .recipeScreenBackground()
        .navigationTitle("Help Me Pick")
        .navigationBarTitleDisplayMode(.inline)
        .recipeToolbarBehavior()
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
                .frame(width: 92, height: 76)
                .clipped()
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            VStack(alignment: .leading, spacing: 4) {
                Text(recipe.title).font(.headline)
                Text("#\(recipe.rank) · \(recipe.rating, specifier: "%.1f") ★")
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Image(systemName: "chevron.right")
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .recipeGlassSurface(cornerRadius: RecipeDesign.compactCornerRadius, interactive: true)
    }
}
