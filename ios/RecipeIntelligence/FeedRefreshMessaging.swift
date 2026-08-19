import Foundation

enum FeedRefreshMessaging {
    static let rebuildingRankings = "Recipe Intelligence found new sources and is rebuilding the rankings. Current certified rankings are shown until the refresh completes."
    static let publishingSnapshot = "Recipe Intelligence is publishing updated rankings. Current certified recipes are shown while the new snapshot finishes."
    static let genericFailure = "Couldn’t check for new rankings. Showing current recipes."

    static func message(for error: Error) -> String {
        guard let clientError = error as? RecipeIntelligenceClientError else {
            return genericFailure
        }

        switch clientError {
        case .nonAuthoritativeFeed(let status):
            return status == "refresh_required" ? rebuildingRankings : "Recipe Intelligence is refreshing its ranking service. Current certified rankings are shown until the refresh completes."
        case .inconsistentSnapshot:
            return publishingSnapshot
        case .badResponse, .unsupportedSchema, .pageOutOfRange:
            return genericFailure
        }
    }
}
