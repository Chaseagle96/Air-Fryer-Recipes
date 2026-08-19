import XCTest
@testable import RecipeIntelligence

final class FeedRefreshMessagingTests: XCTestCase {
    func testRefreshRequiredExplainsRankingRebuild() {
        let message = FeedRefreshMessaging.message(
            for: RecipeIntelligenceClientError.nonAuthoritativeFeed("refresh_required")
        )

        XCTAssertEqual(message, FeedRefreshMessaging.rebuildingRankings)
        XCTAssertTrue(message.contains("found new sources"))
        XCTAssertTrue(message.contains("Current certified rankings"))
    }

    func testInconsistentSnapshotExplainsPublicationInProgress() {
        XCTAssertEqual(
            FeedRefreshMessaging.message(for: RecipeIntelligenceClientError.inconsistentSnapshot),
            FeedRefreshMessaging.publishingSnapshot
        )
    }

    func testOrdinaryNetworkFailuresKeepGenericCopy() {
        XCTAssertEqual(
            FeedRefreshMessaging.message(for: URLError(.notConnectedToInternet)),
            FeedRefreshMessaging.genericFailure
        )
    }
}
