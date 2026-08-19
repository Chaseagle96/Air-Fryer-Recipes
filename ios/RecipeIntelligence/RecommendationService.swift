import Foundation

protocol RecommendationService {
    func recommendations(from recipes: [RemoteRecipe], signals: RecommendationSignals) -> [RemoteRecipe]
}

struct MVPRecommendationService: RecommendationService {
    func recommendations(from recipes: [RemoteRecipe], signals: RecommendationSignals) -> [RemoteRecipe] {
        let eligible = recipes.filter {
            !signals.savedRecipeIDs.contains($0.recipeID)
                && !signals.skippedRecipeIDs.contains($0.recipeID)
                && !signals.notNowRecipeIDs.contains($0.recipeID)
        }

        let base = eligible.sorted { lhs, rhs in
            score(lhs) > score(rhs)
        }

        // Gentle diversity re-ranking prevents a high-quality corpus from turning
        // into ten nearly identical cards in a row. This is intentionally simple
        // and replaceable by a learned model later.
        var categoryCounts: [String: Int] = [:]
        var pool = base
        var output: [RemoteRecipe] = []
        while !pool.isEmpty {
            let window = Array(pool.prefix(min(12, pool.count)))
            let best = window.max { lhs, rhs in
                adjustedScore(lhs, categoryCounts: categoryCounts) < adjustedScore(rhs, categoryCounts: categoryCounts)
            } ?? pool[0]
            output.append(best)
            if let category = best.categories.first { categoryCounts[category, default: 0] += 1 }
            pool.removeAll { $0.recipeID == best.recipeID }
        }
        return output
    }

    private func score(_ recipe: RemoteRecipe) -> Double {
        recipe.hierarchicalScore
            + recipe.evidenceConfidence * 0.08
            + recipe.rankConfidence * 0.04
            + min(log10(Double(max(recipe.ratingCount, 1))), 5) * 0.005
    }

    private func adjustedScore(_ recipe: RemoteRecipe, categoryCounts: [String: Int]) -> Double {
        guard let category = recipe.categories.first else { return score(recipe) }
        return score(recipe) - Double(categoryCounts[category, default: 0]) * 0.025
    }
}

protocol HouseholdRecommendationService {
    func convergenceCandidates(
        recipes: [RemoteRecipe],
        profileIDs: [UUID],
        householdID: UUID
    ) -> [HouseholdMatch]
}

struct PlaceholderHouseholdRecommendationService: HouseholdRecommendationService {
    func convergenceCandidates(
        recipes: [RemoteRecipe],
        profileIDs: [UUID],
        householdID: UUID
    ) -> [HouseholdMatch] {
        recipes.prefix(20).map { recipe in
            let perProfile = Dictionary(uniqueKeysWithValues: profileIDs.map { ($0, recipe.rankConfidence) })
            return HouseholdMatch(recipe: recipe, perProfileConfidence: perProfile, householdConfidence: recipe.rankConfidence)
        }
    }
}
