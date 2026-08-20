import XCTest

final class RecipeIntelligenceUITests: XCTestCase {
    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    func testSaveRecipeAppearsInSavedCollection() {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing"]
        app.launch()

        XCTAssertTrue(app.navigationBars["Discover"].waitForExistence(timeout: 8))
        let card = app.descendants(matching: .any)["discover.card"]
        XCTAssertTrue(card.waitForExistence(timeout: 5))
        card.swipeRight()

        XCTAssertFalse(
            app.buttons["discover.undo"].exists,
            "Undo should be available by shaking the device, not as a toolbar button."
        )

        app.tabBars.buttons["Saved"].tap()
        XCTAssertTrue(app.navigationBars["Saved"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Crispy Air Fryer Chicken Thighs"].waitForExistence(timeout: 5))
    }

    func testVerticalSwitchAndSwipeSkipAreIndependentActions() {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing"]
        app.launch()

        let slowCooker = app.buttons["vertical.slow_cooker"]
        XCTAssertTrue(slowCooker.waitForExistence(timeout: 5))
        slowCooker.tap()

        let card = app.descendants(matching: .any)["discover.card"]
        XCTAssertTrue(card.waitForExistence(timeout: 5))
        let beforeLabel = card.label
        card.swipeLeft()

        XCTAssertFalse(
            app.buttons["discover.undo"].exists,
            "Undo should be available by shaking the device, not as a toolbar button."
        )

        let nextCard = app.descendants(matching: .any)["discover.card"]
        XCTAssertTrue(nextCard.waitForExistence(timeout: 5))
        XCTAssertNotEqual(nextCard.label, beforeLabel)
    }

    func testCardFlipsToScrollableRecipeDetailsAndTapReturns() {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing"]
        app.launch()

        XCTAssertTrue(app.navigationBars["Discover"].waitForExistence(timeout: 8))
        let card = app.descendants(matching: .any)["discover.card"]
        XCTAssertTrue(card.waitForExistence(timeout: 5))
        card.tap()

        let ingredients = app.descendants(matching: .any)["discover.ingredients"]
        XCTAssertTrue(ingredients.waitForExistence(timeout: 5), "Flipping the card should reveal ingredients inside the card.")
        XCTAssertTrue(app.descendants(matching: .any)["discover.directions"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.descendants(matching: .any)["discover.recipeScroll"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["discover.flipBack"].exists, "The flipped card should not have a dedicated flip-back button.")

        card.tap()
        XCTAssertTrue(app.staticTexts["Tap for ingredients & directions"].waitForExistence(timeout: 5), "Tapping anywhere on the flipped card should return to the ranking face.")
        XCTAssertTrue(app.navigationBars["Discover"].exists, "Recipe details should stay inside the static Discover screen.")
    }

    func testPullDownRefreshReportsCurrentFeed() {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing"]
        app.launch()

        XCTAssertTrue(app.navigationBars["Discover"].waitForExistence(timeout: 8))
        XCTAssertFalse(app.buttons["discover.refresh"].exists, "Discover should not expose a dedicated refresh button.")

        let card = app.descendants(matching: .any)["discover.card"]
        XCTAssertTrue(card.waitForExistence(timeout: 5))
        card.swipeDown()

        XCTAssertTrue(app.staticTexts["Recipe Intelligence is up to date."].waitForExistence(timeout: 5))
    }

    func testDiscoverCardHidesFeedRankBadge() {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing"]
        app.launch()

        XCTAssertTrue(app.navigationBars["Discover"].waitForExistence(timeout: 8))
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH '#' AND label CONTAINS 'Air Fryer'")).firstMatch.exists)
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH '#' AND label CONTAINS 'Slow Cooker'")).firstMatch.exists)
    }
}
