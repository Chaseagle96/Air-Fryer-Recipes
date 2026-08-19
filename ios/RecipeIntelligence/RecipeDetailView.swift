import SwiftUI

struct RemoteRecipeDetailView: View {
    @EnvironmentObject private var appModel: AppModel
    @Environment(\.openURL) private var openURL
    let recipe: RemoteRecipe

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                RemoteRecipeImage(url: recipe.photoURL, title: recipe.title)
                    .frame(height: 300)
                    .clipped()
                    .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))

                VStack(alignment: .leading, spacing: 8) {
                    Text(recipe.title).font(.largeTitle.bold())
                    Text("#\(recipe.rank) in \(recipe.verticalName)")
                        .font(.headline)
                        .foregroundStyle(.secondary)
                    HStack {
                        Label(String(format: "%.1f", recipe.rating), systemImage: "star.fill")
                        Text("\(recipe.ratingCount.formatted()) ratings")
                        Text(recipe.confidenceLabel)
                    }
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    Text("From \(recipe.source)")
                        .font(.subheadline.weight(.semibold))
                    if !recipe.author.isEmpty { Text("By \(recipe.author)").foregroundStyle(.secondary) }
                }

                if !recipe.ingredients.isEmpty {
                    sectionTitle("Ingredients")
                    ForEach(Array(recipe.ingredients.enumerated()), id: \.offset) { _, ingredient in
                        Label(ingredient, systemImage: "circle.fill")
                            .symbolRenderingMode(.hierarchical)
                            .font(.body)
                    }
                }

                VStack(alignment: .leading, spacing: 8) {
                    sectionTitle("Cooking directions")
                    if recipe.hasInstructions {
                        Text("Recipe Intelligence found structured directions, but the MVP does not republish publisher instruction prose. Open the original recipe for the complete cooking method.")
                    } else {
                        Text("Open the original publisher page for the complete cooking method.")
                    }
                }
                .foregroundStyle(.secondary)

                if !recipe.rankProvenance.isEmpty {
                    DisclosureGroup("Why this ranks here") {
                        Text(recipe.rankProvenance)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                            .padding(.top, 6)
                    }
                }

                HStack {
                    Button("Save to Try", systemImage: "heart.fill") { appModel.saveFromDetail(recipe) }
                        .buttonStyle(.borderedProminent)
                        .accessibilityIdentifier("detail.save")
                    if let url = recipe.sourceURL {
                        Button("View Original Recipe", systemImage: "arrow.up.right.square") {
                            appModel.recordOriginalSourceOpened(recipeID: recipe.recipeID, verticalID: recipe.verticalID)
                            openURL(url)
                        }
                        .buttonStyle(.bordered)
                    }
                }
            }
            .padding()
        }
        .navigationTitle("Recipe")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func sectionTitle(_ title: String) -> some View {
        Text(title).font(.title2.bold()).accessibilityAddTraits(.isHeader)
    }
}
